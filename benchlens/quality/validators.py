"""Pure validation functions used by the DQ runner.

Each function returns either `None` (pass) or a `Finding` (fail). They have
no DB or config dependencies — easy to unit-test in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from benchlens.quality.rules import FreshnessRule, RangeRule


@dataclass(slots=True)
class Finding:
    """One failed DQ check, ready to persist + alert."""

    rule_id: str
    rule_type: str
    severity: str
    status: str = "fail"
    source_name: str | None = None
    source_record_key: str | None = None
    workload_code: str | None = None
    hardware_code: str | None = None
    kpi_code: str | None = None
    observed_value: float | None = None
    expected_min: float | None = None
    expected_max: float | None = None
    baseline_value: float | None = None
    deviation_pct: float | None = None
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def check_range(
    rule: RangeRule,
    *,
    value: float | None,
    source_name: str | None = None,
    source_record_key: str | None = None,
    workload_code: str | None = None,
    hardware_code: str | None = None,
) -> Finding | None:
    """Fail if `value` falls outside [rule.min, rule.max]. None values pass."""
    if value is None:
        return None
    too_low = rule.min is not None and value < rule.min
    too_high = rule.max is not None and value > rule.max
    if not (too_low or too_high):
        return None

    bound = (
        f"[{rule.min if rule.min is not None else '-inf'}, "
        f"{rule.max if rule.max is not None else '+inf'}]"
    )
    msg = (
        f"{rule.kpi_code}={value} is outside allowed range {bound} "
        f"(workload={workload_code}, hw={hardware_code})."
    )
    return Finding(
        rule_id=rule.id,
        rule_type="range",
        severity=rule.severity,
        source_name=source_name,
        source_record_key=source_record_key,
        workload_code=workload_code,
        hardware_code=hardware_code,
        kpi_code=rule.kpi_code,
        observed_value=float(value),
        expected_min=rule.min,
        expected_max=rule.max,
        message=msg,
    )


def check_freshness(
    rule: FreshnessRule,
    *,
    run_started_at: datetime,
    source_name: str | None = None,
    source_record_key: str | None = None,
    workload_code: str | None = None,
    now: datetime | None = None,
) -> Finding | None:
    """Fail if the run is older than `rule.max_age_days`."""
    ref = now or datetime.now(UTC)
    if run_started_at.tzinfo is None:
        run_started_at = run_started_at.replace(tzinfo=UTC)
    age_days = (ref - run_started_at).total_seconds() / 86400.0
    if age_days <= rule.max_age_days:
        return None

    return Finding(
        rule_id=rule.id,
        rule_type="freshness",
        severity=rule.severity,
        source_name=source_name,
        source_record_key=source_record_key,
        workload_code=workload_code,
        observed_value=round(age_days, 3),
        expected_max=float(rule.max_age_days),
        message=(
            f"Run {source_record_key} is {age_days:.1f} days old (limit {rule.max_age_days})."
        ),
        extra={"run_started_at": run_started_at.isoformat()},
    )
