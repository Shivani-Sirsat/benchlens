"""Regression detection against a rolling baseline.

For each (workload_id, hardware_id, model_id, stack_id, kpi_id) cohort,
compare the latest value against the mean of the previous N runs. A
deviation larger than `threshold_pct` — in the *bad* direction for that KPI
— produces a regression `Finding`.

Direction is read from `dim_kpi.direction`:
  - `higher_is_better`: bad when value < baseline (drop)
  - `lower_is_better` : bad when value > baseline (rise)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from benchlens.quality.rules import RegressionRule
from benchlens.quality.validators import Finding
from benchlens.warehouse.models import (
    DimHardware,
    DimKpi,
    DimWorkload,
    FactBenchmarkRun,
    FactKpiValue,
)


@dataclass(slots=True)
class _Candidate:
    """A KPI value to evaluate, with the cohort needed to fetch its baseline."""
    run_id: int
    run_date: object  # datetime.date
    workload_id: int
    hardware_id: int
    stack_id: int | None
    model_id: int | None
    kpi_id: int
    kpi_code: str
    direction: str
    value: float
    workload_code: str | None = None
    hardware_code: str | None = None
    source_name: str | None = None
    source_record_key: str | None = None


class RegressionDetector:
    """Detects KPI regressions for runs inserted by the current pipeline."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def detect(self, rules: tuple[RegressionRule, ...], run_ids: list[int]) -> list[Finding]:
        """Run each rule against KPI values from `run_ids`. Returns findings."""
        if not rules or not run_ids:
            return []

        findings: list[Finding] = []
        for rule in rules:
            kpi = self._lookup_kpi(rule.kpi_code)
            if kpi is None:
                continue
            candidates = self._load_candidates(run_ids, kpi)
            for cand in candidates:
                finding = self._evaluate(rule, cand)
                if finding is not None:
                    findings.append(finding)
        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _lookup_kpi(self, kpi_code: str) -> DimKpi | None:
        return self.session.execute(
            select(DimKpi).where(DimKpi.code == kpi_code)
        ).scalar_one_or_none()

    def _load_candidates(self, run_ids: list[int], kpi: DimKpi) -> list[_Candidate]:
        """Pull KPI value + cohort columns for every (run_id, kpi_id) row."""
        stmt = (
            select(
                FactKpiValue.run_id,
                FactKpiValue.run_date,
                FactKpiValue.value,
                FactBenchmarkRun.workload_id,
                FactBenchmarkRun.hardware_id,
                FactBenchmarkRun.stack_id,
                FactBenchmarkRun.model_id,
                FactBenchmarkRun.source_name,
                FactBenchmarkRun.source_record_key,
                DimWorkload.code.label("workload_code"),
                DimHardware.code.label("hardware_code"),
            )
            .join(
                FactBenchmarkRun,
                (FactBenchmarkRun.run_id == FactKpiValue.run_id)
                & (FactBenchmarkRun.run_date == FactKpiValue.run_date),
            )
            .join(DimWorkload, DimWorkload.workload_id == FactBenchmarkRun.workload_id)
            .join(DimHardware, DimHardware.hardware_id == FactBenchmarkRun.hardware_id)
            .where(
                FactKpiValue.kpi_id == kpi.kpi_id,
                FactKpiValue.run_id.in_(run_ids),
            )
        )
        rows = self.session.execute(stmt).all()
        return [
            _Candidate(
                run_id=r.run_id,
                run_date=r.run_date,
                workload_id=r.workload_id,
                hardware_id=r.hardware_id,
                stack_id=r.stack_id,
                model_id=r.model_id,
                kpi_id=kpi.kpi_id,
                kpi_code=kpi.code,
                direction=kpi.direction,
                value=float(r.value),
                workload_code=r.workload_code,
                hardware_code=r.hardware_code,
                source_name=r.source_name,
                source_record_key=r.source_record_key,
            )
            for r in rows
        ]

    def _baseline(self, cand: _Candidate, baseline_runs: int) -> list[float]:
        """Fetch the previous `baseline_runs` KPI values for this cohort."""
        stmt = (
            select(FactKpiValue.value)
            .join(
                FactBenchmarkRun,
                (FactBenchmarkRun.run_id == FactKpiValue.run_id)
                & (FactBenchmarkRun.run_date == FactKpiValue.run_date),
            )
            .where(
                FactKpiValue.kpi_id == cand.kpi_id,
                FactBenchmarkRun.workload_id == cand.workload_id,
                FactBenchmarkRun.hardware_id == cand.hardware_id,
                FactBenchmarkRun.run_status == "success",
                # exclude the candidate itself
                FactKpiValue.run_id != cand.run_id,
                # only count runs from before the candidate
                FactBenchmarkRun.started_at < select(FactBenchmarkRun.started_at)
                .where(FactBenchmarkRun.run_id == cand.run_id)
                .scalar_subquery(),
            )
        )
        # Cohort match on optional dims: equality or both-null.
        if cand.stack_id is None:
            stmt = stmt.where(FactBenchmarkRun.stack_id.is_(None))
        else:
            stmt = stmt.where(FactBenchmarkRun.stack_id == cand.stack_id)
        if cand.model_id is None:
            stmt = stmt.where(FactBenchmarkRun.model_id.is_(None))
        else:
            stmt = stmt.where(FactBenchmarkRun.model_id == cand.model_id)

        stmt = stmt.order_by(FactBenchmarkRun.started_at.desc()).limit(baseline_runs)
        return [float(v) for (v,) in self.session.execute(stmt).all()]

    def _evaluate(self, rule: RegressionRule, cand: _Candidate) -> Finding | None:
        baseline = self._baseline(cand, rule.baseline_runs)
        if len(baseline) < max(2, rule.baseline_runs // 2):
            # Not enough history yet to flag a regression confidently.
            return None
        mean = statistics.fmean(baseline)
        if mean == 0:
            return None

        deviation_pct = (cand.value - mean) / mean * 100.0
        is_regression = (
            cand.direction == "higher_is_better" and deviation_pct <= -rule.threshold_pct
        ) or (
            cand.direction == "lower_is_better" and deviation_pct >= rule.threshold_pct
        )
        if not is_regression:
            return None

        direction_word = "dropped" if cand.direction == "higher_is_better" else "rose"
        msg = (
            f"{cand.kpi_code} {direction_word} {abs(deviation_pct):.1f}% vs. baseline "
            f"({len(baseline)}-run mean={mean:.3f}; observed={cand.value:.3f}) "
            f"on workload={cand.workload_code}, hw={cand.hardware_code}."
        )
        return Finding(
            rule_id=rule.id,
            rule_type="regression",
            severity=rule.severity,
            source_name=cand.source_name,
            source_record_key=cand.source_record_key,
            workload_code=cand.workload_code,
            hardware_code=cand.hardware_code,
            kpi_code=cand.kpi_code,
            observed_value=cand.value,
            baseline_value=mean,
            deviation_pct=round(deviation_pct, 3),
            message=msg,
            extra={
                "baseline_n": len(baseline),
                "threshold_pct": rule.threshold_pct,
                "direction": cand.direction,
            },
        )
