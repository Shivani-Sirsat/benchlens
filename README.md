# BenchLens — Benchmark Analytics Platform

> *See every benchmark, every regression, every time.*

A centralized analytics platform for AI/ML and hardware benchmark data. Ingests results from multiple sources, stores them in a PostgreSQL star-schema warehouse, exposes a REST API, and surfaces interactive **Power BI dashboards** for executives, hardware engineers, ML engineers, and SREs.

---

## Features

- **PostgreSQL star-schema warehouse** — 6 dimensions, 2 fact tables, partitioning, materialized views
- **Pluggable ETL pipeline** — CSV / JSON / REST / SQL connectors with retry, idempotent upsert
- **Data quality gate** — declarative validators, quarantine table, audit log
- **Regression detection** — rolling baseline + z-score + severity classification
- **REST API** — FastAPI, JWT + RBAC, OpenAPI docs, Prometheus metrics
- **4 Power BI reports** — Executive Summary, Hardware (CPU/GPU/NPU), Model Comparison, Regression & Reliability
- **Phase 5 analytics** — historical trends, KPI filtering, Year→Month→Day→Run drill-down, RLS
- **Production-ready** — Docker, docker-compose, Kubernetes, GitHub Actions CI/CD

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy 2.x |
| API | FastAPI + Uvicorn |
| ETL | Pandas, Pydantic, httpx, APScheduler |
| Visualization | Power BI Desktop + Service |
| Containers | Docker, docker-compose, Kubernetes |
| CI/CD | GitHub Actions |

---

## Quickstart

```powershell
# 1. Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env template
copy .env.example .env

# 4. Verify CLI
python -m benchlens.main --help
```

For Docker + full stack: `docker-compose up` (available from Day 9).

---

## Project structure

```
benchlens/
├── benchlens/              # Python package
│   ├── main.py             # CLI entry point
│   ├── ingestion/          # Extract layer
│   ├── transform/          # Transform layer (KPIs, regressions)
│   ├── load/               # Load layer (upsert, bulk COPY)
│   ├── warehouse/          # PostgreSQL star-schema models
│   ├── orchestration/      # Pipeline + scheduler
│   ├── api/                # FastAPI service
│   ├── quality/            # Data quality validators
│   ├── alerts/             # Email + Teams notifier
│   └── utils/              # Logger, config, DB helpers
├── config/                 # YAML configuration
├── powerbi/                # .pbix files, DAX, themes, deploy scripts
├── sql/                    # Views and materialized views
├── tests/                  # Unit + integration tests
├── docker/                 # Dockerfiles
├── kubernetes/             # K8s manifests
├── scripts/                # Bootstrap, sample data, triggers
├── notebooks/              # Exploratory analysis
├── docs/                   # Architecture, data model, API ref
└── .github/workflows/      # CI + Power BI deploy
```

---

## 10-day roadmap

| Day | Theme | Deliverable |
|---|---|---|
| 1 | Scaffolding | Runnable skeleton + configs (this commit) |
| 2 | Warehouse | PostgreSQL star schema (6 dims, 2 facts) |
| 3 | Ingestion | 4 connectors (CSV / JSON / REST / SQL) |
| 4 | Transform + Load | End-to-end ETL pipeline |
| 5 | Quality + Regressions | Validators + regression detector |
| 6 | REST API | FastAPI + JWT/RBAC + 10 endpoints |
| 7 | Power BI #1 | Executive Summary + Hardware (CPU/GPU/NPU) |
| 8 | Power BI #2 + Phase 5 | Model Comparison + Reliability + trends/drill-down |
| 9 | Ops | Scheduler + alerts + Docker + K8s + CI/CD |
| 10 | Docs + Demo | Full docs + demo + screenshots |

See [CHANGELOG.md](CHANGELOG.md) for progress.

---

## License

MIT — see [LICENSE](LICENSE).
