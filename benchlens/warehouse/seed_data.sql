-- ============================================================================
-- BenchLens — reference (seed) data
-- ----------------------------------------------------------------------------
-- Idempotent: uses ON CONFLICT DO NOTHING so re-running is safe.
-- KPI rows are *also* seeded from config/kpi_definitions.yaml by bootstrap_db.py;
-- the SQL below is a backup so the warehouse is functional without Python too.
-- ============================================================================

-- ---------- dim_kpi (canonical KPI catalog) ----------
INSERT INTO dim_kpi (code, name, category, unit, direction, description) VALUES
    ('throughput',        'Throughput',             'performance', 'ops/sec',     'higher_is_better', 'Operations completed per second.'),
    ('tokens_per_sec',    'Tokens / Second',        'performance', 'tok/s',       'higher_is_better', 'LLM inference token-generation rate.'),
    ('inference_time_ms', 'Inference Time',         'performance', 'ms',          'lower_is_better',  'End-to-end inference latency per request.'),
    ('latency_p50',       'Latency p50',            'performance', 'ms',          'lower_is_better',  '50th percentile request latency.'),
    ('latency_p95',       'Latency p95',            'performance', 'ms',          'lower_is_better',  '95th percentile request latency.'),
    ('latency_p99',       'Latency p99',            'performance', 'ms',          'lower_is_better',  '99th percentile request latency.'),
    ('power_watts_avg',   'Average Power Draw',     'power',       'W',           'lower_is_better',  'Mean wall-power draw during the run.'),
    ('energy_kwh',        'Energy Consumed',        'power',       'kWh',         'lower_is_better',  'Total energy consumed during the run.'),
    ('perf_per_watt',     'Performance per Watt',   'power',       'ops/sec/W',   'higher_is_better', 'Throughput normalized by average power draw.'),
    ('gpu_util_pct',      'GPU Utilization',        'performance', '%',           'higher_is_better', 'Mean GPU compute utilization.'),
    ('cpu_util_pct',      'CPU Utilization',        'performance', '%',           'higher_is_better', 'Mean CPU utilization.'),
    ('npu_util_pct',      'NPU Utilization',        'performance', '%',           'higher_is_better', 'Mean NPU utilization.'),
    ('memory_util_pct',   'Memory Utilization',     'performance', '%',           'higher_is_better', 'Mean memory utilization.'),
    ('accuracy_score',    'Accuracy',               'quality',     'score',       'higher_is_better', 'Task-specific accuracy / quality score.'),
    ('success_rate',      'Success Rate',           'reliability', '%',           'higher_is_better', 'Fraction of runs that completed successfully.')
ON CONFLICT (code) DO NOTHING;

-- ---------- dim_workload ----------
INSERT INTO dim_workload (code, name, category, version, description) VALUES
    -- AI / ML workloads
    ('llama-inference-7b',  'Llama Inference 7B',     'llm',          '1.0', 'Llama 7B-class inference benchmark (prompt + decode).'),
    ('phi3-inference',      'Phi-3 Inference',        'llm',          '1.0', 'Phi-3 small-model inference benchmark.'),
    ('sdxl-image-gen',      'SDXL Image Generation',  'image_gen',    '1.0', 'Stable Diffusion XL text-to-image generation.'),
    ('resnet50-train',      'ResNet-50 Training',     'classical_ml', '1.0', 'ResNet-50 ImageNet training throughput.'),

    -- Database workloads (OLTP / OLAP / KV / Document)
    ('hammerdb-tpcc',       'HammerDB TPC-C',         'db',           '1.0', 'HammerDB TPC-C OLTP benchmark (multi-DB capable).'),
    ('hammerdb-tpch',       'HammerDB TPC-H',         'db',           '1.0', 'HammerDB TPC-H OLAP/decision-support benchmark.'),
    ('pgsql-pgbench',       'PostgreSQL pgbench',     'db',           '1.0', 'pgbench TPC-B-like OLTP workload on PostgreSQL.'),
    ('mssql-hammerdb',      'MSSQL HammerDB',         'db',           '1.0', 'HammerDB workload targeting Microsoft SQL Server.'),
    ('mysql-sysbench',      'MySQL sysbench',         'db',           '1.0', 'sysbench OLTP read/write workload on MySQL.'),
    ('mongodb-ycsb',        'MongoDB YCSB',           'db',           '1.0', 'YCSB key-value workload on MongoDB.'),
    ('redis-bench',         'Redis Benchmark',        'db',           '1.0', 'redis-benchmark SET/GET ops/sec.'),
    ('rocksdb-bench',       'RocksDB db_bench',       'db',           '1.0', 'RocksDB db_bench KV-store benchmark.'),
    ('tpcc-postgres',       'TPC-C on PostgreSQL',    'db',           '1.0', 'OLTP benchmark on PostgreSQL (legacy entry).'),

    -- Streaming / messaging
    ('kafka-bench',         'Kafka Benchmark',        'streaming',    '1.0', 'kafka-producer/consumer-perf throughput + latency.'),

    -- Big data / HPC
    ('hadoop-bench',        'Hadoop Benchmark',       'big_data',     '1.0', 'Hadoop MapReduce I/O and compute benchmark.'),
    ('hibench-terasort',    'HiBench TeraSort',       'big_data',     '1.0', 'HiBench TeraSort distributed sort benchmark.'),
    ('hibench-kmeans',      'HiBench K-Means',        'big_data',     '1.0', 'HiBench K-Means ML clustering on Spark/Hadoop.')
ON CONFLICT (code) DO NOTHING;

-- ---------- dim_hardware (CPU / GPU / NPU samples) ----------
INSERT INTO dim_hardware
    (code,              accelerator_type, vendor,    sku,                       cores, memory_gb, tdp_watts, price_usd, release_year)
VALUES
    ('cpu-amd-7950x',   'CPU', 'AMD',       'Ryzen 9 7950X',          16,    128.00,    170,       699.00,    2022),
    ('cpu-intel-14900k','CPU', 'Intel',     'Core i9-14900K',         24,    128.00,    253,       589.00,    2023),
    ('gpu-nv-rtx4090',  'GPU', 'NVIDIA',    'GeForce RTX 4090',       16384, 24.00,     450,       1599.00,   2022),
    ('gpu-nv-a100-80g', 'GPU', 'NVIDIA',    'A100 80GB',              6912,  80.00,     400,       15000.00,  2020),
    ('gpu-nv-h100',     'GPU', 'NVIDIA',    'H100 SXM5',              16896, 80.00,     700,       30000.00,  2023),
    ('gpu-amd-mi300x',  'GPU', 'AMD',       'Instinct MI300X',        19456, 192.00,    750,       15000.00,  2023),
    ('npu-intel-meteor','NPU', 'Intel',     'Meteor Lake NPU',        NULL,  NULL,      10,        NULL,      2023),
    ('npu-qcom-x-elite','NPU', 'Qualcomm',  'Snapdragon X Elite NPU', NULL,  NULL,      15,        NULL,      2024),
    ('npu-apple-m4',    'NPU', 'Apple',     'M4 Neural Engine',       NULL,  NULL,      8,         NULL,      2024)
ON CONFLICT (code) DO NOTHING;

-- ---------- dim_stack ----------
INSERT INTO dim_stack (code, name, framework, version, driver_version, os_name, os_version) VALUES
    ('pytorch-2.5-cuda12',  'PyTorch 2.5 + CUDA 12',  'pytorch',     '2.5.1',  'CUDA 12.4',     'Ubuntu', '22.04'),
    ('vllm-0.6',            'vLLM 0.6',               'vllm',        '0.6.4',  'CUDA 12.4',     'Ubuntu', '22.04'),
    ('onnxruntime-1.20',    'ONNX Runtime 1.20',      'onnxruntime', '1.20.1', NULL,            'Windows', '11'),
    ('tensorrt-10',         'TensorRT 10',            'tensorrt',    '10.6.0', 'CUDA 12.4',     'Ubuntu', '22.04')
ON CONFLICT (code) DO NOTHING;

-- ---------- dim_model ----------
INSERT INTO dim_model (code, name, family, parameter_count, quantization, context_length) VALUES
    ('llama3-8b-fp16',  'Llama 3 8B (fp16)',  'llama',    8000000000,    'fp16', 8192),
    ('llama3-8b-int4',  'Llama 3 8B (int4)',  'llama',    8000000000,    'int4', 8192),
    ('llama3-70b-fp16', 'Llama 3 70B (fp16)', 'llama',    70000000000,   'fp16', 8192),
    ('phi3-mini',       'Phi-3 Mini',         'phi',      3800000000,    'fp16', 4096),
    ('phi3-medium',     'Phi-3 Medium',       'phi',      14000000000,   'fp16', 4096),
    ('mistral-7b',      'Mistral 7B',         'mistral',  7300000000,    'fp16', 8192),
    ('sdxl-base-1.0',   'SDXL Base 1.0',      'sdxl',     3500000000,    'fp16', NULL),
    ('resnet50',        'ResNet-50',          'resnet',   25600000,      'fp32', NULL)
ON CONFLICT (code) DO NOTHING;
