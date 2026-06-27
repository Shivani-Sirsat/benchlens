"""APScheduler runner: wraps `run_pipeline()` for every enabled source.

Design notes:
* One job per source so a single bad source doesn't block the others.
* `BlockingScheduler` because each container is single-purpose; if we ever
  need an in-process scheduler embedded in the API, swap to `BackgroundScheduler`.
* All jobs run in UTC. Cron expressions come from `config/settings.yaml`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from benchlens.orchestration import run_pipeline
from benchlens.utils.config_loader import load_config
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class JobConfig:
    """A single scheduled job. `cron` is a 5-field POSIX expression."""

    job_id: str
    cron: str
    description: str
    func: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)


class JobRegistry:
    """Ordered container of `JobConfig`. Trivial layer used so tests can
    assemble a registry without spinning up APScheduler."""

    def __init__(self, jobs: Iterable[JobConfig] | None = None) -> None:
        self._jobs: list[JobConfig] = list(jobs or [])

    def add(self, job: JobConfig) -> None:
        self._jobs.append(job)

    def all(self) -> tuple[JobConfig, ...]:
        return tuple(self._jobs)

    def __len__(self) -> int:
        return len(self._jobs)

    def __iter__(self):
        return iter(self._jobs)


def _ingest_job(source_name: str) -> None:
    """Wrapper around `run_pipeline` that swallows exceptions and logs the
    summary, so a single failing source never crashes the scheduler thread."""
    try:
        summary = run_pipeline(source_name, commit_watermark=True)
        log.info(
            "[scheduler] source=%s extracted=%d runs_upserted=%d kpis_upserted=%d dq_findings=%d",
            source_name,
            summary.rows_extracted,
            summary.runs_upserted,
            summary.kpis_upserted,
            summary.dq_findings,
        )
    except Exception:
        log.exception("[scheduler] source=%s FAILED", source_name)


def _enabled_sources() -> list[str]:
    """Return the names of every source with `enabled: true` in sources.yaml."""
    cfg = load_config("sources") or {}
    return [s["name"] for s in (cfg.get("sources") or []) if s.get("enabled") and s.get("name")]


def build_default_registry() -> JobRegistry:
    """Assemble the job list from `settings.yaml` + `sources.yaml`."""
    settings = load_config("settings")
    cron_expr = settings.get("scheduler", {}).get("daily_ingest_cron", "0 2 * * *")

    registry = JobRegistry()
    for source_name in _enabled_sources():
        registry.add(
            JobConfig(
                job_id=f"ingest_{source_name}",
                cron=cron_expr,
                description=f"Nightly ETL for source {source_name!r}",
                func=_ingest_job,
                args=(source_name,),
            )
        )
    return registry


class SchedulerRunner:
    """APScheduler facade. `start()` blocks until SIGINT/SIGTERM."""

    def __init__(self, registry: JobRegistry | None = None) -> None:
        self.registry = registry if registry is not None else build_default_registry()
        self.scheduler = BlockingScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 600,
            },
        )

    def _install(self) -> None:
        for job in self.registry:
            trigger = CronTrigger.from_crontab(job.cron, timezone="UTC")
            self.scheduler.add_job(
                func=job.func,
                args=job.args,
                kwargs=job.kwargs,
                id=job.job_id,
                trigger=trigger,
                name=job.description,
                replace_existing=True,
            )
            log.info(
                "Registered job id=%s cron=%r desc=%s",
                job.job_id,
                job.cron,
                job.description,
            )

    def start(self) -> None:
        if not len(self.registry):
            log.warning(
                "No enabled sources found; scheduler has nothing to do. "
                "Enable a source in config/sources.yaml."
            )
            return
        self._install()
        log.info("Scheduler starting with %d job(s). Ctrl+C to exit.", len(self.registry))
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped.")
