"""Alert sink ABC. Concrete sinks (console, file, slack, teams) implement `emit`."""

from __future__ import annotations

from abc import ABC, abstractmethod

from benchlens.quality.validators import Finding


class AlertSink(ABC):
    """One destination for DQ findings."""

    name: str = "alert-sink"

    @abstractmethod
    def emit(self, finding: Finding) -> None:
        """Send a single finding to this destination. Must be exception-safe."""
        raise NotImplementedError
