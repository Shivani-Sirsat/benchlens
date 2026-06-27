# Changelog

All notable changes to BenchLens will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.0] — Day 9: Orchestration, containerization & CI/CD
### Added
- **`benchlens/scheduler/`** — APScheduler-based job scheduler that wraps
  `run_pipeline()` for every `enabled: true` source in `config/sources.yaml`.
  Cron expression comes from `scheduler.daily_ingest_cron` in
  `config/settings.yaml`. Each source gets its own job so a failure in one
  source doesn't block the others; job exceptions are logged and swallowed.
  All schedules run in UTC.
- **CLI**:
  - `benchlens scheduler list` — preview the jobs that would be scheduled.
  - `benchlens scheduler start` — start the blocking scheduler (Ctrl+C exits).
- **`docker/Dockerfile`** — multi-stage build on `python:3.12-slim`:
  - Stage 1 (`builder`) provisions a `/opt/venv` with all deps + an editable
    install of the project so the `benchlens` console_script is wired up.
  - Stage 2 (`runtime`) is a fresh slim image with the venv + source copied
    in, a non-root `benchlens` user (uid 1000), and `ENTRYPOINT ["benchlens"]`
    so the same image runs the API, the scheduler, or any one-shot CLI.
- **`docker-compose.yml`** — full local stack (bumped Postgres 15 → 16-alpine
  to match local dev):
  - `postgres` (healthcheck via `pg_isready`)
  - `bootstrap` — one-shot service that runs `benchlens db bootstrap` then
    exits 0; downstream services wait via `service_completed_successfully`.
  - `api` — `benchlens serve --host 0.0.0.0 --port 8000`, exposed on 8000,
    with an HTTP healthcheck against `/health`.
  - `scheduler` — `benchlens scheduler start`.
- **`.dockerignore`** — trims the build context (no `.venv`, no `tests`,
  no `powerbi`, no `.env`, no `__pycache__`).
- **`.github/workflows/ci.yml`** — three-job pipeline:
  - `lint` — `ruff check` + `ruff format --check` on `benchlens/` and
    `scripts/`.
  - `test` — Postgres-16 service container + `benchlens db bootstrap` +
    `pytest --cov`, all on Python 3.12.
  - `docker` — `docker/build-push-action` validates the Dockerfile (no push)
    with GitHub Actions cache for fast subsequent builds.
- **`.pre-commit-config.yaml`** — `ruff` + `ruff-format` + standard
  whitespace/EOF hygiene hooks. `pre-commit install` for local enforcement.
- **`tests/unit/test_scheduler.py`** — 7 new unit tests covering:
  - `JobRegistry` ordering, length, and iteration.
  - `JobConfig` mutable-default isolation (one `kwargs` dict per instance).
  - Only `enabled: true` sources from `sources.yaml` get scheduled.
  - Every cron expression in the live registry parses through
    `CronTrigger.from_crontab`.
  - Every scheduled job is wired to the `_ingest_job` wrapper with a single
    string positional arg, and job_id matches `f"ingest_{source_name}"`.

### Changed
- `docker-compose.yml` upgraded from `postgres:15-alpine` to
  `postgres:16-alpine` to match the local native install and CI service.

### Why APScheduler instead of Prefect/Airflow?
For a single-host demo where every job is a cron-triggered Python call,
APScheduler ships as a single `pip install` with no server process — the
job state lives in the same container as the worker. Prefect/Airflow add
a control-plane component (server, agent, scheduler DB) that's pure
overhead at this scale. The `Scheduler*` abstraction in
`benchlens/scheduler/` is intentionally thin, so swapping in Prefect later
would only touch `runner.py`.

## [0.8.0] — Day 8: Power BI dashboards 3 & 4 + Phase 5 reporting views
### Added
- Migration `004_reporting_views_day8.sql` — 5 new BI-facing views:
  - `vw_model_perf_pivot` — per (model, workload, hardware, KPI) aggregate
    with derived `throughput_per_million_params` (CASE-guarded so it's
    populated only for throughput-like KPIs)
  - `vw_model_comparison_matrix` — one row per model: avg throughput,
    latency, perf-per-watt, perf-per-$1k, perf-per-MParam, accuracy,
    total energy. Per-run pivot CTE feeds the per-model rollup
  - `vw_run_reliability` — per (workload, hardware) cohort: success/failure
    counts, success%, failure%, MTBF (hours) — `mtbf_hours` uses
    observation-window ÷ (failures − 1), guarded to require ≥2 failures
  - `vw_regression_trend_daily` — daily DQ-finding counts + avg/max
    deviation per (severity, rule_type, cohort, KPI)
  - `vw_regression_detection_lag` — LEFT JOIN findings → runs via
    (source_name, source_record_key); computes detection lag in minutes
- `view_manager.py` refactor:
  - `VIEW_MIGRATION_PATHS: list[Path]` replaces single-file constant —
    refresh now iterates 003 + 004 in order
  - `REPORTING_VIEWS` registry expanded from 6 → 11 entries
- Power BI artifacts:
  - `powerbi/reports/model_comparison.md` — full spec for dashboard 3
    (5-card row, param-vs-throughput log scatter, family donut,
    perf-per-MParam ranking, full comparison matrix, bookmarks)
  - `powerbi/reports/regression_reliability.md` — full spec for dashboard
    4 (5-card row, stacked-area severity trend, lowest-reliability cohort
    matrix, detection-lag histogram with explicit bucketing, detailed
    findings table, **drill-through configuration** documented for
    Executive Summary → Regression Reliability)
  - `powerbi/datasets/dax_measures.md` — 2 new sections:
    section 9 model comparison (`Models Tested`, `Avg Throughput (Model)`,
    `Avg Perf/Watt (Model)`, `Avg Throughput / MParam`, `Parameter Count
    (B)`, "Top Model" `CONCATENATEX(TOPN(...))` text measures), section
    10 reliability + detection lag (`Sum Failures`, `Min MTBF Hours`,
    `Findings 30d`, `Critical+Error 30d`, `Avg/Median/P95 Detection Lag`)
    + new format-string rows
  - `powerbi/datasets/data_model.md` updated: 11 tables, 8 relationships
    to Calendar (model + reliability tables intentionally not joined),
    expanded hide-from-report list
  - `powerbi/README.md` — view registry table updated to 11 rows
- 17 new integration tests in `tests/integration/test_reporting_views.py`:
  expected columns for all 5 new views, grain uniqueness for
  `vw_model_perf_pivot` (per model+workload+hardware+kpi),
  `vw_model_comparison_matrix` (per model), `vw_run_reliability` (per
  workload+hardware) plus `success_pct + failure_pct = 100` invariant,
  `success_runs + failure_runs <= total_runs` consistency,
  `throughput_per_million_params` only populated for throughput-like
  KPIs, `finding_count > 0` in regression-trend rows, non-negative
  detection-lag when joined

### Changed
- `REPORTING_VIEWS` dict in `benchlens/reports/view_manager.py` reordered
  with Day 7 / Day 8 grouping comments
- `refresh_views()` now applies multiple migration files in order; raises
  `FileNotFoundError` with the full list of missing files

### Test coverage
- 111 tests pass (up from 94 after Day 7, +17 new integration tests).
- Live view counts after Day 8: 107 / 15 / 14 / 107 / 0 / 3 / 65 / 5 / 10 / 0 / 0

## [0.7.0] — Day 7: Power BI semantic layer (dashboards 1 & 2)
### Added
- Migration `003_reporting_views.sql` — six SQL views that form the
  BI-facing semantic layer over the star schema:
  - `vw_run_kpi_flat` — fully denormalized fact (one row per run x KPI)
  - `vw_run_summary` — one row per run with preference-ordered headline
    performance KPI surfaced via `ROW_NUMBER()`
  - `vw_hardware_efficiency` — per-run KPI pivot via `FILTER` aggregates
    plus derived `throughput_per_watt`, `throughput_per_kdollar`, and
    `latency_efficiency_per_watt` (NULLIF guards on denominators)
  - `vw_kpi_trend_daily` — daily aggregate (avg/min/max/stddev) per
    workload/hardware/KPI
  - `vw_regression_summary` — DQ findings joined to KPI attributes with
    `severity_rank` for stable sorting
  - `vw_etl_health` — daily pipeline health (success/fail counts, rows,
    success %)
- `benchlens/reports/` package:
  - `view_manager.py` — `REPORTING_VIEWS` registry, `check_views()`
    inspects `pg_views` + row counts, `refresh_views()` re-applies the
    migration idempotently using a raw DBAPI cursor
- CLI: `benchlens reports views check` and `benchlens reports views
  refresh` under a new `reports` sub-app
- Power BI artifacts under `powerbi/`:
  - `datasets/benchmark_model.pbids` — Postgres connection file (Import mode)
  - `datasets/data_model.md` — view-to-table mapping, `Calendar` DAX,
    relationships table, column hiding rules
  - `datasets/dax_measures.md` — 8 measure groups: run volume + status,
    headline KPI averages, quality + regression, ETL health, hardware
    efficiency, best-of comparisons, trend deltas, conditional-format
    helpers + format-string reference
  - `reports/executive_summary.md` — full spec for dashboard 1
    (4-card row, combo trend, severity stacked column, top-regressions
    table, workload×hardware heatmap, slicers, drill-through targets,
    acceptance checklist)
  - `reports/hardware_performance.md` — full spec for dashboard 2
    (5-card row, perf-per-watt ranking, throughput-vs-power scatter,
    trend chart, comparison matrix, bookmarks)
  - `themes/benchlens_theme.json` — corporate theme JSON
  - `deployment/refresh_views.ps1` — refresh-then-verify wrapper
- 21 integration tests in `tests/integration/test_reporting_views.py`:
  view existence, expected columns, grain uniqueness for `vw_run_kpi_flat`
  and `vw_run_summary`, success-only filter on `vw_hardware_efficiency`,
  derived-metric formula consistency, `severity_rank` determinism,
  `success_pct` range bounds, refresh idempotency

### Test coverage
- 94 tests pass (up from 73 after Day 6, +21 new integration tests).

## [0.6.0] — Day 6: REST API (FastAPI + JWT + RBAC)
### Added
- `benchlens/api/` package:
  - `auth.py` — scrypt password hashing (stdlib `hashlib.scrypt`, no extra
    dependency), `UserStore` seeded from `settings.yaml`, `JwtConfig`,
    `create_access_token`/`decode_access_token` (HS256)
  - `deps.py` — FastAPI dependencies for DB session, current user,
    role-gated `require_role()` factory + `CurrentUser` / `AdminUser` /
    `DbSession` annotated aliases
  - `schemas.py` — Pydantic v2 response models (`RunOut`, `RunDetailOut`,
    `RunPage`, `KpiValueOut`, dim outs, `QualityFindingOut`/`Page`,
    `RuleOut`, `EtlRunOut`/`Page`, `TokenOut`, `UserOut`, `HealthOut`)
  - `app.py` — application factory with CORS middleware, lifespan-driven
    auth init, JSON exception handler, OpenAPI docs at `/docs` + `/redoc`
- Routers under `benchlens/api/routes/`:
  - `system.py` — `GET /health`, `GET /` (public)
  - `auth.py` — `POST /auth/login` (OAuth2 password flow), `GET /auth/me`
  - `runs.py` — `GET /runs` with filters (workload/hardware/model/stack/
    status/date range/source) + paging, `GET /runs/{id}` returns KPI values
  - `dims.py` — `GET /kpis`, `/workloads`, `/hardware`, `/stacks`, `/models`
  - `quality.py` — `GET /quality/findings` (paged + filtered),
    `GET /quality/rules`
  - `etl.py` — `GET /etl/runs` (paged + filtered audit log)
- CLI: `benchlens serve` now actually starts uvicorn against
  `benchlens.api.app:app` (host/port/reload/workers options)
- Tests:
  - 8 unit tests in `tests/unit/test_auth.py` — password hashing, JWT
    round-trip, bad signature, expired token, user store auth
  - 21 integration tests in `tests/integration/test_api.py` via
    `fastapi.testclient.TestClient` — covers health, login flows (good/bad/
    unknown), bearer-token enforcement on protected routes, all dim
    listings, runs list/detail/404, quality rules + findings, ETL audit

### Verified
- `pytest` — 73 passed (was 44 after Day 5)
- Live server: `benchlens serve --port 8765` then `GET /health` (200),
  `POST /auth/login` (200 + JWT), `GET /runs?limit=2` (200, 15 total),
  `GET /runs/15` (returns 7 KPI values), `GET /quality/rules` (13 rules),
  `GET /etl/runs` (9 audit rows). OpenAPI renders at `/docs`.

## [0.5.0] — Day 5: Data Quality & Regression Detection
### Added
- Warehouse migration `002_quality_check_result.sql` — new table to persist
  failed DQ checks with FK to `etl_run_log`
- `QualityCheckResult` ORM model in `benchlens/warehouse/models.py`
- Declarative rules config: `config/dq_rules.yaml` (13 default rules:
  range/freshness/regression)
- `benchlens/quality/` package:
  - `rules.py` — typed `RangeRule`, `FreshnessRule`, `RegressionRule`,
    `RuleSet`, and YAML loader with validation
  - `validators.py` — pure `check_range` / `check_freshness` functions
    producing `Finding` dataclasses
  - `regression.py` — `RegressionDetector` computes a rolling mean baseline
    from prior runs on the same cohort and flags direction-aware deviations
    (`higher_is_better` / `lower_is_better` from `dim_kpi.direction`)
  - `dq_runner.py` — `DQRunner` orchestrates all checks, persists failed
    findings to `quality_check_result`, and emits to an `AlertManager`
- `benchlens/alerts/` package:
  - `base_sink.py` — `AlertSink` ABC
  - `console_sink.py` — Rich-formatted stdout sink
  - `file_sink.py` — append-only JSONL sink (`logs/alerts.jsonl`)
  - `manager.py` — `AlertManager` fans findings out to all sinks
- Pipeline integration: `run_pipeline` runs the DQ phase after load (inside
  the same transaction); summary now includes `dq_findings`,
  `dq_by_severity`, `dq_rules_evaluated`
- `LoadResult.run_ids` so the DQ phase can scope checks to the current batch
- CLI:
  - `benchlens quality rules` — list active DQ rules
  - `benchlens quality history` — view recent persisted findings
  - `benchlens pipeline run --skip-quality` — opt out of DQ
- Tests:
  - 12 unit tests in `tests/unit/test_quality.py` (rule loader + range +
    freshness validators)
  - 1 integration test `tests/integration/test_regression.py` that seeds a
    5-run baseline, ingests an anomalous run, and asserts a regression is
    detected, persisted, and alerted

### Verified
- `db bootstrap` applies migration 002; warehouse summary clean
- `pytest` — 44 passed (was 31 after Day 4)
- `pipeline run --source sample_csv` — 13 rules evaluated, 0 findings on
  clean fixture data, audit row marked success

## [0.1.0] — Day 1: Scaffolding & Foundation
### Added
- Initial project structure for all 10 days of work
- Python package layout (`benchlens/`) with submodule stubs
- Root config: `README.md`, `LICENSE` (MIT), `.gitignore`, `.env.example`
- Build config: `requirements.txt`, `pyproject.toml`, `Makefile`
- Container stub: `docker-compose.yml` (PostgreSQL placeholder, expanded on Day 9)
- YAML configs: `settings.yaml`, `logging.yaml`, `sources.yaml`, `kpi_definitions.yaml`
- Utilities: `logger.py`, `config_loader.py`, `db.py`
- CLI entry point (`benchlens.main`) with subcommand skeletons:
  `version`, `bootstrap-db`, `ingest`, `run-pipeline`, `serve`
