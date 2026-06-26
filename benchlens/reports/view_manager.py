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
    "vw_run_kpi_flat":        "Denormalized fact: one row per (run, KPI)",
    "vw_run_summary":         "One row per run with the headline performance KPI",
    "vw_hardware_efficiency": "Per-run KPI pivot + perf-per-watt / perf-per-$1k",
    "vw_kpi_trend_daily":     "Daily KPI aggregate (avg/min/max/stddev)",
    "vw_regression_summary":  "DQ findings joined to KPI attributes + severity rank",
    "vw_etl_health":          "ETL pipeline health per (date, source, pipeline)",
}

VIEW_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "warehouse" / "migrations" / "003_reporting_views.sql"
)


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
    """Re-apply the reporting-views migration.

    Returns the list of statements executed (typically the view names) for
    operator feedback. Safe to call repeatedly: all DDL uses CREATE OR REPLACE.
    """
    if not VIEW_MIGRATION_PATH.exists():
        raise FileNotFoundError(f"Reporting-views SQL missing: {VIEW_MIGRATION_PATH}")

    sql = VIEW_MIGRATION_PATH.read_text(encoding="utf-8")

    engine = get_engine()
    # Bypass SQLAlchemy parameter parsing for raw DDL (some views use casts
    # that would otherwise trigger %-placeholder warnings).
    with engine.begin() as conn:
        dbapi_conn = conn.connection.dbapi_connection
        with dbapi_conn.cursor() as cur:
            cur.execute(sql)
    log.info("Reporting views refreshed from %s", VIEW_MIGRATION_PATH.name)
    return list(REPORTING_VIEWS)
