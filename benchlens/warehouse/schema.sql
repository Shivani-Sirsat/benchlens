-- ============================================================================
-- BenchLens — PostgreSQL warehouse schema (star schema)
-- ----------------------------------------------------------------------------
-- 6 dimensions + 2 facts + 1 audit table.
-- Designed for analytical query patterns driven by Power BI.
-- Idempotent: safe to run multiple times (uses IF NOT EXISTS).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Schema versioning (lets bootstrap_db.py know what's already applied)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER     PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description TEXT        NOT NULL
);

-- ============================================================================
-- DIMENSIONS
-- ============================================================================

-- ---------- dim_date ----------
CREATE TABLE IF NOT EXISTS dim_date (
    date_id       INTEGER     PRIMARY KEY,        -- YYYYMMDD integer
    full_date     DATE        NOT NULL UNIQUE,
    day           SMALLINT    NOT NULL,
    day_of_week   SMALLINT    NOT NULL,           -- 1=Mon .. 7=Sun
    day_name      VARCHAR(10) NOT NULL,
    week          SMALLINT    NOT NULL,
    month         SMALLINT    NOT NULL,
    month_name    VARCHAR(10) NOT NULL,
    quarter       SMALLINT    NOT NULL,
    year          SMALLINT    NOT NULL,
    is_weekend    BOOLEAN     NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dim_date_year_month ON dim_date(year, month);

COMMENT ON TABLE dim_date IS 'Date dimension; pre-populated from 2024-01-01 through 2030-12-31.';

-- ---------- dim_workload ----------
CREATE TABLE IF NOT EXISTS dim_workload (
    workload_id  SERIAL       PRIMARY KEY,
    code         VARCHAR(50)  NOT NULL UNIQUE,
    name         VARCHAR(200) NOT NULL,
    category     VARCHAR(50)  NOT NULL,           -- llm | image_gen | classical_ml | db | hpc
    version      VARCHAR(50),
    description  TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE dim_workload IS 'Benchmark workload catalog (e.g. llama-inference, sdxl-image-gen).';

-- ---------- dim_hardware ----------
CREATE TABLE IF NOT EXISTS dim_hardware (
    hardware_id       SERIAL       PRIMARY KEY,
    code              VARCHAR(100) NOT NULL UNIQUE,
    accelerator_type  VARCHAR(10)  NOT NULL CHECK (accelerator_type IN ('CPU','GPU','NPU')),
    vendor            VARCHAR(50)  NOT NULL,      -- Intel, AMD, NVIDIA, Apple, Qualcomm, ...
    sku               VARCHAR(200) NOT NULL,      -- e.g. "RTX 4090", "Ryzen 9 7950X"
    cores             INTEGER,
    memory_gb         NUMERIC(8,2),
    tdp_watts         INTEGER,
    price_usd         NUMERIC(10,2),
    release_year      SMALLINT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dim_hardware_accel ON dim_hardware(accelerator_type);

COMMENT ON TABLE dim_hardware IS 'Hardware SKUs under test (CPU/GPU/NPU).';

-- ---------- dim_stack ----------
CREATE TABLE IF NOT EXISTS dim_stack (
    stack_id         SERIAL       PRIMARY KEY,
    code             VARCHAR(100) NOT NULL UNIQUE,
    name             VARCHAR(200) NOT NULL,
    framework        VARCHAR(50),                 -- pytorch | tensorflow | onnxruntime | tensorrt | vllm
    version          VARCHAR(50),
    driver_version   VARCHAR(50),
    os_name          VARCHAR(50),
    os_version       VARCHAR(50),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE dim_stack IS 'Software stack: framework + driver + OS combination.';

-- ---------- dim_model ----------
CREATE TABLE IF NOT EXISTS dim_model (
    model_id         SERIAL       PRIMARY KEY,
    code             VARCHAR(100) NOT NULL UNIQUE,
    name             VARCHAR(200) NOT NULL,
    family           VARCHAR(50),                 -- llama | phi | mistral | sdxl | resnet ...
    parameter_count  BIGINT,                      -- in parameters (e.g. 7_000_000_000)
    quantization     VARCHAR(20),                 -- fp32 | fp16 | int8 | int4
    context_length   INTEGER,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dim_model_family ON dim_model(family);

COMMENT ON TABLE dim_model IS 'AI/ML model catalog (LLMs, image-gen, classifiers).';

-- ---------- dim_kpi ----------
CREATE TABLE IF NOT EXISTS dim_kpi (
    kpi_id      SERIAL       PRIMARY KEY,
    code        VARCHAR(50)  NOT NULL UNIQUE,
    name        VARCHAR(200) NOT NULL,
    category    VARCHAR(20)  NOT NULL CHECK (category IN ('performance','power','quality','reliability')),
    unit        VARCHAR(20)  NOT NULL,
    direction   VARCHAR(20)  NOT NULL CHECK (direction IN ('higher_is_better','lower_is_better')),
    description TEXT
);

COMMENT ON TABLE dim_kpi IS 'Canonical KPI catalog; seeded from config/kpi_definitions.yaml.';

-- ============================================================================
-- FACTS
-- ============================================================================

-- ---------- fact_benchmark_run ----------
-- Partitioned by run_date (monthly partitions) for time-range query performance.
CREATE TABLE IF NOT EXISTS fact_benchmark_run (
    run_id        BIGSERIAL    NOT NULL,
    run_uuid      UUID         NOT NULL DEFAULT gen_random_uuid(),
    workload_id   INTEGER      NOT NULL REFERENCES dim_workload(workload_id),
    hardware_id   INTEGER      NOT NULL REFERENCES dim_hardware(hardware_id),
    stack_id      INTEGER               REFERENCES dim_stack(stack_id),
    model_id      INTEGER               REFERENCES dim_model(model_id),
    date_id       INTEGER      NOT NULL REFERENCES dim_date(date_id),
    run_date      DATE         NOT NULL,
    started_at    TIMESTAMPTZ  NOT NULL,
    duration_s    NUMERIC(12,3),
    run_status    VARCHAR(20)  NOT NULL CHECK (run_status IN ('success','fail','timeout','aborted')),
    error_message TEXT,
    notes         TEXT,
    source_name   VARCHAR(100),
    source_record_key VARCHAR(200),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, run_date),
    UNIQUE (source_name, source_record_key, run_date)
) PARTITION BY RANGE (run_date);

CREATE INDEX IF NOT EXISTS idx_fact_run_workload ON fact_benchmark_run(workload_id);
CREATE INDEX IF NOT EXISTS idx_fact_run_hardware ON fact_benchmark_run(hardware_id);
CREATE INDEX IF NOT EXISTS idx_fact_run_model    ON fact_benchmark_run(model_id);
CREATE INDEX IF NOT EXISTS idx_fact_run_status   ON fact_benchmark_run(run_status);
CREATE INDEX IF NOT EXISTS idx_fact_run_date_id  ON fact_benchmark_run(date_id);

COMMENT ON TABLE fact_benchmark_run IS 'Run-level fact table; one row per benchmark execution. Partitioned monthly by run_date.';

-- Pre-create monthly partitions for 2025-01 through 2027-12 (sufficient for demo).
-- bootstrap_db.py extends this list dynamically via _ensure_partitions().
DO $$
DECLARE
    start_date DATE := DATE '2025-01-01';
    end_date   DATE := DATE '2027-12-01';
    cur_date   DATE := start_date;
    part_name  TEXT;
    next_date  DATE;
BEGIN
    WHILE cur_date <= end_date LOOP
        next_date := cur_date + INTERVAL '1 month';
        part_name := 'fact_benchmark_run_' || to_char(cur_date, 'YYYY_MM');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF fact_benchmark_run FOR VALUES FROM (%L) TO (%L);',
            part_name, cur_date, next_date
        );
        cur_date := next_date;
    END LOOP;
END $$;

-- ---------- fact_kpi_value ----------
-- One row per (run, KPI). The `value` column holds the metric;
-- dedicated columns capture metric families that Power BI charts directly.
CREATE TABLE IF NOT EXISTS fact_kpi_value (
    run_id              BIGINT       NOT NULL,
    run_date            DATE         NOT NULL,
    kpi_id              INTEGER      NOT NULL REFERENCES dim_kpi(kpi_id),
    value               NUMERIC(20,6) NOT NULL,
    -- denormalized metric family columns for fast Power BI access
    inference_time_ms   NUMERIC(12,3),
    power_watts_avg     NUMERIC(8,2),
    energy_kwh          NUMERIC(10,4),
    gpu_util_pct        NUMERIC(5,2),
    cpu_util_pct        NUMERIC(5,2),
    npu_util_pct        NUMERIC(5,2),
    memory_util_pct     NUMERIC(5,2),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, run_date, kpi_id),
    FOREIGN KEY (run_id, run_date) REFERENCES fact_benchmark_run(run_id, run_date) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fact_kpi_kpi  ON fact_kpi_value(kpi_id);
CREATE INDEX IF NOT EXISTS idx_fact_kpi_date ON fact_kpi_value(run_date);

COMMENT ON TABLE fact_kpi_value IS 'KPI-grain fact table; one row per (run, KPI).';

-- ============================================================================
-- AUDIT / OPERATIONAL
-- ============================================================================

CREATE TABLE IF NOT EXISTS etl_run_log (
    log_id        BIGSERIAL    PRIMARY KEY,
    source_name   VARCHAR(100) NOT NULL,
    pipeline      VARCHAR(50)  NOT NULL,         -- ingest | transform | load | quality | regression
    status        VARCHAR(20)  NOT NULL CHECK (status IN ('started','success','failed')),
    started_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ended_at      TIMESTAMPTZ,
    rows_in       INTEGER,
    rows_out      INTEGER,
    rows_quarantined INTEGER,
    error_message TEXT,
    extra         JSONB
);
CREATE INDEX IF NOT EXISTS idx_etl_log_source ON etl_run_log(source_name);
CREATE INDEX IF NOT EXISTS idx_etl_log_status ON etl_run_log(status);

COMMENT ON TABLE etl_run_log IS 'Audit log for every pipeline execution; populated by orchestration/pipeline.py (Day 4).';
