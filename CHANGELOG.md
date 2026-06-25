# Changelog

All notable changes to BenchLens will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
