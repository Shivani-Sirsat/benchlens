-- ============================================================================
-- Migration 002: data quality + regression detection
-- ----------------------------------------------------------------------------
-- Adds `quality_check_result` to persist DQ rule outcomes (range/freshness/
-- regression). Only failed checks are persisted; pass counts can be derived
-- later from `etl_run_log.extra` if needed.
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_check_result (
    check_id          BIGSERIAL    PRIMARY KEY,
    log_id            BIGINT       REFERENCES etl_run_log(log_id) ON DELETE SET NULL,
    rule_id           VARCHAR(100) NOT NULL,
    rule_type         VARCHAR(50)  NOT NULL,
    severity          VARCHAR(20)  NOT NULL,
    status            VARCHAR(20)  NOT NULL,
    source_name       VARCHAR(100),
    source_record_key VARCHAR(200),
    workload_code     VARCHAR(50),
    hardware_code     VARCHAR(100),
    kpi_code          VARCHAR(50),
    observed_value    NUMERIC(20, 6),
    expected_min      NUMERIC(20, 6),
    expected_max      NUMERIC(20, 6),
    baseline_value    NUMERIC(20, 6),
    deviation_pct     NUMERIC(10, 3),
    message           TEXT,
    detected_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    extra             JSONB,
    CONSTRAINT quality_check_result_status_check
        CHECK (status IN ('pass','fail')),
    CONSTRAINT quality_check_result_severity_check
        CHECK (severity IN ('info','warning','error','critical'))
);

CREATE INDEX IF NOT EXISTS idx_qcr_log         ON quality_check_result(log_id);
CREATE INDEX IF NOT EXISTS idx_qcr_rule        ON quality_check_result(rule_id);
CREATE INDEX IF NOT EXISTS idx_qcr_status      ON quality_check_result(status);
CREATE INDEX IF NOT EXISTS idx_qcr_kpi_code    ON quality_check_result(kpi_code);
CREATE INDEX IF NOT EXISTS idx_qcr_workload    ON quality_check_result(workload_code);
CREATE INDEX IF NOT EXISTS idx_qcr_detected_at ON quality_check_result(detected_at DESC);

INSERT INTO schema_version (version, description)
VALUES (2, 'Quality check results table')
ON CONFLICT (version) DO NOTHING;
