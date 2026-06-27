"""Manage reporting views that back Power BI dashboards.

These views are created by `migrations/003_reporting_views.sql`. This module
provides operational helpers for the CLI:

- `check_views()` returns the list of installed reporting views and row counts.
- `refresh_views()` re-applies the migration (CREATE OR REPLACE VIEW), useful
  after the underlying schema or KPI catalog has changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from benchlens.utils.db import get_engine
from benchlens.utils.logger import get_logger

log = get_logger(__name__)

# View name -> short description. Order is the order shown by `reports views check`.
REPORTING_VIEWS: dict[str, str] = {
    # Day 7
    "vw_run_kpi_flat": "Denormalized fact: one row per (run, KPI)",
    "vw_run_summary": "One row per run with the headline performance KPI",
    "vw_hardware_efficiency": "Per-run KPI pivot + perf-per-watt / perf-per-$1k",
    "vw_kpi_trend_daily": "Daily KPI aggregate (avg/min/max/stddev)",
    "vw_regression_summary": "DQ findings joined to KPI attributes + severity rank",
    "vw_etl_health": "ETL pipeline health per (date, source, pipeline)",
    # Day 8
    "vw_model_perf_pivot": "Per (model, workload, hardware, KPI) aggregate + param-normalized",
    "vw_model_comparison_matrix": "One row per model: avg throughput/latency/perf-per-watt/per-$1k",
    "vw_run_reliability": "Per (workload, hardware): success%, failures, MTBF (h)",
    "vw_regression_trend_daily": "Daily DQ-finding counts + avg/max deviation",
    "vw_regression_detection_lag": "Per finding: minutes between run start and detection",
}

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "warehouse" / "migrations"

# Migration files that own the reporting views, applied in order on refresh.
VIEW_MIGRATION_PATHS: list[Path] = [
    _MIGRATIONS_DIR / "003_reporting_views.sql",
    _MIGRATIONS_DIR / "004_reporting_views_day8.sql",
]


@dataclass(slots=True)
class ViewInfo:
    name: str
    description: str
    exists: bool
    row_count: int | None  # None if the view does not exist or COUNT failed


def check_views() -> list[ViewInfo]:
    """Return the existence + row count for every reporting view."""
    engine = get_engine()
    out: list[ViewInfo] = []
    with engine.connect() as conn:
        installed = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT viewname FROM pg_views "
                    "WHERE schemaname = current_schema() "
                    "AND viewname = ANY(:names)"
                ),
                {"names": list(REPORTING_VIEWS)},
            ).fetchall()
        }
        for name, desc in REPORTING_VIEWS.items():
            exists = name in installed
            count: int | None = None
            if exists:
                try:
                    count = conn.execute(
                        text(f"SELECT COUNT(*) FROM {name}")  # noqa: S608 — name is from a closed allow-list
                    ).scalar_one()
                except Exception as e:  # noqa: BLE001 — surface to CLI as 'unknown'
                    log.warning("Could not count %s: %s", name, e)
                    count = None
            out.append(ViewInfo(name=name, description=desc, exists=exists, row_count=count))
    return out


def refresh_views() -> list[str]:
    """Re-apply all reporting-view migrations.

    Returns the list of view names known to BenchLens (operator feedback).
    Safe to call repeatedly: every view uses CREATE OR REPLACE.
    """
    missing = [p for p in VIEW_MIGRATION_PATHS if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Reporting-view SQL files missing: " + ", ".join(str(p) for p in missing)
        )

    engine = get_engine()
    # Bypass SQLAlchemy parameter parsing for raw DDL (some views use casts
    # that would otherwise trigger %-placeholder warnings).
    with engine.begin() as conn:
        dbapi_conn = conn.connection.dbapi_connection
        with dbapi_conn.cursor() as cur:
            for path in VIEW_MIGRATION_PATHS:
                sql = path.read_text(encoding="utf-8")
                cur.execute(sql)
                log.info("Reporting views refreshed from %s", path.name)
    return list(REPORTING_VIEWS)
