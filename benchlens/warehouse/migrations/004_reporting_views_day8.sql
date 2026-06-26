-- ============================================================================
-- Migration 004: reporting views for Day 8 dashboards
--   - vw_model_perf_pivot          (Model Comparison)
--   - vw_model_comparison_matrix   (Model Comparison)
--   - vw_run_reliability           (Regression Reliability)
--   - vw_regression_trend_daily    (Regression Reliability)
--   - vw_regression_detection_lag  (Regression Reliability)
-- All views are non-materialized; refresh is idempotent (CREATE OR REPLACE).
-- ============================================================================

-- ---------- vw_model_perf_pivot --------------------------------------------
-- One row per (model x workload x hardware x KPI). Adds parameter-normalized
-- throughput so dashboards can compare models of different sizes fairly.
CREATE OR REPLACE VIEW vw_model_perf_pivot AS
SELECT
    m.model_id,
    m.code   AS model_code,
    m.name   AS model_name,
    m.family AS model_family,
    m.parameter_count,
    m.quantization,
    m.context_length,
    w.code AS workload_code,
    w.category AS workload_category,
    h.code AS hardware_code,
    h.accelerator_type,
    h.vendor AS hardware_vendor,
    h.sku    AS hardware_sku,
    h.tdp_watts,
    h.price_usd::double precision AS hardware_price_usd,
    k.code      AS kpi_code,
    k.name      AS kpi_name,
    k.category  AS kpi_category,
    k.unit      AS kpi_unit,
    k.direction AS kpi_direction,
    COUNT(*)                              AS run_count,
    AVG(v.value)::double precision        AS kpi_value_avg,
    MIN(v.value)::double precision        AS kpi_value_min,
    MAX(v.value)::double precision        AS kpi_value_max,
    -- Parameter-normalized throughput: meaningful only for throughput-like KPIs
    CASE
        WHEN k.code IN ('throughput','tokens_per_sec','images_per_sec')
         AND m.parameter_count IS NOT NULL AND m.parameter_count > 0
        THEN AVG(v.value)::double precision / (m.parameter_count / 1e6::double precision)
    END AS throughput_per_million_params
FROM fact_kpi_value v
JOIN fact_benchmark_run f ON f.run_id = v.run_id AND f.run_date = v.run_date
JOIN dim_workload w ON w.workload_id = f.workload_id
JOIN dim_hardware h ON h.hardware_id = f.hardware_id
JOIN dim_kpi      k ON k.kpi_id     = v.kpi_id
JOIN dim_model    m ON m.model_id   = f.model_id    -- inner join: model required
WHERE f.run_status = 'success'
GROUP BY
    m.model_id, m.code, m.name, m.family, m.parameter_count, m.quantization, m.context_length,
    w.code, w.category, h.code, h.accelerator_type, h.vendor, h.sku, h.tdp_watts, h.price_usd,
    k.code, k.name, k.category, k.unit, k.direction;

COMMENT ON VIEW vw_model_perf_pivot IS
    'Per (model, workload, hardware, KPI) aggregate + parameter-normalized throughput.';


-- ---------- vw_model_comparison_matrix ------------------------------------
-- One row per model (across all workloads/hardware). Headline metrics for the
-- model-comparison matrix visual. Uses FILTER aggregates on the run-level
-- pivot to assemble representative per-model averages.
CREATE OR REPLACE VIEW vw_model_comparison_matrix AS
WITH per_run AS (
    SELECT
        f.run_id,
        f.run_date,
        f.model_id,
        h.tdp_watts::double precision AS tdp_watts,
        h.price_usd::double precision AS price_usd,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'throughput')        AS throughput,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'tokens_per_sec')    AS tokens_per_sec,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'images_per_sec')    AS images_per_sec,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'inference_time_ms') AS inference_time_ms,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'latency_p95')       AS latency_p95_ms,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'power_watts_avg')   AS power_watts_avg,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'gpu_util_pct')      AS gpu_util_pct,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'accuracy')          AS accuracy,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'energy_kwh')        AS energy_kwh
    FROM fact_benchmark_run f
    JOIN fact_kpi_value v ON v.run_id = f.run_id AND v.run_date = f.run_date
    JOIN dim_kpi      k   ON k.kpi_id = v.kpi_id
    JOIN dim_hardware h   ON h.hardware_id = f.hardware_id
    WHERE f.run_status = 'success' AND f.model_id IS NOT NULL
    GROUP BY f.run_id, f.run_date, f.model_id, h.tdp_watts, h.price_usd
)
SELECT
    m.model_id,
    m.code   AS model_code,
    m.name   AS model_name,
    m.family AS model_family,
    m.parameter_count,
    m.quantization,
    m.context_length,
    COUNT(per_run.run_id)                                        AS run_count,
    AVG(COALESCE(per_run.throughput, per_run.tokens_per_sec,
                 per_run.images_per_sec))                        AS avg_throughput,
    AVG(per_run.inference_time_ms)                               AS avg_latency_ms,
    AVG(per_run.latency_p95_ms)                                  AS avg_latency_p95_ms,
    AVG(per_run.power_watts_avg)                                 AS avg_power_watts,
    AVG(per_run.gpu_util_pct)                                    AS avg_gpu_util_pct,
    AVG(per_run.accuracy)                                        AS avg_accuracy,
    SUM(per_run.energy_kwh)                                      AS total_energy_kwh,
    -- Per-watt: average throughput divided by average power (or TDP fallback)
    AVG(COALESCE(per_run.throughput, per_run.tokens_per_sec, per_run.images_per_sec))
        / NULLIF(AVG(COALESCE(per_run.power_watts_avg, per_run.tdp_watts)), 0)
        AS avg_throughput_per_watt,
    -- Param-normalized throughput in tokens-per-sec per million parameters
    CASE
        WHEN m.parameter_count IS NOT NULL AND m.parameter_count > 0
        THEN AVG(COALESCE(per_run.throughput, per_run.tokens_per_sec, per_run.images_per_sec))
             / (m.parameter_count / 1e6::double precision)
    END AS throughput_per_million_params,
    -- Cost-normalized: per $1k of hardware
    1000.0 * AVG(COALESCE(per_run.throughput, per_run.tokens_per_sec, per_run.images_per_sec))
        / NULLIF(AVG(per_run.price_usd), 0)
        AS throughput_per_kdollar,
    MAX(per_run.run_date) AS last_run_date
FROM per_run
JOIN dim_model m ON m.model_id = per_run.model_id
GROUP BY m.model_id, m.code, m.name, m.family, m.parameter_count,
         m.quantization, m.context_length;

COMMENT ON VIEW vw_model_comparison_matrix IS
    'One row per model: avg throughput / latency / perf-per-watt / per-$1k / per-Mparam.';


-- ---------- vw_run_reliability --------------------------------------------
-- Per (workload, hardware) cohort reliability stats. Drives the reliability
-- matrix and powers DAX MTBF measures.
CREATE OR REPLACE VIEW vw_run_reliability AS
SELECT
    w.code AS workload_code,
    w.category AS workload_category,
    h.code AS hardware_code,
    h.accelerator_type,
    h.vendor AS hardware_vendor,
    h.sku    AS hardware_sku,
    COUNT(*)                                                                 AS total_runs,
    COUNT(*) FILTER (WHERE f.run_status = 'success')                         AS success_runs,
    COUNT(*) FILTER (WHERE f.run_status IN ('fail','timeout','aborted'))     AS failure_runs,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE f.run_status = 'success')
              / NULLIF(COUNT(*), 0),
        2
    )::double precision                                                      AS success_pct,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE f.run_status IN ('fail','timeout','aborted'))
              / NULLIF(COUNT(*), 0),
        2
    )::double precision                                                      AS failure_pct,
    MIN(f.started_at)                                                        AS first_run_at,
    MAX(f.started_at)                                                        AS last_run_at,
    MAX(f.started_at) FILTER (WHERE f.run_status IN ('fail','timeout','aborted'))
                                                                             AS last_failure_at,
    -- Mean time between failures (hours): observation window / # failures
    CASE
        WHEN COUNT(*) FILTER (WHERE f.run_status IN ('fail','timeout','aborted')) > 1
        THEN EXTRACT(EPOCH FROM (MAX(f.started_at) - MIN(f.started_at))) / 3600.0
             / NULLIF(COUNT(*) FILTER (WHERE f.run_status IN ('fail','timeout','aborted')) - 1, 0)
    END                                                                      AS mtbf_hours
FROM fact_benchmark_run f
JOIN dim_workload w ON w.workload_id = f.workload_id
JOIN dim_hardware h ON h.hardware_id = f.hardware_id
GROUP BY w.code, w.category, h.code, h.accelerator_type, h.vendor, h.sku;

COMMENT ON VIEW vw_run_reliability IS
    'Per (workload, hardware) cohort: success/failure counts, success%, MTBF (h).';


-- ---------- vw_regression_trend_daily -------------------------------------
-- Daily roll-up of DQ findings by (severity, rule_type, workload, kpi).
-- Drives the regression-trend line chart.
CREATE OR REPLACE VIEW vw_regression_trend_daily AS
SELECT
    q.detected_at::date AS detected_date,
    q.severity,
    q.rule_type,
    q.workload_code,
    q.hardware_code,
    q.kpi_code,
    COUNT(*) AS finding_count,
    AVG(q.deviation_pct)::double precision AS avg_deviation_pct,
    MAX(ABS(q.deviation_pct))::double precision AS max_abs_deviation_pct
FROM quality_check_result q
GROUP BY
    q.detected_at::date, q.severity, q.rule_type,
    q.workload_code, q.hardware_code, q.kpi_code;

COMMENT ON VIEW vw_regression_trend_daily IS
    'Daily DQ-finding counts + avg/max deviation per cohort.';


-- ---------- vw_regression_detection_lag -----------------------------------
-- Per finding: how long after the run completed was the regression detected?
-- LEFT JOIN to fact_benchmark_run via (source_name, source_record_key) when
-- the finding carries those identifiers; otherwise lag is NULL.
CREATE OR REPLACE VIEW vw_regression_detection_lag AS
SELECT
    q.check_id,
    q.detected_at,
    q.detected_at::date AS detected_date,
    q.rule_id,
    q.rule_type,
    q.severity,
    q.workload_code,
    q.hardware_code,
    q.kpi_code,
    q.deviation_pct::double precision AS deviation_pct,
    f.run_id,
    f.started_at AS run_started_at,
    EXTRACT(EPOCH FROM (q.detected_at - f.started_at)) / 60.0 AS detection_lag_minutes
FROM quality_check_result q
LEFT JOIN fact_benchmark_run f
       ON f.source_name        = q.source_name
      AND f.source_record_key  = q.source_record_key
WHERE q.source_name IS NOT NULL AND q.source_record_key IS NOT NULL;

COMMENT ON VIEW vw_regression_detection_lag IS
    'Per finding: minutes between run start and DQ detection (NULL if not joinable).';


-- ============================================================================
INSERT INTO schema_version (version, description)
VALUES (4, 'Reporting views for Day 8 dashboards (model comparison + reliability)')
ON CONFLICT (version) DO NOTHING;
