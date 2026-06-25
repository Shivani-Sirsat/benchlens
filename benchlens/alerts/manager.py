"""Fans a finding out to all configured sinks. Failures in one sink never break others."""

from __future__ import annotations

from collections.abc import Iterable

from benchlens.alerts.base_sink import AlertSink
from benchlens.quality.validators import Finding
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


class AlertManager:
    def __init__(self, sinks: Iterable[AlertSink] | None = None) -> None:
        self._sinks: list[AlertSink] = list(sinks) if sinks else []

    def add(self, sink: AlertSink) -> None:
        self._sinks.append(sink)

    @property
    def sinks(self) -> tuple[AlertSink, ...]:
        return tuple(self._sinks)

    def emit(self, findings: Iterable[Finding]) -> int:
        """Route every finding to every sink. Returns the count emitted."""
        count = 0
        for f in findings:
            for sink in self._sinks:
                try:
                    sink.emit(f)
                except Exception as exc:  # noqa: BLE001 — never block pipeline on alert failure
                    log.warning("alert sink %s failed: %s", sink.name, exc)
            count += 1
        return count
