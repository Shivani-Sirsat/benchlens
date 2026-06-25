"""End-to-end pipeline: extract -> transform -> load -> data quality -> audit."""

from __future__ import annotations

from dataclasses import dataclass, field

from benchlens.alerts import AlertManager, ConsoleSink, FileSink
from benchlens.ingestion import build_connector_by_name, load_source_config
from benchlens.load import EtlAudit, LoadResult, WarehouseWriter
from benchlens.load.dim_resolver import DimensionResolver
from benchlens.quality import DQResult, DQRunner, load_rules
from benchlens.transform import TransformResult, transform
from benchlens.utils.db import session_scope
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class PipelineSummary:
    source: str
    log_id: int | None
    rows_extracted: int
    rows_quarantined: int
    runs_upserted: int
    kpis_upserted: int
    rows_skipped: int
    new_watermark: object | None
    dq_findings: int = 0
    dq_by_severity: dict[str, int] = field(default_factory=dict)
    dq_rules_evaluated: int = 0

    def as_table_rows(self) -> list[tuple[str, str]]:
        return [
            ("Source", self.source),
            ("Audit log_id", str(self.log_id)),
            ("Rows extracted", str(self.rows_extracted)),
            ("Rows quarantined", str(self.rows_quarantined)),
            ("Rows skipped (unknown dims)", str(self.rows_skipped)),
            ("Runs upserted", str(self.runs_upserted)),
            ("KPI values upserted", str(self.kpis_upserted)),
            ("DQ rules evaluated", str(self.dq_rules_evaluated)),
            ("DQ findings", str(self.dq_findings)),
            ("DQ by severity", str(self.dq_by_severity or {})),
            ("New watermark", str(self.new_watermark)),
        ]


def run_pipeline(
    source_name: str,
    *,
    commit_watermark: bool = False,
    run_quality: bool = True,
    alert_manager: AlertManager | None = None,
) -> PipelineSummary:
    """Run the full ETL pipeline for a single configured source."""
    source_config = load_source_config(source_name)
    connector = build_connector_by_name(source_name)

    log.info("[%s] pipeline starting (connector=%s).", source_name, connector.kind)
    ingest_result = connector.run()
    log.info("[%s] extracted %d rows.", source_name, ingest_result.rows)

    with session_scope() as session:
        resolver = DimensionResolver(session)
        known_kpi_codes = resolver.cache().kpi_codes()

        with EtlAudit(session, source_name, "pipeline") as audit:
            audit.rows_in = ingest_result.rows

            transform_result: TransformResult = transform(
                ingest_result.records,
                source_config=source_config,
                known_kpi_codes=known_kpi_codes,
            )
            audit.rows_quarantined = len(transform_result.quarantine)

            writer = WarehouseWriter(session, source_name)
            load_result: LoadResult = writer.write(transform_result)

            audit.rows_out = load_result.runs_upserted
            audit.extra.update({
                "connector": connector.kind,
                "kpis_upserted": load_result.kpis_upserted,
                "rows_skipped": load_result.rows_skipped,
                "skipped_reasons": load_result.skipped_reasons[:20],
            })

            dq_result = DQResult(rules_evaluated=0)
            if run_quality and load_result.run_ids:
                manager = alert_manager or _default_alert_manager()
                runner = DQRunner(
                    session,
                    alert_manager=manager,
                    log_id=audit.log_id,
                    source_name=source_name,
                )
                dq_result = runner.run(load_result.run_ids)
                audit.extra.update({
                    "dq_findings": dq_result.fail_count,
                    "dq_by_severity": dq_result.by_severity,
                    "dq_rules_evaluated": dq_result.rules_evaluated,
                })

            summary = PipelineSummary(
                source=source_name,
                log_id=audit.log_id,
                rows_extracted=ingest_result.rows,
                rows_quarantined=len(transform_result.quarantine),
                runs_upserted=load_result.runs_upserted,
                kpis_upserted=load_result.kpis_upserted,
                rows_skipped=load_result.rows_skipped,
                new_watermark=ingest_result.new_watermark,
                dq_findings=dq_result.fail_count,
                dq_by_severity=dq_result.by_severity,
                dq_rules_evaluated=dq_result.rules_evaluated,
            )

    # Outside the transaction: persist the watermark so a future re-run is
    # incremental. Only do this if the pipeline succeeded (we got here).
    if commit_watermark and ingest_result.new_watermark is not None:
        connector.commit_watermark(ingest_result.new_watermark)
        log.info("[%s] watermark committed: %r", source_name, ingest_result.new_watermark)

    return summary


def _default_alert_manager() -> AlertManager:
    """Console + JSONL file sinks. Override by passing your own AlertManager."""
    return AlertManager(sinks=[ConsoleSink(), FileSink()])

