"""Validate a normalized DataFrame against BenchLens canonical schema.

Responsibilities:
    - Ensure required columns exist.
    - Coerce types (timestamps -> tz-aware datetime, numerics -> float).
    - Map source `run_status` aliases to the warehouse vocabulary.
    - Quarantine rows that fail validation; never drop them silently.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from benchlens.transform.canonical import (
    OPTIONAL_RUN_COLUMNS,
    REQUIRED_RUN_COLUMNS,
    STATUS_ALIAS,
)
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class ValidationResult:
    """Output of `validate_runs`."""

    valid: pd.DataFrame
    quarantine: pd.DataFrame


def validate_runs(df: pd.DataFrame) -> ValidationResult:
    """Split `df` into clean rows + quarantined rows.

    A row is quarantined when:
        - any REQUIRED column is missing or null
        - started_at fails to parse
        - run_status cannot be aliased to the warehouse vocabulary
    """
    if df.empty:
        return ValidationResult(df.copy(), df.copy())

    missing_required = [c for c in REQUIRED_RUN_COLUMNS if c not in df.columns]
    if missing_required:
        # Whole frame is invalid — annotate and quarantine everything.
        bad = df.copy()
        bad["_quarantine_reason"] = f"missing required columns: {missing_required}"
        log.warning("Quarantining %d rows; missing required columns %s", len(bad), missing_required)
        return ValidationResult(df.head(0), bad)

    work = df.copy()

    # Capture originally-null required cells BEFORE we coerce anything.
    null_required_orig = work[list(REQUIRED_RUN_COLUMNS)].isna().any(axis=1)
    original_status = work["run_status"].copy()

    # ---- coerce timestamps ----
    work["started_at"] = pd.to_datetime(work["started_at"], utc=True, errors="coerce")
    if "ended_at" in work.columns:
        work["ended_at"] = pd.to_datetime(work["ended_at"], utc=True, errors="coerce")

    # ---- normalize run_status ----
    work["run_status"] = work["run_status"].astype(str).str.strip().str.lower().map(STATUS_ALIAS)

    # ---- numeric coercions ----
    if "duration_s" in work.columns:
        work["duration_s"] = pd.to_numeric(work["duration_s"], errors="coerce")

    # ---- row-level validity mask ----
    # Recompute null mask using the post-coercion values (so e.g. an unparseable
    # started_at becomes NaT and is treated as null).
    null_required_post = work[list(REQUIRED_RUN_COLUMNS)].isna().any(axis=1)
    bad_status = work["run_status"].isna() & original_status.notna()

    reason = pd.Series([""] * len(work), index=work.index, dtype=object)
    reason[null_required_orig] = "null in required column"
    reason[bad_status] = "unknown run_status"
    # Coercion failures (e.g. unparseable timestamp) that didn't fall into either bucket.
    coercion_failure = null_required_post & ~null_required_orig & ~bad_status
    reason[coercion_failure] = "could not coerce required column"

    quarantine_mask = null_required_orig | null_required_post | bad_status
    work["_quarantine_reason"] = reason

    valid = work[~quarantine_mask].drop(columns=["_quarantine_reason"]).reset_index(drop=True)
    quarantine = work[quarantine_mask].reset_index(drop=True)

    # Make sure we keep only known canonical columns + KPI columns (anything else).
    known_meta = set(REQUIRED_RUN_COLUMNS) | set(OPTIONAL_RUN_COLUMNS) | {"_source_file"}
    log.info("Validation: %d valid, %d quarantined.", len(valid), len(quarantine))
    log.debug(
        "Known meta columns retained on valid rows: %s",
        [c for c in valid.columns if c in known_meta],
    )
    return ValidationResult(valid=valid, quarantine=quarantine)
