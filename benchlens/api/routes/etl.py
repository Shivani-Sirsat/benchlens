"""ETL audit log endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from benchlens.api.deps import CurrentUser, DbSession
from benchlens.api.schemas import EtlRunOut, EtlRunPage, PageMeta
from benchlens.warehouse.models import EtlRunLog

router = APIRouter()


@router.get("/runs", response_model=EtlRunPage, summary="List pipeline audit rows")
def list_etl_runs(
    user: CurrentUser,  # noqa: ARG001
    db: DbSession,
    source_name: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status", description="started|success|failed")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EtlRunPage:
    stmt = select(EtlRunLog)
    count_q = select(func.count()).select_from(EtlRunLog)
    if source_name:
        stmt = stmt.where(EtlRunLog.source_name == source_name)
        count_q = count_q.where(EtlRunLog.source_name == source_name)
    if status_filter:
        stmt = stmt.where(EtlRunLog.status == status_filter)
        count_q = count_q.where(EtlRunLog.status == status_filter)

    total = int(db.execute(count_q).scalar_one())
    rows = db.execute(
        stmt.order_by(EtlRunLog.started_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return EtlRunPage(
        items=[EtlRunOut.model_validate(r) for r in rows],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )
