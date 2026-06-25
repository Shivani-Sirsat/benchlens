"""Unit tests for DQ rule loader + validators + regression math.

These tests have NO database dependency — they exercise the pure logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import pytest

from benchlens.quality.rules import (
    FreshnessRule,
    RangeRule,
    RegressionRule,
    RuleConfigError,
    load_rules,
)
from benchlens.quality.validators import (
    Finding,
    check_freshness,
    check_range,
)


# ---------------------------------------------------------------------------
# rules.load_rules
# ---------------------------------------------------------------------------

def _write_rules(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "dq_rules.yaml").write_text(dedent(body), encoding="utf-8")
    return cfg


def test_load_rules_parses_all_three_types(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid YAML with all three rule types should parse cleanly."""
    cfg_dir = _write_rules(
        tmp_path,
        """
        defaults:
          default_severity: warning
        rules:
          - id: r1
            type: range
            kpi_code: gpu_util_pct
            min: 0
            max: 100
            severity: error
          - id: r2
            type: freshness
            max_age_days: 30
          - id: r3
            type: regression
            kpi_code: throughput
            baseline_runs: 7
            threshold_pct: 25
            severity: critical
        """,
    )
    monkeypatch.chdir(tmp_path)
    # config_loader caches by name; clear before reload.
    from benchlens.utils.config_loader import reload_configs
    reload_configs()

    rules = load_rules("dq_rules")
    assert len(rules.range_rules) == 1
    assert len(rules.freshness_rules) == 1
    assert len(rules.regression_rules) == 1
    assert rules.range_rules[0].severity == "error"
    assert rules.freshness_rules[0].severity == "warning"  # default applied
    assert rules.regression_rules[0].threshold_pct == 25.0
    reload_configs()


def test_load_rules_rejects_unknown_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_dir = _write_rules(
        tmp_path,
        """
        rules:
          - id: bad
            type: nonsense
            severity: error
        """,
    )
    monkeypatch.chdir(tmp_path)
    from benchlens.utils.config_loader import reload_configs
    reload_configs()
    with pytest.raises(RuleConfigError):
        load_rules("dq_rules")
    reload_configs()


def test_load_rules_rejects_duplicate_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_rules(
        tmp_path,
        """
        rules:
          - id: dup
            type: freshness
            max_age_days: 1
          - id: dup
            type: freshness
            max_age_days: 2
        """,
    )
    monkeypatch.chdir(tmp_path)
    from benchlens.utils.config_loader import reload_configs
    reload_configs()
    with pytest.raises(RuleConfigError, match="Duplicate"):
        load_rules("dq_rules")
    reload_configs()


def test_load_rules_rejects_range_without_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_rules(
        tmp_path,
        """
        rules:
          - id: r
            type: range
            kpi_code: throughput
            severity: error
        """,
    )
    monkeypatch.chdir(tmp_path)
    from benchlens.utils.config_loader import reload_configs
    reload_configs()
    with pytest.raises(RuleConfigError, match="min.*max"):
        load_rules("dq_rules")
    reload_configs()


# ---------------------------------------------------------------------------
# check_range
# ---------------------------------------------------------------------------

@pytest.fixture
def gpu_util_rule() -> RangeRule:
    return RangeRule(
        id="gpu_util_pct_range",
        type="range",
        severity="error",
        description=None,
        kpi_code="gpu_util_pct",
        min=0.0,
        max=100.0,
    )


def test_check_range_pass(gpu_util_rule: RangeRule) -> None:
    assert check_range(gpu_util_rule, value=85.5) is None


def test_check_range_low_fail(gpu_util_rule: RangeRule) -> None:
    f = check_range(gpu_util_rule, value=-1.0, workload_code="llama-inference-7b")
    assert isinstance(f, Finding)
    assert f.rule_id == "gpu_util_pct_range"
    assert f.kpi_code == "gpu_util_pct"
    assert f.observed_value == -1.0
    assert f.severity == "error"


def test_check_range_high_fail(gpu_util_rule: RangeRule) -> None:
    f = check_range(gpu_util_rule, value=150.0)
    assert f is not None
    assert "150" in f.message


def test_check_range_none_value_passes(gpu_util_rule: RangeRule) -> None:
    assert check_range(gpu_util_rule, value=None) is None


def test_check_range_open_lower_bound() -> None:
    """min=None means only an upper bound is enforced."""
    rule = RangeRule(
        id="r", type="range", severity="warning", description=None,
        kpi_code="power_watts_avg", min=None, max=1000.0,
    )
    assert check_range(rule, value=-5.0) is None  # no lower bound, passes
    assert check_range(rule, value=2000.0) is not None  # over the cap


# ---------------------------------------------------------------------------
# check_freshness
# ---------------------------------------------------------------------------

def test_check_freshness_recent_passes() -> None:
    rule = FreshnessRule(id="f", type="freshness", severity="warning", description=None, max_age_days=7)
    now = datetime(2025, 1, 10, tzinfo=timezone.utc)
    started = datetime(2025, 1, 9, tzinfo=timezone.utc)
    assert check_freshness(rule, run_started_at=started, now=now) is None


def test_check_freshness_stale_fails() -> None:
    rule = FreshnessRule(id="f", type="freshness", severity="warning", description=None, max_age_days=7)
    now = datetime(2025, 1, 30, tzinfo=timezone.utc)
    started = datetime(2025, 1, 1, tzinfo=timezone.utc)
    f = check_freshness(rule, run_started_at=started, now=now, source_record_key="run-42")
    assert f is not None
    assert f.rule_type == "freshness"
    assert f.observed_value is not None and f.observed_value > 7


def test_check_freshness_assumes_utc_for_naive_datetime() -> None:
    rule = FreshnessRule(id="f", type="freshness", severity="warning", description=None, max_age_days=1)
    now = datetime(2025, 1, 10, tzinfo=timezone.utc)
    started = datetime(2025, 1, 1)  # naive
    f = check_freshness(rule, run_started_at=started, now=now)
    assert f is not None
