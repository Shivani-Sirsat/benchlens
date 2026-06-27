"""Unit tests for transform layer — pure functions, no DB required."""

from __future__ import annotations

import pandas as pd

from benchlens.transform import (
    REQUIRED_RUN_COLUMNS,
    TransformResult,
    apply_field_mapping,
    normalize,
    strip_prefix,
    transform,
    validate_runs,
)

# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


def test_field_mapping_renames_known_columns() -> None:
    df = pd.DataFrame({"workload_name": ["a"], "latency_ms": [10.0], "other": [1]})
    mapping = {"workload_code": "workload_name", "inference_time_ms": "latency_ms"}
    out = apply_field_mapping(df, mapping)
    assert "workload_code" in out.columns
    assert "inference_time_ms" in out.columns
    assert "other" in out.columns
    assert "workload_name" not in out.columns


def test_field_mapping_no_match_returns_input() -> None:
    df = pd.DataFrame({"x": [1]})
    out = apply_field_mapping(df, {"workload_code": "missing"})
    pd.testing.assert_frame_equal(out, df)


def test_strip_prefix() -> None:
    df = pd.DataFrame({"kpis.throughput": [10.0], "run_id": ["r1"]})
    out = strip_prefix(df, "kpis.")
    assert "throughput" in out.columns and "run_id" in out.columns


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def _good_row(**overrides) -> dict:
    base = {
        "source_record_key": "r1",
        "workload_code": "llama2-inference",
        "hardware_code": "nvidia-rtx-4090",
        "started_at": "2025-10-01T08:00:00Z",
        "run_status": "success",
    }
    base.update(overrides)
    return base


def test_validate_runs_passes_clean_rows() -> None:
    df = pd.DataFrame([_good_row(), _good_row(source_record_key="r2")])
    result = validate_runs(df)
    assert len(result.valid) == 2
    assert len(result.quarantine) == 0
    assert pd.api.types.is_datetime64_any_dtype(result.valid["started_at"])


def test_validate_runs_aliases_status() -> None:
    df = pd.DataFrame(
        [_good_row(run_status="FAILED"), _good_row(source_record_key="r2", run_status="OK")]
    )
    result = validate_runs(df)
    assert list(result.valid["run_status"]) == ["fail", "success"]


def test_validate_runs_quarantines_unknown_status() -> None:
    df = pd.DataFrame([_good_row(run_status="weird_state")])
    result = validate_runs(df)
    assert len(result.valid) == 0
    assert len(result.quarantine) == 1
    assert "unknown run_status" in result.quarantine["_quarantine_reason"].iloc[0]


def test_validate_runs_missing_required_column_quarantines_all() -> None:
    df = pd.DataFrame(
        [
            {
                "workload_code": "x",
                "hardware_code": "y",
                "started_at": "2025-01-01",
                "run_status": "success",
            }
        ]
    )
    # missing source_record_key
    result = validate_runs(df)
    assert len(result.valid) == 0
    assert len(result.quarantine) == 1
    assert "missing required columns" in result.quarantine["_quarantine_reason"].iloc[0]


def test_validate_runs_null_required_value_quarantines_row() -> None:
    df = pd.DataFrame([_good_row(hardware_code=None), _good_row(source_record_key="r2")])
    result = validate_runs(df)
    assert len(result.valid) == 1
    assert len(result.quarantine) == 1


# ---------------------------------------------------------------------------
# KPI normalization
# ---------------------------------------------------------------------------


def test_normalize_wide_to_long_basic() -> None:
    df = pd.DataFrame(
        [
            _good_row(throughput=100.0, gpu_util_pct=80.0, power_watts_avg=400.0),
            _good_row(source_record_key="r2", throughput=200.0),
        ]
    )
    df["started_at"] = pd.to_datetime(df["started_at"], utc=True)

    result = normalize(df)
    assert len(result.runs) == 2

    # r1 has 3 metrics, r2 has 1 -> total 4 KPI rows.
    assert len(result.kpis) == 4
    r1_kpis = result.kpis[result.kpis["source_record_key"] == "r1"]
    assert set(r1_kpis["kpi_code"]) == {"throughput", "gpu_util_pct", "power_watts_avg"}

    # Denormalized columns are populated where the KPI exists on the run.
    r1_throughput = r1_kpis[r1_kpis["kpi_code"] == "throughput"].iloc[0]
    assert r1_throughput["gpu_util_pct"] == 80.0
    assert r1_throughput["power_watts_avg"] == 400.0


def test_normalize_handles_nan_metric_cells() -> None:
    df = pd.DataFrame(
        [
            _good_row(throughput=float("nan"), gpu_util_pct=50.0),
        ]
    )
    df["started_at"] = pd.to_datetime(df["started_at"], utc=True)
    result = normalize(df)
    assert len(result.kpis) == 1
    assert result.kpis.iloc[0]["kpi_code"] == "gpu_util_pct"


def test_normalize_picks_up_unknown_kpi_via_dim_codes() -> None:
    df = pd.DataFrame([_good_row(custom_metric=42.0)])
    df["started_at"] = pd.to_datetime(df["started_at"], utc=True)
    result = normalize(df, known_kpi_codes={"custom_metric"})
    assert len(result.kpis) == 1
    assert result.kpis.iloc[0]["kpi_code"] == "custom_metric"


def test_normalize_empty_input() -> None:
    df = pd.DataFrame(columns=list(REQUIRED_RUN_COLUMNS) + ["throughput"])
    result = normalize(df)
    assert result.runs.empty and result.kpis.empty


# ---------------------------------------------------------------------------
# End-to-end transform
# ---------------------------------------------------------------------------


def test_transform_full_pipeline_csv_shape() -> None:
    df = pd.DataFrame(
        [
            {
                "run_id": "r1",
                "workload_code": "llama2-inference",
                "hardware_code": "nvidia-rtx-4090",
                "model_code": "llama-2-7b",
                "stack_code": "pytorch",
                "started_at": "2025-10-01T08:00:00Z",
                "ended_at": "2025-10-01T08:05:00Z",
                "duration_s": 300.0,
                "run_status": "success",
                "throughput": 128.4,
                "inference_time_ms": 12.5,
                "gpu_util_pct": 92.3,
            },
            {
                "run_id": "r2",
                "workload_code": "phi3-inference",
                "hardware_code": "nvidia-rtx-4090",
                "model_code": "phi-3-mini",
                "stack_code": "pytorch",
                "started_at": "2025-10-02T09:15:00Z",
                "ended_at": "2025-10-02T09:18:00Z",
                "duration_s": 180.0,
                "run_status": "success",
                "throughput": 210.5,
            },
        ]
    )
    source_config = {"mapping": {"source_record_key": "run_id"}}
    result: TransformResult = transform(df, source_config)
    assert len(result.runs) == 2
    # r1: throughput+inference_time_ms+gpu_util_pct = 3; r2: throughput = 1
    assert len(result.kpis) == 4
    assert "source_record_key" in result.runs.columns


def test_transform_jsonl_shape_with_kpis_prefix() -> None:
    df = pd.DataFrame(
        [
            {
                "run_id": "j1",
                "workload_code": "llama2-inference",
                "hardware_code": "nvidia-rtx-4090",
                "model_code": "llama-2-7b",
                "stack_code": "pytorch",
                "started_at": "2025-10-08T08:00:00Z",
                "run_status": "success",
                "kpis.throughput": 131.7,
                "kpis.tokens_per_sec": 2204.8,
            },
        ]
    )
    source_config = {"mapping": {"source_record_key": "run_id"}}
    result = transform(df, source_config)
    assert len(result.runs) == 1
    assert set(result.kpis["kpi_code"]) == {"throughput", "tokens_per_sec"}


def test_transform_empty_input() -> None:
    df = pd.DataFrame()
    result = transform(df, {})
    assert result.is_empty
