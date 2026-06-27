"""Unit tests for the APScheduler-based job registry.

These tests do not start APScheduler — they only assert that the registry
is assembled correctly from configuration and that the cron strings parse.
"""

from __future__ import annotations

import pytest
from apscheduler.triggers.cron import CronTrigger

from benchlens.scheduler import (
    JobConfig,
    JobRegistry,
    build_default_registry,
)
from benchlens.scheduler.runner import _ingest_job

pytestmark = pytest.mark.unit


def _noop() -> None:
    return None


class TestJobRegistry:
    def test_empty_registry_has_zero_length(self) -> None:
        assert len(JobRegistry()) == 0
        assert JobRegistry().all() == ()

    def test_add_jobs_preserves_order(self) -> None:
        registry = JobRegistry()
        a = JobConfig("a", "0 1 * * *", "first", _noop)
        b = JobConfig("b", "0 2 * * *", "second", _noop)
        registry.add(a)
        registry.add(b)
        assert registry.all() == (a, b)
        assert len(registry) == 2

    def test_initial_jobs_iterable(self) -> None:
        a = JobConfig("a", "0 1 * * *", "first", _noop)
        b = JobConfig("b", "0 2 * * *", "second", _noop)
        registry = JobRegistry([a, b])
        assert list(registry) == [a, b]

    def test_jobconfig_default_kwargs_isolated_per_instance(self) -> None:
        # field(default_factory=dict) protects against the classic
        # mutable-default footgun shared across instances.
        a = JobConfig("a", "0 * * * *", "x", _noop)
        b = JobConfig("b", "0 * * * *", "y", _noop)
        assert a.kwargs is not b.kwargs


class TestBuildDefaultRegistry:
    """Reads real config/sources.yaml + settings.yaml from the repo."""

    def test_only_enabled_sources_registered(self) -> None:
        registry = build_default_registry()
        # We don't assert an exact count because sources.yaml can grow,
        # but at minimum the two enabled sample sources must be there.
        job_ids = {j.job_id for j in registry}
        assert "ingest_sample_csv" in job_ids
        assert "ingest_sample_json" in job_ids
        # Disabled sources from sources.yaml must NOT be scheduled.
        for disabled in ("ingest_nightly_csv_dump", "ingest_lab_api", "ingest_lab_db"):
            assert disabled not in job_ids

    def test_every_registered_cron_string_parses(self) -> None:
        registry = build_default_registry()
        assert len(registry) > 0
        for job in registry:
            # Will raise ValueError if cron is malformed.
            trigger = CronTrigger.from_crontab(job.cron, timezone="UTC")
            assert trigger is not None

    def test_jobs_target_the_ingest_wrapper(self) -> None:
        registry = build_default_registry()
        for job in registry:
            assert job.func is _ingest_job
            assert len(job.args) == 1
            assert isinstance(job.args[0], str)
            assert job.job_id == f"ingest_{job.args[0]}"
