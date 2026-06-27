"""Reshape a wide benchmark-run DataFrame into long KPI rows.

Input  (wide): one row per benchmark run; KPI metrics as columns.
Output (long): two DataFrames —
    - `runs`: one row per benchmark run (run metadata only)
    - `kpis`: one row per (run, kpi) pair with a single numeric value

The split mirrors `fact_benchmark_run` + `fact_kpi_value` in the warehouse.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from benchlens.transform.canonical import (
    COLUMN_TO_KPI,
    DENORM_KPI_COLUMNS,
    OPTIONAL_RUN_COLUMNS,
    REQUIRED_RUN_COLUMNS,
)
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class NormalizeResult:
    runs: pd.DataFrame
    kpis: pd.DataFrame


def normalize(df: pd.DataFrame, known_kpi_codes: set[str] | None = None) -> NormalizeResult:
    """Split `df` into a run frame + a KPI frame.

    `known_kpi_codes` (e.g. dim_kpi.code values) lets us pick up any future
    KPI without code changes — any column whose name matches a known code is
    treated as a metric.
    """
    if df.empty:
        return NormalizeResult(runs=df.copy(), kpis=_empty_kpi_frame())

    known_kpi_codes = known_kpi_codes or set()
    metric_columns = _detect_metric_columns(df.columns, known_kpi_codes)
    log.debug("Detected metric columns: %s", metric_columns)

    run_cols = [c for c in (*REQUIRED_RUN_COLUMNS, *OPTIONAL_RUN_COLUMNS) if c in df.columns]
    runs = df[run_cols].copy().reset_index(drop=True)
    runs["source_record_key"] = runs["source_record_key"].astype(str)

    if not metric_columns:
        log.warning("No KPI metric columns detected on input.")
        return NormalizeResult(runs=runs, kpis=_empty_kpi_frame())

    # Use source_record_key as the linking column between runs + kpis.
    linker = df["source_record_key"].astype(str).reset_index(drop=True)

    # Build a per-row map of denormalized KPI context (one set per run row).
    denorm_context = _build_denorm_context(df, metric_columns)

    kpi_rows: list[dict] = []
    for col, kpi_code in metric_columns.items():
        series = pd.to_numeric(df[col], errors="coerce").reset_index(drop=True)
        for idx, value in series.items():
            if pd.isna(value):
                continue
            row = {
                "source_record_key": linker.iat[idx],
                "kpi_code": kpi_code,
                "value": float(value),
            }
            row.update(denorm_context[idx])
            kpi_rows.append(row)

    kpis = pd.DataFrame(kpi_rows) if kpi_rows else _empty_kpi_frame()
    log.info("Normalize: %d runs, %d KPI rows.", len(runs), len(kpis))
    return NormalizeResult(runs=runs, kpis=kpis)


# ---------- helpers ----------


def _detect_metric_columns(columns, known_kpi_codes: set[str]) -> dict[str, str]:
    """Return {source_column_name: canonical_kpi_code} for every KPI-looking col."""
    out: dict[str, str] = {}
    for c in columns:
        if c in COLUMN_TO_KPI:
            out[c] = COLUMN_TO_KPI[c]
        elif c in known_kpi_codes:
            out[c] = c
    return out


def _build_denorm_context(df: pd.DataFrame, metric_columns: dict[str, str]) -> list[dict]:
    """Pre-compute the per-row denormalized KPI columns (gpu_util_pct, ...)."""
    inverse = {v: k for k, v in metric_columns.items()}  # kpi_code -> source col
    out: list[dict] = []
    for idx in range(len(df)):
        ctx: dict[str, float | None] = {}
        for kpi_code, fkv_col in DENORM_KPI_COLUMNS.items():
            src_col = inverse.get(kpi_code)
            if src_col is None:
                ctx[fkv_col] = None
                continue
            raw = df[src_col].iloc[idx]
            try:
                val = float(raw)
                ctx[fkv_col] = val if val == val else None  # NaN check
            except (TypeError, ValueError):
                ctx[fkv_col] = None
        out.append(ctx)
    return out


def _empty_kpi_frame() -> pd.DataFrame:
    cols = ["source_record_key", "kpi_code", "value", *DENORM_KPI_COLUMNS.values()]
    return pd.DataFrame(columns=cols)
