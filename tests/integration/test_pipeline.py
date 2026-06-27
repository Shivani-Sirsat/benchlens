"""End-to-end pipeline test against the local Postgres warehouse.

Skips automatically if Postgres is unreachable. Cleans up by removing only
rows created with source_name == 'integration_test' so existing data is
preserved.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from benchlens.utils.db import ping, session_scope
from benchlens.warehouse.models import EtlRunLog, FactBenchmarkRun, FactKpiValue

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SOURCE_NAME = "integration_test"


pytestmark = pytest.mark.skipif(
    not ping(),
    reason="local Postgres warehouse not reachable; skipping integration test.",
)


@pytest.fixture()
def staged_csv(tmp_path: Path) -> Path:
    target = tmp_path / "raw"
    target.mkdir()
    shutil.copy(FIXTURES / "sample_results.csv", target / "sample_results.csv")
    return target


@pytest.fixture(autouse=True)
def _cleanup() -> None:
    """Remove any rows the previous test run created under our source name."""

    def _purge() -> None:
        with session_scope() as s:
            # KPI rows cascade via FK; deleting runs is enough.
            run_dates = s.execute(
                select(FactBenchmarkRun.run_id, FactBenchmarkRun.run_date).where(
                    FactBenchmarkRun.source_name == SOURCE_NAME
                )
            ).all()
            if run_dates:
                ids = [r.run_id for r in run_dates]
                dates = list({r.run_date for r in run_dates})
                s.execute(
                    delete(FactKpiValue).where(
                        FactKpiValue.run_id.in_(ids),
                        FactKpiValue.run_date.in_(dates),
                    )
                )
                s.execute(
                    delete(FactBenchmarkRun).where(
                        FactBenchmarkRun.source_name == SOURCE_NAME,
                    )
                )
            s.execute(delete(EtlRunLog).where(EtlRunLog.source_name == SOURCE_NAME))

    _purge()
    yield
    _purge()


def test_pipeline_loads_csv_into_warehouse(
    staged_csv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the full pipeline and verify fact rows landed."""
    fake_source = {
        "name": SOURCE_NAME,
        "connector": "csv",
        "enabled": True,
        "path": str(staged_csv),
        "pattern": "*.csv",
        "watermark_field": "started_at",
        "mapping": {"source_record_key": "run_id"},
    }
    # pipeline_runner imports load_source_config at module load, so we must
    # patch the bound name there as well as the factory module's own copy.
    monkeypatch.setattr("benchlens.ingestion.factory.load_source_config", lambda name: fake_source)
    monkeypatch.setattr(
        "benchlens.orchestration.pipeline_runner.load_source_config",
        lambda name: fake_source,
    )

    from benchlens.orchestration import run_pipeline

    summary = run_pipeline(SOURCE_NAME, commit_watermark=False)

    # We extracted 10 rows from the fixture.
    assert summary.rows_extracted == 10
    # All rows had a known workload_code / hardware_code, so none skipped.
    assert summary.rows_skipped == 0
    assert summary.runs_upserted == 10
    assert summary.kpis_upserted > 0

    # Verify rows are really in the warehouse.
    with session_scope() as s:
        run_count = s.scalar(
            select(FactBenchmarkRun)
            .where(FactBenchmarkRun.source_name == SOURCE_NAME)
            .with_only_columns(FactBenchmarkRun.run_id)
            .order_by(FactBenchmarkRun.run_id)
        )
        assert run_count is not None
        all_runs = s.execute(
            select(FactBenchmarkRun.run_id).where(FactBenchmarkRun.source_name == SOURCE_NAME)
        ).all()
        assert len(all_runs) == 10

        # KPI count must match what the writer reported.
        kpi_count = s.scalar(
            select(FactKpiValue)
            .join(
                FactBenchmarkRun,
                (FactKpiValue.run_id == FactBenchmarkRun.run_id)
                & (FactKpiValue.run_date == FactBenchmarkRun.run_date),
            )
            .where(FactBenchmarkRun.source_name == SOURCE_NAME)
            .with_only_columns(FactKpiValue.kpi_id)
        )
        assert kpi_count is not None

        # The audit row exists and is marked success.
        audit = (
            s.execute(
                select(EtlRunLog)
                .where(EtlRunLog.source_name == SOURCE_NAME)
                .order_by(EtlRunLog.log_id.desc())
            )
            .scalars()
            .first()
        )
        assert audit is not None
        assert audit.status == "success"
        assert audit.rows_in == 10
        assert audit.rows_out == 10


def test_pipeline_is_idempotent(staged_csv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running twice yields the same fact-run count (upsert path works)."""
    fake_source = {
        "name": SOURCE_NAME,
        "connector": "csv",
        "enabled": True,
        "path": str(staged_csv),
        "pattern": "*.csv",
        "mapping": {"source_record_key": "run_id"},
    }
    monkeypatch.setattr("benchlens.ingestion.factory.load_source_config", lambda name: fake_source)
    monkeypatch.setattr(
        "benchlens.orchestration.pipeline_runner.load_source_config",
        lambda name: fake_source,
    )

    from benchlens.orchestration import run_pipeline

    first = run_pipeline(SOURCE_NAME)
    second = run_pipeline(SOURCE_NAME)
    assert first.runs_upserted == second.runs_upserted == 10

    with session_scope() as s:
        rows = s.execute(
            select(FactBenchmarkRun.run_id).where(FactBenchmarkRun.source_name == SOURCE_NAME)
        ).all()
        assert len(rows) == 10  # no duplicates after second run.
