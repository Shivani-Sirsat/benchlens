"""Dimension lookups: KPI catalog, workloads, hardware, stacks, models."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from benchlens.api.deps import CurrentUser, DbSession
from benchlens.api.schemas import (
    HardwareOut,
    KpiOut,
    ModelOut,
    StackOut,
    WorkloadOut,
)
from benchlens.warehouse.models import (
    DimHardware,
    DimKpi,
    DimModel,
    DimStack,
    DimWorkload,
)

router = APIRouter()


@router.get("/kpis", response_model=list[KpiOut], tags=["dimensions"])
def list_kpis(
    user: CurrentUser,  # noqa: ARG001
    db: DbSession,
    category: Annotated[str | None, Query()] = None,
) -> list[KpiOut]:
    stmt = select(DimKpi).order_by(DimKpi.code)
    if category:
        stmt = stmt.where(DimKpi.category == category)
    return [KpiOut.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.get("/workloads", response_model=list[WorkloadOut], tags=["dimensions"])
def list_workloads(user: CurrentUser, db: DbSession) -> list[WorkloadOut]:  # noqa: ARG001
    rows = db.execute(select(DimWorkload).order_by(DimWorkload.code)).scalars().all()
    return [WorkloadOut.model_validate(r) for r in rows]


@router.get("/hardware", response_model=list[HardwareOut], tags=["dimensions"])
def list_hardware(
    user: CurrentUser,  # noqa: ARG001
    db: DbSession,
    accelerator_type: Annotated[str | None, Query(description="CPU|GPU|NPU")] = None,
) -> list[HardwareOut]:
    stmt = select(DimHardware).order_by(DimHardware.code)
    if accelerator_type:
        stmt = stmt.where(DimHardware.accelerator_type == accelerator_type)
    return [HardwareOut.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.get("/stacks", response_model=list[StackOut], tags=["dimensions"])
def list_stacks(user: CurrentUser, db: DbSession) -> list[StackOut]:  # noqa: ARG001
    rows = db.execute(select(DimStack).order_by(DimStack.code)).scalars().all()
    return [StackOut.model_validate(r) for r in rows]


@router.get("/models", response_model=list[ModelOut], tags=["dimensions"])
def list_models(
    user: CurrentUser,  # noqa: ARG001
    db: DbSession,
    family: Annotated[str | None, Query()] = None,
) -> list[ModelOut]:
    stmt = select(DimModel).order_by(DimModel.code)
    if family:
        stmt = stmt.where(DimModel.family == family)
    return [ModelOut.model_validate(r) for r in db.execute(stmt).scalars().all()]
