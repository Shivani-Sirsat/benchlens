"""SQLAlchemy 2.x ORM models for the BenchLens warehouse.

Mirrors `warehouse/schema.sql`. The SQL file is the source of truth for DDL;
these models are used by the API, ETL writers, and test fixtures.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all warehouse models."""


# ============================================================================
# Dimensions
# ============================================================================

class DimDate(Base):
    __tablename__ = "dim_date"

    date_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    day_name: Mapped[str] = mapped_column(String(10), nullable=False)
    week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month_name: Mapped[str] = mapped_column(String(10), nullable=False)
    quarter: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_weekend: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (Index("idx_dim_date_year_month", "year", "month"),)


class DimWorkload(Base):
    __tablename__ = "dim_workload"

    workload_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DimHardware(Base):
    __tablename__ = "dim_hardware"

    hardware_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    accelerator_type: Mapped[str] = mapped_column(String(10), nullable=False)
    vendor: Mapped[str] = mapped_column(String(50), nullable=False)
    sku: Mapped[str] = mapped_column(String(200), nullable=False)
    cores: Mapped[int | None] = mapped_column(Integer)
    memory_gb: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    tdp_watts: Mapped[int | None] = mapped_column(Integer)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    release_year: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "accelerator_type IN ('CPU','GPU','NPU')", name="dim_hardware_accel_check"
        ),
        Index("idx_dim_hardware_accel", "accelerator_type"),
    )


class DimStack(Base):
    __tablename__ = "dim_stack"

    stack_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    framework: Mapped[str | None] = mapped_column(String(50))
    version: Mapped[str | None] = mapped_column(String(50))
    driver_version: Mapped[str | None] = mapped_column(String(50))
    os_name: Mapped[str | None] = mapped_column(String(50))
    os_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DimModel(Base):
    __tablename__ = "dim_model"

    model_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    family: Mapped[str | None] = mapped_column(String(50))
    parameter_count: Mapped[int | None] = mapped_column(BigInteger)
    quantization: Mapped[str | None] = mapped_column(String(20))
    context_length: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_dim_model_family", "family"),)


class DimKpi(Base):
    __tablename__ = "dim_kpi"

    kpi_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "category IN ('performance','power','quality','reliability')",
            name="dim_kpi_category_check",
        ),
        CheckConstraint(
            "direction IN ('higher_is_better','lower_is_better')",
            name="dim_kpi_direction_check",
        ),
    )


# ============================================================================
# Facts
# ============================================================================

class FactBenchmarkRun(Base):
    __tablename__ = "fact_benchmark_run"

    run_id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, nullable=False)
    run_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=func.gen_random_uuid(), nullable=False
    )
    workload_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_workload.workload_id"), nullable=False
    )
    hardware_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_hardware.hardware_id"), nullable=False
    )
    stack_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("dim_stack.stack_id"))
    model_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("dim_model.model_id"))
    date_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_date.date_id"), nullable=False
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_s: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    run_status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(String(100))
    source_record_key: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workload: Mapped[DimWorkload] = relationship(lazy="joined")
    hardware: Mapped[DimHardware] = relationship(lazy="joined")
    stack: Mapped[DimStack | None] = relationship(lazy="joined")
    model: Mapped[DimModel | None] = relationship(lazy="joined")

    __table_args__ = (
        PrimaryKeyConstraint("run_id", "run_date", name="fact_benchmark_run_pkey"),
        UniqueConstraint(
            "source_name", "source_record_key", "run_date",
            name="fact_benchmark_run_source_unique",
        ),
        CheckConstraint(
            "run_status IN ('success','fail','timeout','aborted')",
            name="fact_benchmark_run_status_check",
        ),
        Index("idx_fact_run_workload", "workload_id"),
        Index("idx_fact_run_hardware", "hardware_id"),
        Index("idx_fact_run_model", "model_id"),
        Index("idx_fact_run_status", "run_status"),
        Index("idx_fact_run_date_id", "date_id"),
        # Native partitioning is declared in schema.sql; ORM stays unaware of it.
        {"postgresql_partition_by": "RANGE (run_date)"},
    )


class FactKpiValue(Base):
    __tablename__ = "fact_kpi_value"

    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    kpi_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_kpi.kpi_id"), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    inference_time_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    power_watts_avg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    gpu_util_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cpu_util_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    npu_util_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    memory_util_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    kpi: Mapped[DimKpi] = relationship(lazy="joined")

    __table_args__ = (
        PrimaryKeyConstraint("run_id", "run_date", "kpi_id", name="fact_kpi_value_pkey"),
        ForeignKeyConstraint(
            ["run_id", "run_date"],
            ["fact_benchmark_run.run_id", "fact_benchmark_run.run_date"],
            ondelete="CASCADE",
            name="fact_kpi_value_run_fkey",
        ),
        Index("idx_fact_kpi_kpi", "kpi_id"),
        Index("idx_fact_kpi_date", "run_date"),
    )


# ============================================================================
# Audit / operational
# ============================================================================

class EtlRunLog(Base):
    __tablename__ = "etl_run_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pipeline: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_in: Mapped[int | None] = mapped_column(Integer)
    rows_out: Mapped[int | None] = mapped_column(Integer)
    rows_quarantined: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint(
            "status IN ('started','success','failed')", name="etl_run_log_status_check"
        ),
        Index("idx_etl_log_source", "source_name"),
        Index("idx_etl_log_status", "status"),
    )


class QualityCheckResult(Base):
    """Persisted DQ + regression-detection findings (failed checks only)."""
    __tablename__ = "quality_check_result"

    check_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    log_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("etl_run_log.log_id", ondelete="SET NULL")
    )
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(100))
    source_record_key: Mapped[str | None] = mapped_column(String(200))
    workload_code: Mapped[str | None] = mapped_column(String(50))
    hardware_code: Mapped[str | None] = mapped_column(String(100))
    kpi_code: Mapped[str | None] = mapped_column(String(50))
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    expected_min: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    expected_max: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    deviation_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    message: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    extra: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pass','fail')", name="quality_check_result_status_check"
        ),
        CheckConstraint(
            "severity IN ('info','warning','error','critical')",
            name="quality_check_result_severity_check",
        ),
        Index("idx_qcr_log", "log_id"),
        Index("idx_qcr_rule", "rule_id"),
        Index("idx_qcr_status", "status"),
        Index("idx_qcr_kpi_code", "kpi_code"),
    )


__all__ = [
    "Base",
    "DimDate",
    "DimWorkload",
    "DimHardware",
    "DimStack",
    "DimModel",
    "DimKpi",
    "FactBenchmarkRun",
    "FactKpiValue",
    "EtlRunLog",
    "QualityCheckResult",
]
