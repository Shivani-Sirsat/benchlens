"""Pydantic v2 response models for the BenchLens API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _BaseOut(BaseModel):
    """Shared config: read attributes off ORM rows."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    role: str
    username: str


class UserOut(BaseModel):
    username: str
    role: str


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------


class WorkloadOut(_BaseOut):
    workload_id: int
    code: str
    name: str
    category: str | None = None
    version: str | None = None
    description: str | None = None


class HardwareOut(_BaseOut):
    hardware_id: int
    code: str
    accelerator_type: str
    vendor: str
    sku: str
    cores: int | None = None
    memory_gb: Decimal | None = None
    tdp_watts: int | None = None
    price_usd: Decimal | None = None
    release_year: int | None = None


class StackOut(_BaseOut):
    stack_id: int
    code: str
    name: str
    framework: str | None = None
    version: str | None = None
    driver_version: str | None = None
    os_name: str | None = None
    os_version: str | None = None


class ModelOut(_BaseOut):
    model_id: int
    code: str
    name: str
    family: str | None = None
    parameter_count: int | None = None
    quantization: str | None = None
    context_length: int | None = None


class KpiOut(_BaseOut):
    kpi_id: int
    code: str
    name: str
    category: str
    unit: str
    direction: str
    description: str | None = None


# ---------------------------------------------------------------------------
# Facts / runs
# ---------------------------------------------------------------------------


class KpiValueOut(BaseModel):
    kpi_code: str
    kpi_name: str
    unit: str
    value: Decimal
    direction: str


class RunOut(BaseModel):
    run_id: int
    run_uuid: UUID
    workload_code: str
    hardware_code: str
    stack_code: str | None = None
    model_code: str | None = None
    run_date: date
    started_at: datetime
    duration_s: Decimal | None = None
    run_status: str
    source_name: str | None = None
    source_record_key: str | None = None


class RunDetailOut(RunOut):
    kpis: list[KpiValueOut] = Field(default_factory=list)


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class RunPage(BaseModel):
    items: list[RunOut]
    meta: PageMeta


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


class QualityFindingOut(_BaseOut):
    check_id: int
    log_id: int | None = None
    rule_id: str
    rule_type: str
    severity: str
    status: str
    source_name: str | None = None
    source_record_key: str | None = None
    workload_code: str | None = None
    hardware_code: str | None = None
    kpi_code: str | None = None
    observed_value: Decimal | None = None
    expected_min: Decimal | None = None
    expected_max: Decimal | None = None
    baseline_value: Decimal | None = None
    deviation_pct: Decimal | None = None
    message: str | None = None
    detected_at: datetime
    extra: dict[str, Any] | None = None


class QualityFindingPage(BaseModel):
    items: list[QualityFindingOut]
    meta: PageMeta


class RuleOut(BaseModel):
    id: str
    type: str
    severity: str
    description: str | None = None
    # Range
    kpi_code: str | None = None
    min: float | None = None
    max: float | None = None
    # Freshness
    max_age_days: int | None = None
    # Regression
    baseline_runs: int | None = None
    threshold_pct: float | None = None


# ---------------------------------------------------------------------------
# ETL audit log
# ---------------------------------------------------------------------------


class EtlRunOut(_BaseOut):
    log_id: int
    source_name: str
    pipeline: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    rows_in: int | None = None
    rows_out: int | None = None
    rows_quarantined: int | None = None
    error_message: str | None = None
    extra: dict[str, Any] | None = None


class EtlRunPage(BaseModel):
    items: list[EtlRunOut]
    meta: PageMeta


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class HealthOut(BaseModel):
    status: str
    db: str
    version: str


class ErrorOut(BaseModel):
    detail: str
