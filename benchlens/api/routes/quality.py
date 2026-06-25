"""Data-quality endpoints: persisted findings + active rule catalog."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from benchlens.api.deps import CurrentUser, DbSession
from benchlens.api.schemas import (
    PageMeta,
    QualityFindingOut,
    QualityFindingPage,
    RuleOut,
)
from benchlens.quality import (
    FreshnessRule,
    RangeRule,
    RegressionRule,
    load_rules,
)
from benchlens.warehouse.models import QualityCheckResult

router = APIRouter()


@router.get("/findings", response_model=QualityFindingPage, summary="List persisted DQ findings")
def list_findings(
    user: CurrentUser,  # noqa: ARG001
    db: DbSession,
    severity: Annotated[str | None, Query(description="info|warning|error|critical")] = None,
    rule_type: Annotated[str | None, Query(description="range|freshness|regression")] = None,
    rule_id: Annotated[str | None, Query()] = None,
    source_name: Annotated[str | None, Query()] = None,
    kpi_code: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query(description="detected_at >= filter")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QualityFindingPage:
    """Paginated list of failed DQ checks."""
    stmt = select(QualityCheckResult)
    count_q = select(func.count()).select_from(QualityCheckResult)

    if severity:
        stmt = stmt.where(QualityCheckResult.severity == severity)
        count_q = count_q.where(QualityCheckResult.severity == severity)
    if rule_type:
        stmt = stmt.where(QualityCheckResult.rule_type == rule_type)
        count_q = count_q.where(QualityCheckResult.rule_type == rule_type)
    if rule_id:
        stmt = stmt.where(QualityCheckResult.rule_id == rule_id)
        count_q = count_q.where(QualityCheckResult.rule_id == rule_id)
    if source_name:
        stmt = stmt.where(QualityCheckResult.source_name == source_name)
        count_q = count_q.where(QualityCheckResult.source_name == source_name)
    if kpi_code:
        stmt = stmt.where(QualityCheckResult.kpi_code == kpi_code)
        count_q = count_q.where(QualityCheckResult.kpi_code == kpi_code)
    if since:
        stmt = stmt.where(QualityCheckResult.detected_at >= since)
        count_q = count_q.where(QualityCheckResult.detected_at >= since)

    total = int(db.execute(count_q).scalar_one())
    rows = db.execute(
        stmt.order_by(QualityCheckResult.detected_at.desc()).limit(limit).offset(offset)
    ).scalars().all()

    return QualityFindingPage(
        items=[QualityFindingOut.model_validate(r) for r in rows],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/rules", response_model=list[RuleOut], summary="List active DQ rules")
def list_rules(user: CurrentUser) -> list[RuleOut]:  # noqa: ARG001
    """Echoes config/dq_rules.yaml — useful for the dashboard to render thresholds."""
    rs = load_rules()
    out: list[RuleOut] = []
    for r in rs.range_rules:
        out.append(RuleOut(
            id=r.id, type=r.type, severity=r.severity, description=r.description,
            kpi_code=r.kpi_code, min=r.min, max=r.max,
        ))
    for r in rs.freshness_rules:
        out.append(RuleOut(
            id=r.id, type=r.type, severity=r.severity, description=r.description,
            max_age_days=r.max_age_days,
        ))
    for r in rs.regression_rules:
        out.append(RuleOut(
            id=r.id, type=r.type, severity=r.severity, description=r.description,
            kpi_code=r.kpi_code, baseline_runs=r.baseline_runs, threshold_pct=r.threshold_pct,
        ))
    return out
