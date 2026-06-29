# BenchLens — Benchmark Analytics Platform

[![CI](https://github.com/Shivani-Sirsat/benchlens/actions/workflows/ci.yml/badge.svg)](https://github.com/Shivani-Sirsat/benchlens/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.14-blue.svg)](pyproject.toml)
[![Postgres](https://img.shields.io/badge/postgres-16-336791.svg)](docker-compose.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](.pre-commit-config.yaml)

> **See every benchmark, every regression, every time.**
>
> An end-to-end analytics platform for AI/ML and hardware benchmark data:
> ingest from any source → land in a Postgres star-schema warehouse → enforce
> quality + detect regressions → serve via REST API → visualize through four
> Power BI dashboards.

```mermaid
flowchart LR
    subgraph Sources
        CSV[CSV / Parquet]
        JSON[JSON results]
        REST[REST APIs]
        SQL[(Vendor DBs)]
    end

    subgraph Ingestion
        CONN[Connectors<br/>+ incremental state]
    end

    subgraph Transform
        XF[Field mapping<br/>+ KPI normalize]
    end

    subgraph Quality
        DQ[DQ rules<br/>range / freshness / regression]
    end

    subgraph Warehouse
        PG[(Postgres 16<br/>star schema<br/>+ partitioned facts)]
        VIEWS[[11 reporting views]]
    end

    subgraph Serve
        API[FastAPI<br/>JWT + RBAC]
        SCHED[APScheduler<br/>cron worker]
        BI[Power BI<br/>4 dashboards]
    end

    CSV & JSON & REST & SQL --> CONN --> XF --> PG
    PG --> DQ --> PG
    PG --> VIEWS --> BI
    PG --> API
    SCHED -.daily.-> CONN
```

---

## Quickstart — one command, full stack

```powershell
git clone https://github.com/Shivani-Sirsat/benchlens.git
cd benchlens
docker compose up -d
```

That builds the image, starts Postgres, bootstraps the schema + seed data + reporting views, then launches the API and scheduler.

| Endpoint | URL |
|---|---|
| API health | http://localhost:8000/health |
| OpenAPI docs | http://localhost:8000/docs |
| Postgres | `postgres://benchlens:benchlens@localhost:5432/benchlens` |

**Demo credentials** (local dev only):
| Role | User | Password |
|---|---|---|
| admin (write) | `admin` | `admin` |
| viewer (read) | `viewer` | `viewer` |

Tear down with `docker compose down -v`.

### Native quickstart (without Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
copy .env.example .env        # edit if your Postgres differs
benchlens db bootstrap         # create schema + load seeds + install views
benchlens serve                # API on :8000
benchlens scheduler start      # in a second shell — cron worker
```

---

## What's in the box

| Layer | Tech | Status |
|---|---|---|
| **Warehouse** | Postgres 16, star schema (6 dims + 2 facts, monthly-partitioned), 11 reporting views | shipped |
| **Ingestion** | CSV / JSON / REST / SQL connectors, incremental state, retry | shipped |
| **Transform** | Field mapping, KPI normalization, schema validation | shipped |
| **Data Quality** | Range / freshness / regression rules, findings table, severity ranking | shipped |
| **REST API** | FastAPI, JWT auth, RBAC, OpenAPI, healthcheck, Prometheus-ready | shipped |
| **Orchestration** | APScheduler cron worker — one job per enabled source | shipped |
| **Power BI** | Connection file, data-model spec, full DAX library, **4 dashboard specs** | shipped |
| **Containers** | Multi-stage Dockerfile (non-root), 4-service compose (postgres → bootstrap → api + scheduler) | shipped |
| **CI/CD** | GitHub Actions: ruff lint, pytest with Postgres service, docker build cache | shipped |
| **Tests** | 118 passing (47 integration + 71 unit) | shipped |

---

## Dashboards

Four Power BI reports back the platform. Each has a full **build spec** committed under [powerbi/reports/](powerbi/reports/) so they can be reproduced from scratch in Power BI Desktop using the [.pbids connection file](powerbi/datasets/benchmark_model.pbids) and the [DAX library](powerbi/datasets/dax_measures.md).

| Dashboard | Audience | Answers |
|---|---|---|
| **Executive Summary** ([spec](powerbi/reports/executive_summary.md)) | Leadership | "How healthy is the benchmark program right now?" |
| **Hardware Performance** ([spec](powerbi/reports/hardware_performance.md)) | HW evaluation engineers | "Which accelerator gives best perf/watt and perf/$ for my workload?" |
| **Model Comparison** ([spec](powerbi/reports/model_comparison.md)) | ML engineers | "Which model wins on throughput / $ / accuracy, normalized for parameter count?" |
| **Regression & Reliability** ([spec](powerbi/reports/regression_reliability.md)) | SRE / DQ | "Where are regressions concentrated, how fast do we catch them?" |

Screenshots are stored in [docs/screenshots/](docs/screenshots/) — see the [README there](docs/screenshots/README.md) for instructions on regenerating them from the `.pbix` files.

---

## Architecture at a glance

```mermaid
flowchart TB
    subgraph Container Stack
        direction TB
        PG[(postgres:16-alpine<br/>volume: benchlens_pgdata)]
        BOOT[bootstrap<br/>one-shot:<br/>schema + seeds + views]
        API[api<br/>benchlens serve<br/>:8000]
        SCHED[scheduler<br/>benchlens scheduler start]
        BOOT -- exits 0 --> API
        BOOT -- exits 0 --> SCHED
        PG -- healthcheck --> BOOT
        API -- SQL --> PG
        SCHED -- SQL --> PG
    end
```

Full architecture document: [docs/architecture.md](docs/architecture.md)
Design decisions log: [docs/decisions.md](docs/decisions.md)

---

## Project structure

```
benchlens/
├── benchlens/                  Python package
│   ├── main.py                 Typer CLI (db / serve / scheduler / reports)
│   ├── ingestion/              CSV, JSON, REST, SQL connectors + state
│   ├── transform/              Field mapping, KPI normalization, schema
│   ├── load/                   Dim resolution, warehouse writer, ETL log
│   ├── quality/                Rules, validators, regression detector
│   ├── warehouse/              SQLAlchemy models + migrations
│   ├── orchestration/          run_pipeline() — source → fact orchestrator
│   ├── scheduler/              APScheduler wrapper + JobRegistry
│   ├── api/                    FastAPI app, auth, routes, schemas
│   ├── alerts/                 Console + file sinks
│   ├── reports/                View installer
│   └── utils/                  Config, DB, logging
├── config/                     sources.yaml, settings.yaml, rules
├── powerbi/                    .pbids, data model, DAX, 4 dashboard specs, theme
├── sql/                        Migrations + reporting views
├── scripts/                    bootstrap_db.py, generators
├── tests/                      unit/ + integration/ + fixtures/
├── docker/                     multi-stage Dockerfile
├── docs/                       architecture, decisions, screenshots
├── .github/workflows/ci.yml    lint + test + docker-build pipeline
└── docker-compose.yml          full local stack
```

---

## Development

```powershell
# Tests
python -m pytest -q                    # all 118
python -m pytest tests/unit -q         # fast feedback loop

# Lint + format (matches CI exactly)
ruff check .
ruff format --check .

# Pre-commit (run once after clone)
pre-commit install
```

Pre-commit hooks auto-format with ruff on every `git commit`.

---

## Tech decisions in one paragraph

**Postgres** over a cloud warehouse for portability + zero-cost local dev. **Star schema** + partitioned facts for analytics-friendly queries and cheap drops of old partitions. **SQLAlchemy 2.x + psycopg 3** for typed sessions and Python 3.14 wheel coverage. **FastAPI** for typed routes + free OpenAPI; **PyJWT + stdlib scrypt** instead of `passlib` (Py 3.14 compat). **APScheduler** over Prefect/Airflow — single-host demo doesn't need a control plane. **Power BI Desktop** for dashboards because the target users are already on it (free authoring tier, Postgres native connector). **Ruff** as the only lint + format tool. Full reasoning in [docs/decisions.md](docs/decisions.md).

---

## 10-day build log

| Day | Theme | Commit |
|---|---|---|
| 1 | Scaffolding | `014663f` |
| 2 | Warehouse (star schema, partitions, seeds) | `1819dcd` |
| 3 | Ingestion (4 connectors + state) | `7fcbfde` |
| 4 | Transform + Load (full ETL) | `2acd72f` |
| 5 | Data Quality + regression detection | `4ea13e7` |
| 6 | REST API (FastAPI + JWT + RBAC) | `49e0040` |
| 7 | Power BI semantic layer (6 views + DAX) | `a09f7d3` |
| 8 | Dashboards 3 & 4 + 5 more views | `5d13263` |
| 9 | Orchestration + Docker + CI/CD | `099178b` |
| 10 | Docs + demo + v1.0.0 | this commit |

Full notes in [CHANGELOG.md](CHANGELOG.md).

---

## License

MIT — see [LICENSE](LICENSE).

