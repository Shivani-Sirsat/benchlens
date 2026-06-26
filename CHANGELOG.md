# Changelog

All notable changes to BenchLens will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
