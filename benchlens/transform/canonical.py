"""Canonical column names + KPI vocabulary used across the transform/load layer."""

from __future__ import annotations

# Required columns for a valid benchmark run row.
REQUIRED_RUN_COLUMNS: tuple[str, ...] = (
    "source_record_key",
    "workload_code",
    "hardware_code",
    "started_at",
    "run_status",
)

# Optional run-level columns kept on fact_benchmark_run when present.
OPTIONAL_RUN_COLUMNS: tuple[str, ...] = (
    "stack_code",
    "model_code",
    "ended_at",
    "duration_s",
    "error_message",
    "notes",
)

# Source status -> warehouse status. Warehouse only allows success|fail|timeout|aborted.
STATUS_ALIAS: dict[str, str] = {
    "success": "success",
    "successful": "success",
    "ok": "success",
    "pass": "success",
    "passed": "success",
    "fail": "fail",
    "failed": "fail",
    "error": "fail",
    "timeout": "timeout",
    "timed_out": "timeout",
    "abort": "aborted",
    "aborted": "aborted",
    "cancelled": "aborted",
    "canceled": "aborted",
}

# Source-column-name -> canonical KPI code (dim_kpi.code).
# Anything else that matches a dim_kpi.code directly is also picked up.
COLUMN_TO_KPI: dict[str, str] = {
    "throughput": "throughput",
    "tokens_per_sec": "tokens_per_sec",
    "tokens_per_second": "tokens_per_sec",
    "inference_time_ms": "inference_time_ms",
    "latency_p50_ms": "latency_p50",
    "latency_p95_ms": "latency_p95",
    "latency_p99_ms": "latency_p99",
    "latency_p50": "latency_p50",
    "latency_p95": "latency_p95",
    "latency_p99": "latency_p99",
    "gpu_util_pct": "gpu_util_pct",
    "cpu_util_pct": "cpu_util_pct",
    "npu_util_pct": "npu_util_pct",
    "memory_util_pct": "memory_util_pct",
    "power_watts_avg": "power_watts_avg",
    "energy_kwh": "energy_kwh",
    "perf_per_watt": "perf_per_watt",
    "accuracy_score": "accuracy_score",
    "success_rate": "success_rate",
}

# These KPIs are denormalized as columns on fact_kpi_value for fast filters.
# Map: canonical KPI code -> fact_kpi_value column name.
DENORM_KPI_COLUMNS: dict[str, str] = {
    "inference_time_ms": "inference_time_ms",
    "power_watts_avg": "power_watts_avg",
    "energy_kwh": "energy_kwh",
    "gpu_util_pct": "gpu_util_pct",
    "cpu_util_pct": "cpu_util_pct",
    "npu_util_pct": "npu_util_pct",
    "memory_util_pct": "memory_util_pct",
}
