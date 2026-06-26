"""Integration tests for the Power BI reporting views (migration 003).

Verify that each view exists, exposes the expected columns, and returns rows
that respect the documented grain. Skips automatically if Postgres is
unreachable.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from benchlens.reports import REPORTING_VIEWS, check_views, refresh_views
from benchlens.utils.db import get_engine, ping

pytestmark = pytest.mark.skipif(
    not ping(),
    reason="local Postgres warehouse not reachable; skipping reporting-view tests.",
)


# Each entry: a subset of columns the view must expose. We don't check the
# full column list (it would lock down evolution); we check that the columns
# the DAX library + dashboard specs rely on are present.
EXPECTED_COLUMNS: dict[str, set[str]] = {
    # ---------- Day 7 ----------
    "vw_run_kpi_flat": {
        "run_id", "run_date", "run_status",
        "workload_code", "hardware_code", "kpi_code",
        "kpi_value", "accelerator_type", "kpi_direction",
    },
    "vw_run_summary": {
        "run_id", "run_date", "run_status",
        "workload_code", "hardware_code",
        "primary_kpi_code", "primary_kpi_value", "primary_kpi_direction",
    },
    "vw_hardware_efficiency": {
        "run_id", "hardware_code", "accelerator_type",
        "primary_throughput", "throughput_per_watt",
        "throughput_per_kdollar", "tdp_watts", "price_usd",
    },
    "vw_kpi_trend_daily": {
        "run_date", "workload_code", "hardware_code", "kpi_code",
        "kpi_value_avg", "kpi_value_min", "kpi_value_max", "run_count",
    },
    "vw_regression_summary": {
        "check_id", "detected_at", "detected_date",
        "rule_id", "rule_type", "severity", "severity_rank",
        "workload_code", "hardware_code", "kpi_code",
    },
    "vw_etl_health": {
        "run_date", "source_name", "pipeline",
        "success_runs", "failed_runs", "total_runs", "success_pct",
    },
    # ---------- Day 8 ----------
    "vw_model_perf_pivot": {
        "model_id", "model_code", "model_family", "parameter_count",
        "workload_code", "hardware_code", "kpi_code",
        "kpi_value_avg", "throughput_per_million_params",
    },
    "vw_model_comparison_matrix": {
        "model_id", "model_code", "model_family", "parameter_count",
        "run_count", "avg_throughput", "avg_latency_ms",
        "avg_throughput_per_watt", "throughput_per_million_params",
        "throughput_per_kdollar", "last_run_date",
    },
    "vw_run_reliability": {
        "workload_code", "hardware_code", "accelerator_type",
        "total_runs", "success_runs", "failure_runs",
        "success_pct", "failure_pct", "mtbf_hours",
        "first_run_at", "last_run_at", "last_failure_at",
    },
    "vw_regression_trend_daily": {
        "detected_date", "severity", "rule_type",
        "workload_code", "kpi_code",
        "finding_count", "avg_deviation_pct", "max_abs_deviation_pct",
    },
    "vw_regression_detection_lag": {
        "check_id", "detected_at", "detected_date",
        "rule_id", "severity", "kpi_code",
        "run_id", "run_started_at", "detection_lag_minutes",
    },
}


@pytest.fixture(scope="module", autouse=True)
def _ensure_views_installed() -> None:
    """Re-apply view DDL once per module so tests are self-sufficient."""
    refresh_views()


def test_all_views_listed():
    """`REPORTING_VIEWS` covers exactly the views we test."""
    assert set(REPORTING_VIEWS) == set(EXPECTED_COLUMNS)


def test_check_views_reports_all_installed():
    infos = {info.name: info for info in check_views()}
    missing = [name for name, info in infos.items() if not info.exists]
    assert not missing, f"Missing reporting views: {missing}"


@pytest.mark.parametrize("view_name", list(EXPECTED_COLUMNS))
def test_view_has_expected_columns(view_name: str):
    """Each view exposes the columns the DAX library + dashboards expect."""
    expected = EXPECTED_COLUMNS[view_name]
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :name AND table_schema = current_schema()"
            ),
            {"name": view_name},
        ).fetchall()
    actual = {r[0] for r in rows}
    missing = expected - actual
    assert not missing, f"{view_name} missing columns: {missing}"


@pytest.mark.parametrize("view_name", list(EXPECTED_COLUMNS))
def test_view_returns_rows(view_name: str):
    """Smoke: each view returns >=0 rows without raising (planner sanity)."""
    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {view_name}")).scalar_one()
    assert count >= 0


def test_run_kpi_flat_grain_unique():
    """Grain: one row per (run_id, run_date, kpi_id) in vw_run_kpi_flat."""
    engine = get_engine()
    with engine.connect() as conn:
        dups = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                    SELECT run_id, run_date, kpi_id, COUNT(*) AS c
                    FROM vw_run_kpi_flat
                    GROUP BY run_id, run_date, kpi_id
                    HAVING COUNT(*) > 1
                ) AS d
                """
            )
        ).scalar_one()
    assert dups == 0


def test_run_summary_grain_unique():
    """Grain: one row per (run_id, run_date) in vw_run_summary."""
    engine = get_engine()
    with engine.connect() as conn:
        dups = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                    SELECT run_id, run_date, COUNT(*) AS c
                    FROM vw_run_summary
                    GROUP BY run_id, run_date
                    HAVING COUNT(*) > 1
                ) AS d
                """
            )
        ).scalar_one()
    assert dups == 0


def test_hardware_efficiency_only_successful_runs():
    engine = get_engine()
    with engine.connect() as conn:
        bad = conn.execute(
            text(
                "SELECT COUNT(*) FROM vw_hardware_efficiency "
                "WHERE run_status <> 'success'"
            )
        ).scalar_one()
    assert bad == 0


def test_hardware_efficiency_derived_metrics_consistent():
    """Where both numerator and denominator are present, derived metrics
    should equal the formula (sanity check that division didn't go sideways)."""
    engine = get_engine()
    with engine.connect() as conn:
        mismatched = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM vw_hardware_efficiency
                WHERE primary_throughput IS NOT NULL
                  AND power_watts_avg IS NOT NULL
                  AND power_watts_avg > 0
                  AND throughput_per_watt IS NOT NULL
                  AND ABS(
                          throughput_per_watt
                          - (primary_throughput / power_watts_avg)
                      ) > 1e-6
                """
            )
        ).scalar_one()
    assert mismatched == 0


def test_regression_summary_severity_rank_matches_severity():
    """severity_rank must be a deterministic function of severity."""
    engine = get_engine()
    with engine.connect() as conn:
        mismatches = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM vw_regression_summary
                WHERE
                    (severity = 'critical' AND severity_rank <> 4)
                 OR (severity = 'error'    AND severity_rank <> 3)
                 OR (severity = 'warning'  AND severity_rank <> 2)
                 OR (severity = 'info'     AND severity_rank <> 1)
                """
            )
        ).scalar_one()
    assert mismatches == 0


def test_etl_health_success_pct_in_range():
    engine = get_engine()
    with engine.connect() as conn:
        bad = conn.execute(
            text(
                "SELECT COUNT(*) FROM vw_etl_health "
                "WHERE success_pct < 0 OR success_pct > 100"
            )
        ).scalar_one()
    assert bad == 0


def test_refresh_views_is_idempotent():
    """Calling refresh_views twice should not raise."""
    refresh_views()
    refresh_views()
    infos = check_views()
    assert all(info.exists for info in infos)


# ============================ Day 8 view invariants ==========================

def test_model_perf_pivot_grain_unique():
    """Grain: one row per (model_id, workload_code, hardware_code, kpi_code)."""
    engine = get_engine()
    with engine.connect() as conn:
        dups = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                    SELECT model_id, workload_code, hardware_code, kpi_code,
                           COUNT(*) AS c
                    FROM vw_model_perf_pivot
                    GROUP BY model_id, workload_code, hardware_code, kpi_code
                    HAVING COUNT(*) > 1
                ) AS d
                """
            )
        ).scalar_one()
    assert dups == 0


def test_model_perf_pivot_param_normalized_only_for_throughput_kpis():
    """`throughput_per_million_params` is non-null only for throughput-like KPIs."""
    engine = get_engine()
    with engine.connect() as conn:
        bad = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM vw_model_perf_pivot
                WHERE throughput_per_million_params IS NOT NULL
                  AND kpi_code NOT IN ('throughput', 'tokens_per_sec', 'images_per_sec')
                """
            )
        ).scalar_one()
    assert bad == 0


def test_model_comparison_matrix_grain_unique():
    """One row per model."""
    engine = get_engine()
    with engine.connect() as conn:
        dups = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                    SELECT model_id, COUNT(*) AS c
                    FROM vw_model_comparison_matrix
                    GROUP BY model_id
                    HAVING COUNT(*) > 1
                ) AS d
                """
            )
        ).scalar_one()
    assert dups == 0


def test_run_reliability_grain_and_percentages():
    """Grain: one row per (workload_code, hardware_code); success% + failure% sum
    to 100 (within rounding) when total_runs > 0."""
    engine = get_engine()
    with engine.connect() as conn:
        dups = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                    SELECT workload_code, hardware_code, COUNT(*) AS c
                    FROM vw_run_reliability
                    GROUP BY workload_code, hardware_code
                    HAVING COUNT(*) > 1
                ) AS d
                """
            )
        ).scalar_one()
        assert dups == 0

        bad_pct = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM vw_run_reliability
                WHERE total_runs > 0
                  AND ABS((success_pct + failure_pct) - 100.0) > 0.01
                """
            )
        ).scalar_one()
    assert bad_pct == 0


def test_run_reliability_counts_consistent():
    """success_runs + failure_runs cannot exceed total_runs."""
    engine = get_engine()
    with engine.connect() as conn:
        bad = conn.execute(
            text(
                "SELECT COUNT(*) FROM vw_run_reliability "
                "WHERE success_runs + failure_runs > total_runs"
            )
        ).scalar_one()
    assert bad == 0


def test_regression_trend_daily_finding_counts_positive():
    engine = get_engine()
    with engine.connect() as conn:
        bad = conn.execute(
            text(
                "SELECT COUNT(*) FROM vw_regression_trend_daily "
                "WHERE finding_count <= 0"
            )
        ).scalar_one()
    assert bad == 0


def test_detection_lag_non_negative_when_joined():
    """When detection_lag_minutes is non-null, the regression cannot be
    detected before the run started."""
    engine = get_engine()
    with engine.connect() as conn:
        bad = conn.execute(
            text(
                "SELECT COUNT(*) FROM vw_regression_detection_lag "
                "WHERE detection_lag_minutes IS NOT NULL "
                "  AND detection_lag_minutes < 0"
            )
        ).scalar_one()
    assert bad == 0
