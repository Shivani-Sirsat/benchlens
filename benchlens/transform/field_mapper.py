"""Column renaming based on a source's `mapping` block in sources.yaml.

A connector may emit columns named anything ("workload_name", "latency_ms").
This module renames them to BenchLens canonical names defined in
`benchlens.transform.canonical`.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from benchlens.utils.logger import get_logger

log = get_logger(__name__)


def apply_field_mapping(df: pd.DataFrame, mapping: Mapping[str, str] | None) -> pd.DataFrame:
    """Rename columns in `df` per `mapping` (source_name -> canonical_name).

    Unknown source columns are left untouched. Returns a new DataFrame.
    """
    if not mapping or df.empty:
        return df

    # Source-yaml convention: mapping is {canonical_name: source_column_name}.
    # Invert that so we can hand it to pandas.rename().
    rename = {src: canon for canon, src in mapping.items() if src in df.columns}
    if not rename:
        log.debug("Field mapping had no matching source columns: %s", list(mapping.values()))
        return df

    log.debug("Renaming columns: %s", rename)
    return df.rename(columns=rename)


def strip_prefix(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Drop a leading prefix from column names (e.g. "kpis.throughput" -> "throughput")."""
    if df.empty or not prefix:
        return df
    rename = {c: c[len(prefix):] for c in df.columns if c.startswith(prefix)}
    if not rename:
        return df
    return df.rename(columns=rename)
