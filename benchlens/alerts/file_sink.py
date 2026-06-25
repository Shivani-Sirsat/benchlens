"""Append-only JSONL alert sink — durable record for off-system review."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from benchlens.alerts.base_sink import AlertSink
from benchlens.quality.validators import Finding


class FileSink(AlertSink):
    name = "file"

    def __init__(self, path: str | Path = "logs/alerts.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, finding: Finding) -> None:
        record = asdict(finding)
        record["emitted_at"] = datetime.now(timezone.utc).isoformat()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
