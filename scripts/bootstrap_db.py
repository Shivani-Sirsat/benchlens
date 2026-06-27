"""Bootstrap the BenchLens warehouse.

Idempotent: safe to run multiple times.

Steps:
  1. Verify connectivity.
  2. Apply schema.sql (creates all tables + partitions if missing).
  3. Populate dim_date for [2024-01-01, 2030-12-31] if empty.
  4. Apply seed_data.sql (KPI catalog, sample dims).
  5. Sync dim_kpi from config/kpi_definitions.yaml (source of truth).
  6. Apply numbered migrations from warehouse/migrations/ (records schema_version).
  7. Print summary.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

# Ensure repo root is on sys.path when run as a script.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchlens.utils.config_loader import load_config  # noqa: E402
from benchlens.utils.db import get_engine, ping  # noqa: E402
from benchlens.utils.logger import get_logger  # noqa: E402

log = get_logger(__name__)

WAREHOUSE_DIR = REPO_ROOT / "benchlens" / "warehouse"
SCHEMA_FILE = WAREHOUSE_DIR / "schema.sql"
SEED_FILE = WAREHOUSE_DIR / "seed_data.sql"
MIGRATIONS_DIR = WAREHOUSE_DIR / "migrations"

DIM_DATE_START = date(2024, 1, 1)
DIM_DATE_END = date(2030, 12, 31)


def _exec_sql_file(path: Path) -> None:
    """Execute a full .sql file (multi-statement, DO $$ blocks supported).

    Uses the raw psycopg cursor (not SQLAlchemy's exec_driver_sql) to avoid
    `%I`/`%L`/`%s` inside PostgreSQL `format()` calls being interpreted as
    psycopg parameter placeholders.
    """
    sql = path.read_text(encoding="utf-8")
    engine = get_engine()
    with engine.begin() as conn:
        dbapi_conn = conn.connection.dbapi_connection
        with dbapi_conn.cursor() as cur:
            cur.execute(sql)
    log.info("Applied %s", path.name)


def _populate_dim_date() -> int:
    """Fill dim_date for the configured range. Returns rows inserted."""
    engine = get_engine()
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM dim_date")).scalar_one()
    if existing and existing > 0:
        log.info("dim_date already has %s rows; skipping.", existing)
        return 0

    rows = []
    cur = DIM_DATE_START
    while cur <= DIM_DATE_END:
        rows.append(
            {
                "date_id": int(cur.strftime("%Y%m%d")),
                "full_date": cur,
                "day": cur.day,
                "day_of_week": cur.isoweekday(),
                "day_name": cur.strftime("%A"),
                "week": int(cur.strftime("%V")),
                "month": cur.month,
                "month_name": cur.strftime("%B"),
                "quarter": (cur.month - 1) // 3 + 1,
                "year": cur.year,
                "is_weekend": cur.isoweekday() >= 6,
            }
        )
        cur += timedelta(days=1)

    insert_sql = text(
        """
        INSERT INTO dim_date
            (date_id, full_date, day, day_of_week, day_name, week,
             month, month_name, quarter, year, is_weekend)
        VALUES
            (:date_id, :full_date, :day, :day_of_week, :day_name, :week,
             :month, :month_name, :quarter, :year, :is_weekend)
        ON CONFLICT (date_id) DO NOTHING
        """
    )
    with engine.begin() as conn:
        conn.execute(insert_sql, rows)
    log.info("Inserted %s rows into dim_date.", len(rows))
    return len(rows)


def _sync_kpi_catalog() -> int:
    """Upsert dim_kpi from config/kpi_definitions.yaml. Returns rows touched."""
    cfg = load_config("kpi_definitions")
    kpis = cfg.get("kpis", [])
    if not kpis:
        log.warning("No KPIs found in kpi_definitions.yaml.")
        return 0

    upsert_sql = text(
        """
        INSERT INTO dim_kpi (code, name, category, unit, direction, description)
        VALUES (:code, :name, :category, :unit, :direction, :description)
        ON CONFLICT (code) DO UPDATE SET
            name        = EXCLUDED.name,
            category    = EXCLUDED.category,
            unit        = EXCLUDED.unit,
            direction   = EXCLUDED.direction,
            description = EXCLUDED.description
        """
    )
    rows = [
        {
            "code": k["id"],
            "name": k["name"],
            "category": k["category"],
            "unit": k["unit"],
            "direction": k["direction"],
            "description": k.get("description"),
        }
        for k in kpis
    ]
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(upsert_sql, rows)
    log.info("Synced %s KPIs from kpi_definitions.yaml into dim_kpi.", len(rows))
    return len(rows)


def _apply_migrations() -> list[str]:
    """Apply any .sql files in warehouse/migrations/ whose version isn't recorded yet."""
    if not MIGRATIONS_DIR.exists():
        return []

    engine = get_engine()
    with engine.connect() as conn:
        applied = {
            row[0] for row in conn.execute(text("SELECT version FROM schema_version")).fetchall()
        }

    new_files: list[str] = []
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            version = int(sql_file.stem.split("_", 1)[0])
        except (ValueError, IndexError):
            log.warning("Skipping migration with unparseable name: %s", sql_file.name)
            continue
        if version in applied:
            log.debug("Migration %s already applied; skipping.", sql_file.name)
            continue
        _exec_sql_file(sql_file)
        new_files.append(sql_file.name)
    return new_files


def _summary() -> None:
    engine = get_engine()
    tables = [
        "dim_date",
        "dim_workload",
        "dim_hardware",
        "dim_stack",
        "dim_model",
        "dim_kpi",
        "fact_benchmark_run",
        "fact_kpi_value",
        "etl_run_log",
    ]
    with engine.connect() as conn:
        log.info("--- Warehouse summary ---")
        for t in tables:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
                log.info("  %-25s %s rows", t, n)
            except Exception as e:
                log.warning("  %-25s ERROR: %s", t, e)


def main() -> int:
    log.info("BenchLens bootstrap starting...")

    if not ping():
        log.error("Cannot connect to PostgreSQL. Check .env and that the service is running.")
        return 1

    if not SCHEMA_FILE.exists():
        log.error("Schema file missing: %s", SCHEMA_FILE)
        return 2

    _exec_sql_file(SCHEMA_FILE)
    _populate_dim_date()

    if SEED_FILE.exists():
        _exec_sql_file(SEED_FILE)
    else:
        log.warning("Seed file missing: %s", SEED_FILE)

    _sync_kpi_catalog()
    _apply_migrations()
    _summary()

    log.info("Bootstrap complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
