"""BenchLens Data Quality + Regression Detection.

Loads declarative rules from `config/dq_rules.yaml`, runs them against the
KPI values produced by a pipeline run, and yields `Finding` records that are
persisted to `quality_check_result` and routed to alert sinks.
"""

from benchlens.quality.dq_runner import DQResult, DQRunner
from benchlens.quality.regression import RegressionDetector
from benchlens.quality.rules import (
    FreshnessRule,
    RangeRule,
    RegressionRule,
    Rule,
    RuleSet,
    load_rules,
)
from benchlens.quality.validators import Finding, check_freshness, check_range

__all__ = [
    "Rule",
    "RangeRule",
    "FreshnessRule",
    "RegressionRule",
    "RuleSet",
    "load_rules",
    "Finding",
    "check_range",
    "check_freshness",
    "RegressionDetector",
    "DQRunner",
    "DQResult",
]
