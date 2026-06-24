"""JSON connector — reads JSON or JSON-Lines files.

Supports two layouts (auto-detected from the `format` config key or extension):
    - `json`  : a single JSON document; can be an array OR an object with a
                top-level `records` key.
    - `jsonl` : newline-delimited JSON objects, one record per line.

Config keys:
    path:            File or directory. Required.
    pattern:         Glob pattern (default "*.json" or "*.jsonl").
    format:          "json" | "jsonl" (auto-detected if omitted).
    records_path:    For nested JSON, dotted path to the records array
                     (e.g. "data.runs"). Optional.
    watermark_field: Column for incremental loads. Optional.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from benchlens.ingestion.base_connector import BaseConnector, ConnectorError
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


class JSONConnector(BaseConnector):
    kind = "json"

    def _extract(self, watermark: Any) -> pd.DataFrame:
        path = Path(self.config.get("path", ""))
        if not path.exists():
            raise ConnectorError(f"[{self.name}] JSON path does not exist: {path}")

        fmt = (self.config.get("format") or "").lower()
        records_path = self.config.get("records_path")

        if path.is_dir():
            pattern = self.config.get("pattern") or ("*.jsonl" if fmt == "jsonl" else "*.json")
            files = sorted(path.glob(pattern))
        else:
            files = [path]

        if not files:
            log.warning("[%s] no JSON files found in %s.", self.name, path)
            return pd.DataFrame()

        records: list[dict] = []
        for f in files:
            file_fmt = fmt or ("jsonl" if f.suffix.lower() == ".jsonl" else "json")
            records.extend(_read_one(f, file_fmt, records_path))

        if not records:
            return pd.DataFrame()

        df = pd.json_normalize(records)
        return self._apply_watermark_filter(df, watermark)

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
        return df[mask].reset_index(drop=True)


def _read_one(path: Path, fmt: str, records_path: str | None) -> list[dict]:
    if fmt == "jsonl":
        out: list[dict] = []
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as e:
                    log.warning("Skipping malformed JSONL line %d in %s: %s", line_no, path, e)
        return out

    with path.open("r", encoding="utf-8") as fh:
        doc = json.load(fh)
    if records_path:
        for part in records_path.split("."):
            doc = doc[part]
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        return [doc]
    raise ConnectorError(f"Unsupported JSON shape in {path}: {type(doc).__name__}")
