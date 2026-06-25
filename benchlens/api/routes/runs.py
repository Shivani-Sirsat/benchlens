"""Benchmark runs: list with filters + single-run KPI detail."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from benchlens.api.deps import CurrentUser, DbSession
from benchlens.api.schemas import (
    KpiValueOut,
    PageMeta,
    RunDetailOut,
    RunOut,
    RunPage,
)
from benchlens.warehouse.models import (
    DimHardware,
    DimKpi,
    DimModel,
    DimStack,
    DimWorkload,
    FactBenchmarkRun,
    FactKpiValue,
)

router = APIRouter()


def _to_run_out(row: dict) -> RunOut:
    return RunOut(
        run_id=row["run_id"],
        run_uuid=row["run_uuid"],
        workload_code=row["workload_code"],
        hardware_code=row["hardware_code"],
        stack_code=row["stack_code"],
        model_code=row["model_code"],
        run_date=row["run_date"],
        started_at=row["started_at"],
        duration_s=row["duration_s"],
        run_status=row["run_status"],
        source_name=row["source_name"],
        source_record_key=row["source_record_key"],
    )


@router.get("", response_model=RunPage, summary="List benchmark runs")
def list_runs(
    user: CurrentUser,  # noqa: ARG001 — auth gate
    db: DbSession,
    workload: Annotated[str | None, Query(description="dim_workload.code filter")] = None,
    hardware: Annotated[str | None, Query(description="dim_hardware.code filter")] = None,
    model: Annotated[str | None, Query(description="dim_model.code filter")] = None,
    stack: Annotated[str | None, Query(description="dim_stack.code filter")] = None,
    run_status: Annotated[str | None, Query(description="run_status filter")] = None,
    start_date: Annotated[date | None, Query(description="run_date >= filter")] = None,
    end_date: Annotated[date | None, Query(description="run_date <= filter")] = None,
    source_name: Annotated[str | None, Query(description="ETL source_name filter")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunPage:
    """Paginated list of benchmark runs joined with their dim codes."""
    base = (
        select(
            FactBenchmarkRun.run_id,
            FactBenchmarkRun.run_uuid,
            DimWorkload.code.label("workload_code"),
            DimHardware.code.label("hardware_code"),
            DimStack.code.label("stack_code"),
            DimModel.code.label("model_code"),
            FactBenchmarkRun.run_date,
            FactBenchmarkRun.started_at,
            FactBenchmarkRun.duration_s,
            FactBenchmarkRun.run_status,
            FactBenchmarkRun.source_name,
            FactBenchmarkRun.source_record_key,
        )
        .join(DimWorkload, DimWorkload.workload_id == FactBenchmarkRun.workload_id)
        .join(DimHardware, DimHardware.hardware_id == FactBenchmarkRun.hardware_id)
        .outerjoin(DimStack, DimStack.stack_id == FactBenchmarkRun.stack_id)
        .outerjoin(DimModel, DimModel.model_id == FactBenchmarkRun.model_id)
    )
    count_q = select(func.count()).select_from(FactBenchmarkRun)

    if workload:
        base = base.where(DimWorkload.code == workload)
        count_q = count_q.join(DimWorkload, DimWorkload.workload_id == FactBenchmarkRun.workload_id) \
            .where(DimWorkload.code == workload)
    if hardware:
        base = base.where(DimHardware.code == hardware)
        count_q = count_q.join(DimHardware, DimHardware.hardware_id == FactBenchmarkRun.hardware_id) \
            .where(DimHardware.code == hardware)
    if model:
        base = base.where(DimModel.code == model)
        count_q = count_q.join(DimModel, DimModel.model_id == FactBenchmarkRun.model_id) \
            .where(DimModel.code == model)
    if stack:
        base = base.where(DimStack.code == stack)
        count_q = count_q.join(DimStack, DimStack.stack_id == FactBenchmarkRun.stack_id) \
            .where(DimStack.code == stack)
    if run_status:
        base = base.where(FactBenchmarkRun.run_status == run_status)
        count_q = count_q.where(FactBenchmarkRun.run_status == run_status)
    if start_date:
        base = base.where(FactBenchmarkRun.run_date >= start_date)
        count_q = count_q.where(FactBenchmarkRun.run_date >= start_date)
    if end_date:
        base = base.where(FactBenchmarkRun.run_date <= end_date)
        count_q = count_q.where(FactBenchmarkRun.run_date <= end_date)
    if source_name:
        base = base.where(FactBenchmarkRun.source_name == source_name)
        count_q = count_q.where(FactBenchmarkRun.source_name == source_name)

    total = int(db.execute(count_q).scalar_one())
    rows = db.execute(
        base.order_by(FactBenchmarkRun.started_at.desc()).limit(limit).offset(offset)
    ).mappings().all()

    return RunPage(
        items=[_to_run_out(dict(r)) for r in rows],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/{run_id}",
    response_model=RunDetailOut,
    responses={404: {"description": "Run not found."}},
    summary="Get a single run with its KPI values",
)
def get_run(
    run_id: int,
    user: CurrentUser,  # noqa: ARG001
    db: DbSession,
) -> RunDetailOut:
    """Single run + every KPI value persisted for it."""
    row = db.execute(
        select(
            FactBenchmarkRun.run_id,
            FactBenchmarkRun.run_uuid,
            DimWorkload.code.label("workload_code"),
            DimHardware.code.label("hardware_code"),
            DimStack.code.label("stack_code"),
            DimModel.code.label("model_code"),
            FactBenchmarkRun.run_date,
            FactBenchmarkRun.started_at,
            FactBenchmarkRun.duration_s,
            FactBenchmarkRun.run_status,
            FactBenchmarkRun.source_name,
            FactBenchmarkRun.source_record_key,
        )
        .join(DimWorkload, DimWorkload.workload_id == FactBenchmarkRun.workload_id)
        .join(DimHardware, DimHardware.hardware_id == FactBenchmarkRun.hardware_id)
        .outerjoin(DimStack, DimStack.stack_id == FactBenchmarkRun.stack_id)
        .outerjoin(DimModel, DimModel.model_id == FactBenchmarkRun.model_id)
        .where(FactBenchmarkRun.run_id == run_id)
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    kpi_rows = db.execute(
        select(
            DimKpi.code.label("kpi_code"),
            DimKpi.name.label("kpi_name"),
            DimKpi.unit,
            DimKpi.direction,
            FactKpiValue.value,
        )
        .join(DimKpi, DimKpi.kpi_id == FactKpiValue.kpi_id)
        .where(FactKpiValue.run_id == run_id)
        .order_by(DimKpi.code)
    ).mappings().all()

    return RunDetailOut(
        **_to_run_out(dict(row)).model_dump(),
        kpis=[KpiValueOut(**dict(k)) for k in kpi_rows],
    )
