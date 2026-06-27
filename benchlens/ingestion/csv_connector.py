"""CSV connector — reads one or many CSV files from a directory.

Config keys (under sources.yaml -> sources[*]):
    path:            Directory containing CSV files. Required.
    pattern:         Glob pattern (default "*.csv").
    watermark_field: Column to use for incremental loads (optional).
    encoding:        File encoding (default "utf-8").
    delimiter:       Field separator (default ",").
    parse_dates:     List of columns to parse as dates (optional).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from benchlens.ingestion.base_connector import BaseConnector, ConnectorError
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


class CSVConnector(BaseConnector):
    kind = "csv"

    def _extract(self, watermark: Any) -> pd.DataFrame:
        path = Path(self.config.get("path", ""))
        if not path.exists():
            raise ConnectorError(f"[{self.name}] CSV path does not exist: {path}")

        pattern = self.config.get("pattern", "*.csv")
        encoding = self.config.get("encoding", "utf-8")
        delimiter = self.config.get("delimiter", ",")
        parse_dates = self.config.get("parse_dates") or False

        files = sorted(path.glob(pattern)) if path.is_dir() else [path]
        if not files:
            log.warning("[%s] no CSV files matched %s in %s.", self.name, pattern, path)
            return pd.DataFrame()

        frames: list[pd.DataFrame] = []
        for f in files:
            log.debug("[%s] reading %s", self.name, f)
            df = pd.read_csv(f, encoding=encoding, delimiter=delimiter, parse_dates=parse_dates)
            df["_source_file"] = f.name
            frames.append(df)

        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self._apply_watermark_filter(combined, watermark)

    def _apply_watermark_filter(self, df: pd.DataFrame, watermark: Any) -> pd.DataFrame:
        if watermark is None or self.watermark_field is None:
            return df
        if df.empty or self.watermark_field not in df.columns:
            return df
        col = df[self.watermark_field]
        try:
            ts = pd.to_datetime(watermark)
            mask = pd.to_datetime(col, errors="coerce") > ts
        except (ValueError, TypeError):
            mask = col > watermark
        kept = df[mask].reset_index(drop=True)
        log.info(
            "[%s] watermark %r filtered %d/%d rows.",
            self.name,
            watermark,
            len(kept),
            len(df),
        )
        return kept
