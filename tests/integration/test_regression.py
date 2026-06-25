"""Integration test for DQ + regression detection through the full pipeline.

We stage two CSV files for the same source:
  - baseline: 5 runs of the same workload/hardware/model/stack at high throughput
  - regression: 1 run of the same cohort at low throughput (≈50% drop)

After both pipeline runs the warehouse should contain:
  - 6 fact_benchmark_run rows
  - several fact_kpi_value rows
  - >=1 quality_check_result row of rule_type='regression'

Skips automatically if Postgres is unreachable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from benchlens.utils.db import ping, session_scope
from benchlens.warehouse.models import (
    EtlRunLog,
    FactBenchmarkRun,
    FactKpiValue,
    QualityCheckResult,
)

SOURCE_NAME = "dq_regression_test"

pytestmark = pytest.mark.skipif(
    not ping(),
    reason="local Postgres warehouse not reachable; skipping DQ integration test.",
)


def _make_csv(path: Path, *, run_id_prefix: str, base_time: datetime, throughputs: list[float]) -> Path:
    """Write a CSV with one row per throughput value, all on the same cohort."""
    headers = [
        "run_id", "workload_code", "hardware_code", "model_code", "stack_code",
        "started_at", "duration_s", "run_status", "throughput",
        "tokens_per_sec", "gpu_util_pct",
    ]
    lines = [",".join(headers)]
    for i, tput in enumerate(throughputs):
        started = base_time + timedelta(hours=i)
        lines.append(
            ",".join([
                f"{run_id_prefix}-{i:02d}",
                "llama-inference-7b",
                "gpu-nv-rtx4090",
                "llama3-8b-fp16",
                "pytorch-2.5-cuda12",
                started.isoformat(),
                "12.5",
                "success",
                f"{tput}",
                f"{tput * 2.5}",
                "92.0",
            ])
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _cleanup() -> None:
    """Remove rows from any prior run so the test is deterministic."""
    def _purge() -> None:
        with session_scope() as s:
            s.execute(
                delete(QualityCheckResult).where(QualityCheckResult.source_name == SOURCE_NAME)
            )
            runs = s.execute(
                select(FactBenchmarkRun.run_id, FactBenchmarkRun.run_date)
                .where(FactBenchmarkRun.source_name == SOURCE_NAME)
            ).all()
            if runs:
                ids = [r.run_id for r in runs]
                dates = list({r.run_date for r in runs})
                s.execute(
                    delete(FactKpiValue).where(
                        FactKpiValue.run_id.in_(ids),
                        FactKpiValue.run_date.in_(dates),
                    )
                )
                s.execute(
                    delete(FactBenchmarkRun).where(
                        FactBenchmarkRun.source_name == SOURCE_NAME
                    )
                )
            s.execute(
                delete(EtlRunLog).where(EtlRunLog.source_name == SOURCE_NAME)
            )
    _purge()
    yield
    _purge()


def _stage_source(monkeypatch: pytest.MonkeyPatch, dir_path: Path) -> None:
    fake_source = {
        "name": SOURCE_NAME,
        "connector": "csv",
        "enabled": True,
        "path": str(dir_path),
        "pattern": "*.csv",
        "watermark_field": "started_at",
        "mapping": {"source_record_key": "run_id"},
    }
    monkeypatch.setattr(
        "benchlens.ingestion.factory.load_source_config", lambda name: fake_source
    )
    monkeypatch.setattr(
        "benchlens.orchestration.pipeline_runner.load_source_config",
        lambda name: fake_source,
    )


def test_regression_is_detected_persisted_and_alerted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: bad data after a clean baseline produces a persisted finding."""
    from benchlens.alerts import AlertManager
    from benchlens.alerts.base_sink import AlertSink
    from benchlens.orchestration import run_pipeline
    from benchlens.quality.validators import Finding

    # 1. Stage and run a CLEAN baseline batch.
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    base_time = datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc)
    _make_csv(
        baseline_dir / "baseline.csv",
        run_id_prefix="bl",
        base_time=base_time,
        throughputs=[100.0, 102.0, 98.0, 101.0, 99.0],  # mean ≈ 100
    )
    _stage_source(monkeypatch, baseline_dir)

    captured: list[Finding] = []

    class CaptureSink(AlertSink):
        name = "capture"
        def emit(self, finding: Finding) -> None:
            captured.append(finding)

    capture_mgr = AlertManager(sinks=[CaptureSink()])
    summary_baseline = run_pipeline(SOURCE_NAME, alert_manager=capture_mgr)
    assert summary_baseline.runs_upserted == 5
    # No regression possible on the very first batch.
    regression_findings = [f for f in captured if f.rule_type == "regression"]
    assert regression_findings == []

    # 2. Stage and run the REGRESSED batch — throughput cut in half.
    regressed_dir = tmp_path / "regressed"
    regressed_dir.mkdir()
    bad_time = base_time + timedelta(days=1)
    _make_csv(
        regressed_dir / "regressed.csv",
        run_id_prefix="rg",
        base_time=bad_time,
        throughputs=[40.0],  # ~60% drop from baseline mean of ~100
    )
    _stage_source(monkeypatch, regressed_dir)

    captured.clear()
    summary_regressed = run_pipeline(SOURCE_NAME, alert_manager=capture_mgr)
    assert summary_regressed.runs_upserted == 1

    # 3. Regression should have been flagged.
    rule_ids = {f.rule_id for f in captured if f.rule_type == "regression"}
    assert "throughput_regression" in rule_ids, (
        f"Expected throughput_regression in {rule_ids}; all findings={captured}"
    )

    # 4. Finding must be persisted to quality_check_result.
    with session_scope() as s:
        persisted = s.execute(
            select(QualityCheckResult)
            .where(
                QualityCheckResult.source_name == SOURCE_NAME,
                QualityCheckResult.rule_type == "regression",
                QualityCheckResult.rule_id == "throughput_regression",
            )
        ).scalars().all()
        assert len(persisted) >= 1
        f = persisted[0]
        assert f.kpi_code == "throughput"
        assert f.observed_value is not None
        assert float(f.observed_value) == pytest.approx(40.0, rel=1e-3)
        assert f.baseline_value is not None
        assert float(f.baseline_value) == pytest.approx(100.0, abs=2.0)
        assert f.deviation_pct is not None and float(f.deviation_pct) <= -15.0
        # Linked back to the etl_run_log row.
        assert f.log_id is not None
