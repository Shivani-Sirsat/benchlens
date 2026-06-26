-- ============================================================================
-- Migration 003: reporting views (Power BI semantic layer)
-- ----------------------------------------------------------------------------
-- These views are the supported public surface for BI tools. They denormalize
-- the star schema so dashboards can be authored without writing joins, and
-- expose pre-computed efficiency metrics (perf-per-watt, perf-per-dollar) that
-- would otherwise require fragile DAX. All numeric ratios are cast to
-- double precision so Power BI maps them to a single Decimal Number type.
--
-- Views (not materialized) — Power BI Import mode caches the full result set
-- at refresh time, so MATERIALIZED VIEWS would only add operational overhead.
--
-- Re-running this migration is safe: every view uses CREATE OR REPLACE VIEW.
-- ============================================================================

-- ---------- vw_run_kpi_flat -----------------------------------------------
-- One row per (benchmark run, KPI). Denormalized fact for ad-hoc slicing.
CREATE OR REPLACE VIEW vw_run_kpi_flat AS
SELECT
    f.run_id,
    f.run_uuid,
    f.run_date,
    f.started_at,
    f.run_status,
    f.duration_s,
    f.source_name,
    f.source_record_key,
    -- workload attributes
    w.workload_id,
    w.code      AS workload_code,
    w.name      AS workload_name,
    w.category  AS workload_category,
    w.version   AS workload_version,
    -- hardware attributes
    h.hardware_id,
    h.code             AS hardware_code,
    h.accelerator_type,
    h.vendor           AS hardware_vendor,
    h.sku              AS hardware_sku,
    h.cores            AS hardware_cores,
    h.memory_gb        AS hardware_memory_gb,
    h.tdp_watts        AS hardware_tdp_watts,
    h.price_usd        AS hardware_price_usd,
    h.release_year     AS hardware_release_year,
    -- stack attributes (nullable)
    s.stack_id,
    s.code      AS stack_code,
    s.name      AS stack_name,
    s.framework AS stack_framework,
    s.version   AS stack_version,
    -- model attributes (nullable)
    m.model_id,
    m.code            AS model_code,
    m.name            AS model_name,
    m.family          AS model_family,
    m.parameter_count AS model_parameter_count,
    m.quantization    AS model_quantization,
    -- KPI attributes
    k.kpi_id,
    k.code      AS kpi_code,
    k.name      AS kpi_name,
    k.category  AS kpi_category,
    k.unit      AS kpi_unit,
    k.direction AS kpi_direction,
    -- KPI measurement
    v.value::double precision           AS kpi_value,
    v.inference_time_ms::double precision AS inference_time_ms,
    v.power_watts_avg::double precision  AS power_watts_avg,
    v.energy_kwh::double precision       AS energy_kwh,
    v.gpu_util_pct::double precision     AS gpu_util_pct,
    v.cpu_util_pct::double precision     AS cpu_util_pct,
    v.npu_util_pct::double precision     AS npu_util_pct,
    v.memory_util_pct::double precision  AS memory_util_pct,
    -- date attributes for time intelligence
    d.full_date,
    d.year,
    d.quarter,
    d.month,
    d.month_name,
    d.week,
    d.day_name,
    d.is_weekend
FROM fact_kpi_value v
JOIN fact_benchmark_run f
       ON f.run_id = v.run_id AND f.run_date = v.run_date
JOIN dim_workload w ON w.workload_id = f.workload_id
JOIN dim_hardware h ON h.hardware_id = f.hardware_id
LEFT JOIN dim_stack s ON s.stack_id  = f.stack_id
LEFT JOIN dim_model m ON m.model_id  = f.model_id
JOIN dim_kpi k       ON k.kpi_id     = v.kpi_id
JOIN dim_date d      ON d.date_id    = f.date_id;

COMMENT ON VIEW vw_run_kpi_flat IS
    'Fully denormalized fact: one row per (benchmark run, KPI). Primary source for Power BI.';


-- ---------- vw_run_summary ------------------------------------------------
-- One row per run with the most representative performance KPI surfaced.
-- "Primary" KPI is the first performance KPI present for the run, ordered by
-- a preference list (throughput > tokens_per_sec > images_per_sec > inference_time_ms).
CREATE OR REPLACE VIEW vw_run_summary AS
WITH ranked AS (
    SELECT
        v.run_id,
        v.run_date,
        v.kpi_id,
        v.value,
        ROW_NUMBER() OVER (
            PARTITION BY v.run_id, v.run_date
            ORDER BY CASE k.code
                WHEN 'throughput'        THEN 1
                WHEN 'tokens_per_sec'    THEN 2
                WHEN 'images_per_sec'    THEN 3
                WHEN 'queries_per_sec'   THEN 4
                WHEN 'inference_time_ms' THEN 5
                WHEN 'latency_p95'       THEN 6
                ELSE 99
            END,
            k.kpi_id
        ) AS rk
    FROM fact_kpi_value v
    JOIN dim_kpi k ON k.kpi_id = v.kpi_id
    WHERE k.category = 'performance'
)
SELECT
    f.run_id,
    f.run_uuid,
    f.run_date,
    f.started_at,
    f.run_status,
    f.duration_s::double precision  AS duration_s,
    f.source_name,
    w.code AS workload_code,
    w.name AS workload_name,
    w.category AS workload_category,
    h.code AS hardware_code,
    h.accelerator_type,
    h.vendor AS hardware_vendor,
    h.sku    AS hardware_sku,
    h.tdp_watts,
    h.price_usd,
    s.code AS stack_code,
    s.framework AS stack_framework,
    m.code AS model_code,
    m.family AS model_family,
    k.code      AS primary_kpi_code,
    k.name      AS primary_kpi_name,
    k.unit      AS primary_kpi_unit,
    k.direction AS primary_kpi_direction,
    r.value::double precision AS primary_kpi_value
FROM fact_benchmark_run f
JOIN dim_workload w  ON w.workload_id = f.workload_id
JOIN dim_hardware h  ON h.hardware_id = f.hardware_id
LEFT JOIN dim_stack s ON s.stack_id   = f.stack_id
LEFT JOIN dim_model m ON m.model_id   = f.model_id
LEFT JOIN ranked r
       ON r.run_id = f.run_id AND r.run_date = f.run_date AND r.rk = 1
LEFT JOIN dim_kpi k ON k.kpi_id = r.kpi_id;

COMMENT ON VIEW vw_run_summary IS
    'One row per run with the headline performance KPI value (preference-ordered).';


-- ---------- vw_hardware_efficiency ----------------------------------------
-- One row per run. Pivots key metrics so Power BI can plot perf-per-watt and
-- perf-per-dollar without DAX gymnastics. Ratios are NULL when denominator is
-- 0 or NULL (NULLIF guards against divide-by-zero).
CREATE OR REPLACE VIEW vw_hardware_efficiency AS
WITH agg AS (
    SELECT
        v.run_id,
        v.run_date,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'throughput')        AS throughput,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'tokens_per_sec')    AS tokens_per_sec,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'images_per_sec')    AS images_per_sec,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'inference_time_ms') AS inference_time_ms,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'latency_p95')       AS latency_p95_ms,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'power_watts_avg')   AS power_watts_avg,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'gpu_util_pct')      AS gpu_util_pct,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'memory_util_pct')   AS memory_util_pct,
        MAX(v.value::double precision) FILTER (WHERE k.code = 'energy_kwh')        AS energy_kwh
    FROM fact_kpi_value v
    JOIN dim_kpi k ON k.kpi_id = v.kpi_id
    GROUP BY v.run_id, v.run_date
)
SELECT
    f.run_id,
    f.run_date,
    f.run_status,
    f.source_name,
    h.hardware_id,
    h.code AS hardware_code,
    h.accelerator_type,
    h.vendor AS hardware_vendor,
    h.sku    AS hardware_sku,
    h.tdp_watts,
    h.price_usd::double precision AS price_usd,
    h.release_year,
    w.code AS workload_code,
    w.category AS workload_category,
    -- Primary throughput metric (prefer throughput, fall back to tokens/images)
    COALESCE(agg.throughput, agg.tokens_per_sec, agg.images_per_sec) AS primary_throughput,
    agg.throughput,
    agg.tokens_per_sec,
    agg.images_per_sec,
    agg.inference_time_ms,
    agg.latency_p95_ms,
    agg.power_watts_avg,
    agg.gpu_util_pct,
    agg.memory_util_pct,
    agg.energy_kwh,
    -- Derived efficiency: throughput per watt of measured power (or TDP fallback)
    COALESCE(agg.throughput, agg.tokens_per_sec, agg.images_per_sec)
        / NULLIF(COALESCE(agg.power_watts_avg, h.tdp_watts::double precision), 0)
        AS throughput_per_watt,
    -- Throughput per $1000 of hardware cost — readable scale for cards
    1000.0 * COALESCE(agg.throughput, agg.tokens_per_sec, agg.images_per_sec)
        / NULLIF(h.price_usd::double precision, 0)
        AS throughput_per_kdollar,
    -- Latency-adjusted efficiency: 1000 / inference_time_ms × per-watt
    (1000.0 / NULLIF(agg.inference_time_ms, 0))
        / NULLIF(COALESCE(agg.power_watts_avg, h.tdp_watts::double precision), 0)
        AS latency_efficiency_per_watt
FROM fact_benchmark_run f
JOIN dim_hardware h ON h.hardware_id = f.hardware_id
JOIN dim_workload w ON w.workload_id = f.workload_id
LEFT JOIN agg ON agg.run_id = f.run_id AND agg.run_date = f.run_date
WHERE f.run_status = 'success';

COMMENT ON VIEW vw_hardware_efficiency IS
    'One row per successful run with pivoted KPIs + perf-per-watt / perf-per-$1k metrics.';


-- ---------- vw_kpi_trend_daily --------------------------------------------
-- Daily aggregate per (workload, hardware, kpi). Powers trend lines.
CREATE OR REPLACE VIEW vw_kpi_trend_daily AS
SELECT
    f.run_date,
    d.year,
    d.quarter,
    d.month,
    d.week,
    w.code AS workload_code,
    w.category AS workload_category,
    h.code AS hardware_code,
    h.accelerator_type,
    h.vendor AS hardware_vendor,
    k.code AS kpi_code,
    k.name AS kpi_name,
    k.unit AS kpi_unit,
    k.direction AS kpi_direction,
    k.category AS kpi_category,
    COUNT(*)                                  AS run_count,
    AVG(v.value)::double precision            AS kpi_value_avg,
    MIN(v.value)::double precision            AS kpi_value_min,
    MAX(v.value)::double precision            AS kpi_value_max,
    STDDEV_POP(v.value)::double precision     AS kpi_value_stddev
FROM fact_kpi_value v
JOIN fact_benchmark_run f ON f.run_id = v.run_id AND f.run_date = v.run_date
JOIN dim_workload w ON w.workload_id = f.workload_id
JOIN dim_hardware h ON h.hardware_id = f.hardware_id
JOIN dim_kpi      k ON k.kpi_id     = v.kpi_id
JOIN dim_date     d ON d.date_id    = f.date_id
WHERE f.run_status = 'success'
GROUP BY
    f.run_date, d.year, d.quarter, d.month, d.week,
    w.code, w.category, h.code, h.accelerator_type, h.vendor,
    k.code, k.name, k.unit, k.direction, k.category;

COMMENT ON VIEW vw_kpi_trend_daily IS
    'Daily KPI aggregate per workload/hardware. Avg/min/max/stddev. Drives trend visuals.';


-- ---------- vw_regression_summary -----------------------------------------
-- Quality findings (regression + range + freshness) joined to dim attributes
-- with normalized deviation. One row per finding.
CREATE OR REPLACE VIEW vw_regression_summary AS
SELECT
    q.check_id,
    q.detected_at,
    q.detected_at::date AS detected_date,
    q.rule_id,
    q.rule_type,
    q.severity,
    q.status,
    q.source_name,
    q.source_record_key,
    q.workload_code,
    q.hardware_code,
    q.kpi_code,
    k.name      AS kpi_name,
    k.category  AS kpi_category,
    k.direction AS kpi_direction,
    k.unit      AS kpi_unit,
    q.observed_value::double precision  AS observed_value,
    q.baseline_value::double precision  AS baseline_value,
    q.expected_min::double precision    AS expected_min,
    q.expected_max::double precision    AS expected_max,
    q.deviation_pct::double precision   AS deviation_pct,
    q.message,
    -- Severity rank for sorting in visuals
    CASE q.severity
        WHEN 'critical' THEN 4
        WHEN 'error'    THEN 3
        WHEN 'warning'  THEN 2
        WHEN 'info'     THEN 1
        ELSE 0
    END AS severity_rank
FROM quality_check_result q
LEFT JOIN dim_kpi k ON k.code = q.kpi_code;

COMMENT ON VIEW vw_regression_summary IS
    'DQ findings (range/freshness/regression) with KPI attributes and severity rank.';


-- ---------- vw_etl_health -------------------------------------------------
-- ETL pipeline health per (date, source, pipeline). Powers ops dashboard tile.
CREATE OR REPLACE VIEW vw_etl_health AS
SELECT
    started_at::date AS run_date,
    source_name,
    pipeline,
    COUNT(*) FILTER (WHERE status = 'success') AS success_runs,
    COUNT(*) FILTER (WHERE status = 'failed')  AS failed_runs,
    COUNT(*) FILTER (WHERE status = 'started') AS started_runs,
    COUNT(*) AS total_runs,
    COALESCE(SUM(rows_in),          0) AS rows_in_total,
    COALESCE(SUM(rows_out),         0) AS rows_out_total,
    COALESCE(SUM(rows_quarantined), 0) AS rows_quarantined_total,
    -- Success ratio as percentage 0-100
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'success')
              / NULLIF(COUNT(*), 0),
        2
    )::double precision AS success_pct,
    MAX(ended_at) AS last_ended_at
FROM etl_run_log
GROUP BY started_at::date, source_name, pipeline;

COMMENT ON VIEW vw_etl_health IS
    'Daily ETL pipeline health: success/fail counts, rows processed, success %.';


-- ============================================================================
INSERT INTO schema_version (version, description)
VALUES (3, 'Reporting views for Power BI semantic layer (6 views)')
ON CONFLICT (version) DO NOTHING;
