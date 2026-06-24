"""Write start/success/failure rows to `etl_run_log` for every pipeline execution.

Designed as a context manager so success / failure transitions happen
automatically:

    with EtlAudit(session, "sample_csv", "pipeline") as audit:
        audit.rows_in = 10
        # ... do work ...
        audit.rows_out = 10
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import TracebackType
from typing import Any

from sqlalchemy.orm import Session

from benchlens.utils.logger import get_logger
from benchlens.warehouse.models import EtlRunLog

log = get_logger(__name__)


class EtlAudit:
    """Context manager that maintains an `etl_run_log` row."""

    def __init__(
        self,
        session: Session,
        source_name: str,
        pipeline: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._session = session
        self.source_name = source_name
        self.pipeline = pipeline
        self.rows_in: int | None = None
        self.rows_out: int | None = None
        self.rows_quarantined: int | None = None
        self.extra: dict[str, Any] = dict(extra or {})
        self._log_row: EtlRunLog | None = None

    # ----- context manager -----

    def __enter__(self) -> "EtlAudit":
        self._log_row = EtlRunLog(
            source_name=self.source_name,
            pipeline=self.pipeline,
            status="started",
            started_at=datetime.now(timezone.utc),
            extra=self.extra or None,
        )
        self._session.add(self._log_row)
        self._session.flush()  # populate log_id without committing
        log.info(
            "[%s/%s] audit row %d (started)",
            self.source_name, self.pipeline, self._log_row.log_id,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        assert self._log_row is not None
        self._log_row.ended_at = datetime.now(timezone.utc)
        self._log_row.rows_in = self.rows_in
        self._log_row.rows_out = self.rows_out
        self._log_row.rows_quarantined = self.rows_quarantined
        self._log_row.extra = self.extra or None

        if exc is None:
            self._log_row.status = "success"
            log.info(
                "[%s/%s] audit row %d (success rows_in=%s rows_out=%s)",
                self.source_name, self.pipeline, self._log_row.log_id,
                self.rows_in, self.rows_out,
            )
        else:
            self._log_row.status = "failed"
            self._log_row.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            log.exception(
                "[%s/%s] audit row %d (failed)",
                self.source_name, self.pipeline, self._log_row.log_id,
            )
        # Never swallow; let the caller decide.
        return False

    @property
    def log_id(self) -> int | None:
        return None if self._log_row is None else self._log_row.log_id
