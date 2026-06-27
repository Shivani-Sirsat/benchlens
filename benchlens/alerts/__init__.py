"""Alert routing for DQ findings.

Day 5 ships console + JSONL sinks. Email + Microsoft Teams sinks land on Day 9.
"""

from benchlens.alerts.base_sink import AlertSink
from benchlens.alerts.console_sink import ConsoleSink
from benchlens.alerts.file_sink import FileSink
from benchlens.alerts.manager import AlertManager

__all__ = ["AlertSink", "ConsoleSink", "FileSink", "AlertManager"]
