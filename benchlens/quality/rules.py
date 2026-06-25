"""Typed DQ rule definitions and YAML loader.

Each rule is a small immutable dataclass. The loader reads
`config/dq_rules.yaml`, splits rules by `type`, and returns a `RuleSet` that
the runner can iterate over efficiently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from benchlens.utils.config_loader import load_config

VALID_SEVERITIES = {"info", "warning", "error", "critical"}


class RuleConfigError(ValueError):
    """Raised when a rule in dq_rules.yaml is malformed."""


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    type: str
    severity: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class RangeRule(Rule):
    kpi_code: str = ""
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True, slots=True)
class FreshnessRule(Rule):
    max_age_days: int = 365


@dataclass(frozen=True, slots=True)
class RegressionRule(Rule):
    kpi_code: str = ""
    baseline_runs: int = 5
    threshold_pct: float = 20.0


@dataclass(frozen=True, slots=True)
class RuleSet:
    range_rules: tuple[RangeRule, ...] = field(default_factory=tuple)
    freshness_rules: tuple[FreshnessRule, ...] = field(default_factory=tuple)
    regression_rules: tuple[RegressionRule, ...] = field(default_factory=tuple)

    @property
    def all(self) -> tuple[Rule, ...]:
        return self.range_rules + self.freshness_rules + self.regression_rules

    def __len__(self) -> int:
        return len(self.range_rules) + len(self.freshness_rules) + len(self.regression_rules)


def _require(rule: dict[str, Any], key: str, rule_id: str) -> Any:
    if key not in rule or rule[key] in (None, ""):
        raise RuleConfigError(f"Rule '{rule_id}' is missing required field '{key}'.")
    return rule[key]


def _build_rule(raw: dict[str, Any], default_severity: str) -> Rule:
    rule_id = raw.get("id")
    if not rule_id:
        raise RuleConfigError(f"Rule is missing 'id': {raw!r}")
    rule_type = _require(raw, "type", rule_id)
    severity = raw.get("severity", default_severity)
    if severity not in VALID_SEVERITIES:
        raise RuleConfigError(
            f"Rule '{rule_id}' has invalid severity '{severity}'. "
            f"Must be one of {sorted(VALID_SEVERITIES)}."
        )
    description = raw.get("description")

    if rule_type == "range":
        kpi_code = _require(raw, "kpi_code", rule_id)
        min_v = raw.get("min")
        max_v = raw.get("max")
        if min_v is None and max_v is None:
            raise RuleConfigError(
                f"Range rule '{rule_id}' must specify at least one of 'min' or 'max'."
            )
        return RangeRule(
            id=rule_id, type=rule_type, severity=severity, description=description,
            kpi_code=kpi_code,
            min=float(min_v) if min_v is not None else None,
            max=float(max_v) if max_v is not None else None,
        )

    if rule_type == "freshness":
        max_age_days = int(raw.get("max_age_days", 365))
        return FreshnessRule(
            id=rule_id, type=rule_type, severity=severity, description=description,
            max_age_days=max_age_days,
        )

    if rule_type == "regression":
        kpi_code = _require(raw, "kpi_code", rule_id)
        baseline_runs = int(raw.get("baseline_runs", 5))
        threshold_pct = float(raw.get("threshold_pct", 20.0))
        if baseline_runs < 1:
            raise RuleConfigError(
                f"Regression rule '{rule_id}': baseline_runs must be >= 1."
            )
        if threshold_pct <= 0:
            raise RuleConfigError(
                f"Regression rule '{rule_id}': threshold_pct must be > 0."
            )
        return RegressionRule(
            id=rule_id, type=rule_type, severity=severity, description=description,
            kpi_code=kpi_code, baseline_runs=baseline_runs, threshold_pct=threshold_pct,
        )

    raise RuleConfigError(f"Rule '{rule_id}' has unknown type '{rule_type}'.")


def load_rules(config_name: str = "dq_rules") -> RuleSet:
    """Read `config/<config_name>.yaml` and produce a typed `RuleSet`."""
    cfg = load_config(config_name)
    defaults = cfg.get("defaults") or {}
    default_severity = defaults.get("default_severity", "warning")
    raw_rules: Iterable[dict[str, Any]] = cfg.get("rules") or []

    ranges: list[RangeRule] = []
    freshnesses: list[FreshnessRule] = []
    regressions: list[RegressionRule] = []
    seen: set[str] = set()

    for raw in raw_rules:
        rule = _build_rule(raw, default_severity)
        if rule.id in seen:
            raise RuleConfigError(f"Duplicate rule id: '{rule.id}'.")
        seen.add(rule.id)
        if isinstance(rule, RangeRule):
            ranges.append(rule)
        elif isinstance(rule, FreshnessRule):
            freshnesses.append(rule)
        elif isinstance(rule, RegressionRule):
            regressions.append(rule)

    return RuleSet(
        range_rules=tuple(ranges),
        freshness_rules=tuple(freshnesses),
        regression_rules=tuple(regressions),
    )
