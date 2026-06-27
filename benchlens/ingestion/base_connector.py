"""Abstract base for ingestion connectors.

A connector is responsible only for **extraction** — pulling raw records from
a source into a typed `IngestResult` (records + metadata). Transformation and
loading live in the `transform/` and `load/` packages (Day 4).

Cross-cutting concerns handled here:
    - Retry with exponential backoff (tenacity)
    - Watermark persistence (file-based; one JSON per source under data/state/)
    - Structured logging and row counting
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from benchlens.utils.logger import get_logger

log = get_logger(__name__)

STATE_DIR = Path("data") / "state"
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_SECONDS = 2


@dataclass
class IngestResult:
    """Output of a connector run."""

    source: str
    connector: str
    records: pd.DataFrame
    new_watermark: Any = None
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def rows(self) -> int:
        return len(self.records)


class ConnectorError(Exception):
    """Raised for unrecoverable connector failures."""


class BaseConnector(ABC):
    """Base class for all extract-side connectors.

    Subclasses implement `_extract()` (the actual fetch) and may override
    `_iter_attempts()` to customize retry semantics.
    """

    #: Stable identifier for the registry; subclasses must set.
    kind: str = ""

    def __init__(self, name: str, config: dict[str, Any]):
        if not name:
            raise ValueError("Connector name is required.")
        self.name = name
        self.config = config or {}
        self.enabled: bool = bool(self.config.get("enabled", True))
        self.watermark_field: str | None = self.config.get("watermark_field")
        self._max_attempts = int(self.config.get("retry_max_attempts", DEFAULT_MAX_ATTEMPTS))
        self._backoff = float(self.config.get("retry_backoff_seconds", DEFAULT_BACKOFF_SECONDS))

    # ----- public API -----

    def run(self) -> IngestResult:
        """Execute the connector. Wraps `_extract()` with retries + watermark IO."""
        if not self.enabled:
            log.info("[%s] disabled in config; returning empty result.", self.name)
            return IngestResult(self.name, self.kind, pd.DataFrame())

        log.info("[%s] starting %s extraction.", self.name, self.kind)
        watermark = self._load_watermark()
        log.debug("[%s] current watermark: %r", self.name, watermark)

        @retry(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=self._backoff, min=1, max=30),
            retry=retry_if_exception_type((IOError, OSError, ConnectionError, TimeoutError)),
            reraise=True,
        )
        def _attempt() -> pd.DataFrame:
            return self._extract(watermark)

        try:
            df = _attempt()
        except RetryError as e:
            raise ConnectorError(f"[{self.name}] exceeded retry attempts: {e}") from e

        new_watermark = self._compute_new_watermark(df, watermark)
        log.info(
            "[%s] extracted %d rows (new watermark=%r).",
            self.name,
            len(df),
            new_watermark,
        )

        return IngestResult(
            source=self.name,
            connector=self.kind,
            records=df,
            new_watermark=new_watermark,
        )

    def commit_watermark(self, value: Any) -> None:
        """Persist the new watermark; call only after a successful load."""
        if value is None or self.watermark_field is None:
            return
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = STATE_DIR / f"{self.name}.json"
        payload = {"watermark": _serialize(value), "updated_at": datetime.now(UTC).isoformat()}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.debug("[%s] watermark committed: %s", self.name, path)

    # ----- subclass hooks -----

    @abstractmethod
    def _extract(self, watermark: Any) -> pd.DataFrame:
        """Pull rows newer than `watermark`. Must return a DataFrame (may be empty)."""

    # ----- internal helpers -----

    def _load_watermark(self) -> Any:
        if self.watermark_field is None:
            return None
        path = STATE_DIR / f"{self.name}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("watermark")
        except (json.JSONDecodeError, OSError):
            log.warning("[%s] could not read watermark file %s.", self.name, path)
            return None

    def _compute_new_watermark(self, df: pd.DataFrame, current: Any) -> Any:
        """Default: max value of the configured watermark column in the new rows."""
        if self.watermark_field is None or df.empty or self.watermark_field not in df.columns:
            return current
        col = df[self.watermark_field]
        try:
            return _serialize(col.max())
        except Exception:
            return current

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} kind={self.kind!r}>"


def _serialize(value: Any) -> Any:
    """Coerce common pandas/numpy/datetime types to JSON-safe primitives."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value
