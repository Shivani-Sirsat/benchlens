"""Cached code -> surrogate-key lookups for warehouse dimensions.

Used by the warehouse_writer to translate human-readable codes
(`workload_code="llama2-inference"`) into the integer foreign-key values
required by the fact tables (`workload_id=3`).

Lookup tables are loaded once per session and cached. Use `refresh()` to
invalidate after a dimension change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from benchlens.utils.logger import get_logger
from benchlens.warehouse.models import (
    DimHardware,
    DimKpi,
    DimModel,
    DimStack,
    DimWorkload,
)

log = get_logger(__name__)


class UnknownDimensionError(LookupError):
    """Raised when a required dimension code is missing from the warehouse."""


@dataclass
class DimensionCache:
    workloads: dict[str, int] = field(default_factory=dict)
    hardware: dict[str, int] = field(default_factory=dict)
    stacks: dict[str, int] = field(default_factory=dict)
    models: dict[str, int] = field(default_factory=dict)
    kpis: dict[str, int] = field(default_factory=dict)

    def kpi_codes(self) -> set[str]:
        return set(self.kpis.keys())


class DimensionResolver:
    """Looks up surrogate keys for all 5 SCD-1 dimensions + dim_date."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._cache: DimensionCache | None = None

    # ----- cache management -----

    def cache(self) -> DimensionCache:
        if self._cache is None:
            self._cache = self._load_all()
        return self._cache

    def refresh(self) -> DimensionCache:
        self._cache = None
        return self.cache()

    def _load_all(self) -> DimensionCache:
        s = self._session
        out = DimensionCache(
            workloads=dict(s.execute(select(DimWorkload.code, DimWorkload.workload_id)).all()),
            hardware=dict(s.execute(select(DimHardware.code, DimHardware.hardware_id)).all()),
            stacks=dict(s.execute(select(DimStack.code, DimStack.stack_id)).all()),
            models=dict(s.execute(select(DimModel.code, DimModel.model_id)).all()),
            kpis=dict(s.execute(select(DimKpi.code, DimKpi.kpi_id)).all()),
        )
        log.info(
            "Dim cache loaded: workloads=%d hardware=%d stacks=%d models=%d kpis=%d",
            len(out.workloads), len(out.hardware), len(out.stacks),
            len(out.models), len(out.kpis),
        )
        return out

    # ----- public lookups -----

    def workload_id(self, code: str) -> int:
        return self._required("workload", code, self.cache().workloads)

    def hardware_id(self, code: str) -> int:
        return self._required("hardware", code, self.cache().hardware)

    def stack_id(self, code: str | None) -> int | None:
        return self._optional(code, self.cache().stacks)

    def model_id(self, code: str | None) -> int | None:
        return self._optional(code, self.cache().models)

    def kpi_id(self, code: str) -> int:
        return self._required("kpi", code, self.cache().kpis)

    @staticmethod
    def date_id(value: date | datetime) -> int:
        """Compute the YYYYMMDD integer used as dim_date.date_id."""
        d = value.date() if isinstance(value, datetime) else value
        return d.year * 10000 + d.month * 100 + d.day

    # ----- internal -----

    @staticmethod
    def _required(label: str, code: str, table: Mapping[str, int]) -> int:
        if not code:
            raise UnknownDimensionError(f"{label} code is empty")
        try:
            return table[code]
        except KeyError as e:
            raise UnknownDimensionError(
                f"Unknown {label} code {code!r}; add it to dim_{label} first."
            ) from e

    @staticmethod
    def _optional(code: str | None, table: Mapping[str, int]) -> int | None:
        if code is None or code == "" or code == "nan":
            return None
        return table.get(code)
