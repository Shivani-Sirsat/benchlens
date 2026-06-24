"""Write transformed runs + KPIs into the warehouse with proper upsert semantics.

Strategy:
    fact_benchmark_run
        ON CONFLICT (source_name, source_record_key, run_date) DO UPDATE
        with RETURNING run_id  — so we can correlate KPI rows.

    fact_kpi_value
        ON CONFLICT (run_id, run_date, kpi_id) DO UPDATE
        set value + denormalized columns + created_at.

Caller must wrap this in a transaction (the warehouse_writer opens its own
Session by default).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from benchlens.load.dim_resolver import DimensionResolver, UnknownDimensionError
from benchlens.transform import TransformResult
from benchlens.transform.canonical import DENORM_KPI_COLUMNS
from benchlens.utils.logger import get_logger
from benchlens.warehouse.models import FactBenchmarkRun, FactKpiValue

log = get_logger(__name__)


@dataclass
class LoadResult:
    rows_in: int
    runs_upserted: int
    kpis_upserted: int
    rows_skipped: int  # rows whose dimension codes were unknown
    skipped_reasons: list[str]


class WarehouseWriter:
    """Persists a `TransformResult` into the BenchLens warehouse."""

    def __init__(self, session: Session, source_name: str) -> None:
        self._session = session
        self._source_name = source_name
        self._resolver = DimensionResolver(session)

    def write(self, result: TransformResult) -> LoadResult:
        rows_in = len(result.runs)
        if result.runs.empty:
            log.info("[%s] nothing to load.", self._source_name)
            return LoadResult(0, 0, 0, 0, [])

        # Refresh dim cache once at the start.
        self._resolver.refresh()

        run_payloads, skipped_reasons = self._build_run_rows(result.runs)
        if not run_payloads:
            return LoadResult(rows_in, 0, 0, rows_in, skipped_reasons)

        # Upsert runs and capture run_ids keyed by source_record_key.
        key_to_run_id = self._upsert_runs(run_payloads)
        log.info("[%s] upserted %d runs.", self._source_name, len(key_to_run_id))

        # Build KPI rows using the freshly-known run_ids.
        kpi_payloads = self._build_kpi_rows(result.kpis, key_to_run_id, run_payloads)
        kpis_upserted = self._upsert_kpis(kpi_payloads)
        log.info("[%s] upserted %d KPI values.", self._source_name, kpis_upserted)

        return LoadResult(
            rows_in=rows_in,
            runs_upserted=len(key_to_run_id),
            kpis_upserted=kpis_upserted,
            rows_skipped=rows_in - len(run_payloads),
            skipped_reasons=skipped_reasons,
        )

    # ------------------------------------------------------------------
    # Run rows
    # ------------------------------------------------------------------

    def _build_run_rows(self, runs: pd.DataFrame) -> tuple[list[dict], list[str]]:
        rows: list[dict] = []
        skipped: list[str] = []

        for _, r in runs.iterrows():
            try:
                workload_id = self._resolver.workload_id(str(r["workload_code"]))
                hardware_id = self._resolver.hardware_id(str(r["hardware_code"]))
            except UnknownDimensionError as e:
                reason = f"run {r.get('source_record_key')!r}: {e}"
                log.warning("[%s] skipping %s", self._source_name, reason)
                skipped.append(reason)
                continue

            started_at: datetime = r["started_at"].to_pydatetime() \
                if hasattr(r["started_at"], "to_pydatetime") else r["started_at"]
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            run_date = started_at.date()

            ended_at = r.get("ended_at")
            if ended_at is not None and hasattr(ended_at, "to_pydatetime") and not pd.isna(ended_at):
                ended_at = ended_at.to_pydatetime()
                if ended_at.tzinfo is None:
                    ended_at = ended_at.replace(tzinfo=timezone.utc)
            else:
                ended_at = None

            rows.append({
                "workload_id": workload_id,
                "hardware_id": hardware_id,
                "stack_id": self._resolver.stack_id(_clean(r.get("stack_code"))),
                "model_id": self._resolver.model_id(_clean(r.get("model_code"))),
                "date_id": DimensionResolver.date_id(run_date),
                "run_date": run_date,
                "started_at": started_at,
                "duration_s": _clean_numeric(r.get("duration_s")),
                "run_status": r["run_status"],
                "error_message": _clean(r.get("error_message")),
                "notes": _clean(r.get("notes")),
                "source_name": self._source_name,
                "source_record_key": str(r["source_record_key"]),
            })
        return rows, skipped

    def _upsert_runs(self, payloads: list[dict]) -> dict[tuple[str, "datetime.date"], int]:  # type: ignore[name-defined]
        """Upsert fact_benchmark_run rows; return {(source_record_key, run_date): run_id}."""
        table = FactBenchmarkRun.__table__
        stmt = insert(table).values(payloads)
        # NB: partitioned table — the conflict target's unique index includes run_date.
        update_cols = {
            c.name: stmt.excluded[c.name]
            for c in table.columns
            if c.name in {
                "workload_id", "hardware_id", "stack_id", "model_id",
                "date_id", "started_at", "duration_s", "run_status",
                "error_message", "notes",
            }
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_name", "source_record_key", "run_date"],
            set_=update_cols,
        ).returning(table.c.run_id, table.c.source_record_key, table.c.run_date)

        result = self._session.execute(stmt).all()
        return {(row.source_record_key, row.run_date): row.run_id for row in result}

    # ------------------------------------------------------------------
    # KPI rows
    # ------------------------------------------------------------------

    def _build_kpi_rows(
        self,
        kpis: pd.DataFrame,
        key_to_run_id: dict[tuple[str, "datetime.date"], int],  # type: ignore[name-defined]
        run_payloads: list[dict],
    ) -> list[dict]:
        if kpis.empty:
            return []
        # Build {source_record_key -> run_date} from the payloads we just wrote.
        key_to_run_date = {p["source_record_key"]: p["run_date"] for p in run_payloads}

        rows: list[dict] = []
        for _, k in kpis.iterrows():
            src_key = str(k["source_record_key"])
            run_date = key_to_run_date.get(src_key)
            if run_date is None:
                continue  # KPI without a matching run (must have been skipped)
            run_id = key_to_run_id.get((src_key, run_date))
            if run_id is None:
                continue
            try:
                kpi_id = self._resolver.kpi_id(str(k["kpi_code"]))
            except UnknownDimensionError as e:
                log.warning("[%s] dropping KPI value: %s", self._source_name, e)
                continue

            row = {
                "run_id": run_id,
                "run_date": run_date,
                "kpi_id": kpi_id,
                "value": float(k["value"]),
            }
            for fkv_col in DENORM_KPI_COLUMNS.values():
                v = k.get(fkv_col)
                row[fkv_col] = float(v) if v is not None and not pd.isna(v) else None
            rows.append(row)
        return rows

    def _upsert_kpis(self, payloads: list[dict]) -> int:
        if not payloads:
            return 0
        table = FactKpiValue.__table__
        stmt = insert(table).values(payloads)
        update_cols = {
            "value": stmt.excluded.value,
            **{c: stmt.excluded[c] for c in DENORM_KPI_COLUMNS.values()},
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id", "run_date", "kpi_id"],
            set_=update_cols,
        )
        self._session.execute(stmt)
        return len(payloads)


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    return s


def _clean_numeric(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
