"""Orchestrates DQ + regression checks for one pipeline batch.

Inputs:
  * a SQLAlchemy session bound to the same transaction as the load,
  * the `run_ids` produced by the load,
  * a `RuleSet` loaded from `config/dq_rules.yaml`,
  * (optional) `log_id` to link findings back to the etl_run_log row,
  * (optional) an `AlertManager` to fan findings out to sinks.

Outputs:
  * a `DQResult` summary,
  * findings persisted to `quality_check_result`,
  * alerts emitted via the manager.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from benchlens.quality.regression import RegressionDetector
from benchlens.quality.rules import (
    RangeRule,
    RuleSet,
    load_rules,
)
from benchlens.quality.validators import Finding, check_freshness, check_range
from benchlens.utils.logger import get_logger
from benchlens.warehouse.models import (
    DimHardware,
    DimKpi,
    DimWorkload,
    FactBenchmarkRun,
    FactKpiValue,
    QualityCheckResult,
)

if TYPE_CHECKING:
    from benchlens.alerts.manager import AlertManager

log = get_logger(__name__)


@dataclass
class DQResult:
    rules_evaluated: int
    findings: list[Finding] = field(default_factory=list)
    persisted: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)

    @property
    def fail_count(self) -> int:
        return len(self.findings)


class DQRunner:
    """Runs all DQ + regression rules for a freshly-loaded batch."""

    def __init__(
        self,
        session: Session,
        *,
        rules: RuleSet | None = None,
        alert_manager: AlertManager | None = None,
        log_id: int | None = None,
        source_name: str | None = None,
    ) -> None:
        self.session = session
        self.rules = rules if rules is not None else load_rules()
        self.alerts = alert_manager
        self.log_id = log_id
        self.source_name = source_name
        self._detector = RegressionDetector(session)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def run(self, run_ids: list[int]) -> DQResult:
        if not run_ids:
            return DQResult(rules_evaluated=len(self.rules))

        findings: list[Finding] = []
        findings.extend(self._run_range_rules(run_ids))
        findings.extend(self._run_freshness_rules(run_ids))
        findings.extend(self._detector.detect(self.rules.regression_rules, run_ids))

        persisted = self._persist(findings)
        if self.alerts is not None and findings:
            self.alerts.emit(findings)

        by_sev: dict[str, int] = {}
        for f in findings:
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1

        log.info(
            "[dq] evaluated %d rules over %d run_ids -> %d findings (%s)",
            len(self.rules),
            len(run_ids),
            len(findings),
            by_sev or "clean",
        )
        return DQResult(
            rules_evaluated=len(self.rules),
            findings=findings,
            persisted=persisted,
            by_severity=by_sev,
        )

    # ------------------------------------------------------------------
    # Range
    # ------------------------------------------------------------------
    def _run_range_rules(self, run_ids: list[int]) -> list[Finding]:
        rules = self.rules.range_rules
        if not rules:
            return []
        # Index rules by kpi_code to evaluate each row once per applicable rule.
        rules_by_kpi: dict[str, list[RangeRule]] = {}
        for rule in rules:
            rules_by_kpi.setdefault(rule.kpi_code, []).append(rule)

        stmt = (
            select(
                FactKpiValue.value,
                DimKpi.code.label("kpi_code"),
                FactBenchmarkRun.source_name,
                FactBenchmarkRun.source_record_key,
                DimWorkload.code.label("workload_code"),
                DimHardware.code.label("hardware_code"),
            )
            .join(DimKpi, DimKpi.kpi_id == FactKpiValue.kpi_id)
            .join(
                FactBenchmarkRun,
                (FactBenchmarkRun.run_id == FactKpiValue.run_id)
                & (FactBenchmarkRun.run_date == FactKpiValue.run_date),
            )
            .join(DimWorkload, DimWorkload.workload_id == FactBenchmarkRun.workload_id)
            .join(DimHardware, DimHardware.hardware_id == FactBenchmarkRun.hardware_id)
            .where(FactKpiValue.run_id.in_(run_ids))
            .where(DimKpi.code.in_(rules_by_kpi.keys()))
        )
        findings: list[Finding] = []
        for row in self.session.execute(stmt).all():
            for rule in rules_by_kpi.get(row.kpi_code, []):
                f = check_range(
                    rule,
                    value=float(row.value),
                    source_name=row.source_name,
                    source_record_key=row.source_record_key,
                    workload_code=row.workload_code,
                    hardware_code=row.hardware_code,
                )
                if f is not None:
                    findings.append(f)
        return findings

    # ------------------------------------------------------------------
    # Freshness
    # ------------------------------------------------------------------
    def _run_freshness_rules(self, run_ids: list[int]) -> list[Finding]:
        rules = self.rules.freshness_rules
        if not rules:
            return []
        stmt = (
            select(
                FactBenchmarkRun.started_at,
                FactBenchmarkRun.source_name,
                FactBenchmarkRun.source_record_key,
                DimWorkload.code.label("workload_code"),
            )
            .join(DimWorkload, DimWorkload.workload_id == FactBenchmarkRun.workload_id)
            .where(FactBenchmarkRun.run_id.in_(run_ids))
        )
        findings: list[Finding] = []
        for row in self.session.execute(stmt).all():
            for rule in rules:
                f = check_freshness(
                    rule,
                    run_started_at=row.started_at,
                    source_name=row.source_name,
                    source_record_key=row.source_record_key,
                    workload_code=row.workload_code,
                )
                if f is not None:
                    findings.append(f)
        return findings

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist(self, findings: Iterable[Finding]) -> int:
        rows: list[QualityCheckResult] = []
        for f in findings:
            rows.append(
                QualityCheckResult(
                    log_id=self.log_id,
                    rule_id=f.rule_id,
                    rule_type=f.rule_type,
                    severity=f.severity,
                    status=f.status,
                    source_name=f.source_name or self.source_name,
                    source_record_key=f.source_record_key,
                    workload_code=f.workload_code,
                    hardware_code=f.hardware_code,
                    kpi_code=f.kpi_code,
                    observed_value=_dec(f.observed_value),
                    expected_min=_dec(f.expected_min),
                    expected_max=_dec(f.expected_max),
                    baseline_value=_dec(f.baseline_value),
                    deviation_pct=_dec(f.deviation_pct),
                    message=f.message,
                    extra=f.extra or None,
                )
            )
        if not rows:
            return 0
        self.session.add_all(rows)
        self.session.flush()
        return len(rows)


def _dec(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
