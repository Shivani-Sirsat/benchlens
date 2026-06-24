"""Transform pipeline — chains field mapping, validation, and KPI normalization."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from benchlens.transform.field_mapper import apply_field_mapping, strip_prefix
from benchlens.transform.kpi_normalizer import NormalizeResult, normalize
from benchlens.transform.schema_validator import validate_runs
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class TransformResult:
    runs: pd.DataFrame
    kpis: pd.DataFrame
    quarantine: pd.DataFrame

    @property
    def is_empty(self) -> bool:
        return self.runs.empty


def transform(
    df: pd.DataFrame,
    source_config: dict,
    known_kpi_codes: set[str] | None = None,
) -> TransformResult:
    """Apply the full transform pipeline.

    Parameters
    ----------
    df
        Output of a connector's `run()` call (`IngestResult.records`).
    source_config
        The source entry from `sources.yaml` (used for `mapping`).
    known_kpi_codes
        Set of `dim_kpi.code` values — additional metrics to recognize beyond
        the built-in `COLUMN_TO_KPI` map.
    """
    if df.empty:
        return TransformResult(runs=df.copy(), kpis=df.copy(), quarantine=df.copy())

    log.info("Transform: starting with %d rows.", len(df))

    # 1. flatten nested JSON keys (`kpis.throughput` -> `throughput`).
    df = strip_prefix(df, "kpis.")

    # 2. apply per-source column renames.
    df = apply_field_mapping(df, source_config.get("mapping"))

    # 3. validate + quarantine.
    validated = validate_runs(df)
    if validated.valid.empty:
        return TransformResult(
            runs=validated.valid,
            kpis=pd.DataFrame(),
            quarantine=validated.quarantine,
        )

    # 4. wide -> long.
    normalized: NormalizeResult = normalize(validated.valid, known_kpi_codes)

    return TransformResult(
        runs=normalized.runs,
        kpis=normalized.kpis,
        quarantine=validated.quarantine,
    )
