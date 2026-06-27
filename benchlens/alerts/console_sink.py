"""Rich-formatted console sink — used in dev runs and CLI."""

from __future__ import annotations

from rich.console import Console

from benchlens.alerts.base_sink import AlertSink
from benchlens.quality.validators import Finding

_SEVERITY_STYLE = {
    "info": "cyan",
    "warning": "yellow",
    "error": "red",
    "critical": "bold red on white",
}


class ConsoleSink(AlertSink):
    name = "console"

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def emit(self, finding: Finding) -> None:
        style = _SEVERITY_STYLE.get(finding.severity, "white")
        tag = f"[{style}][{finding.severity.upper()}][/]"
        self._console.print(f"{tag} {finding.rule_type}:{finding.rule_id} → {finding.message}")
