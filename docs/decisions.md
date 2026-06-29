# Design decisions

A short ADR-style log of the choices that shaped BenchLens, with the
trade-offs we accepted.

---

## ADR-1 — Postgres over a cloud warehouse

**Context.** Benchmark data is well-structured, modest volume (millions of
rows, not billions), and read-heavy from a small number of analysts.

**Decision.** Use **Postgres 16** as the warehouse.

**Why.**
- Portable: identical experience on a laptop, in CI, and on a server.
- No per-query cost — analysts can iterate freely.
- Native JSON, partitioning, window functions, and `pg_stat_*` cover
  every reporting need we have.
- Power BI has a first-class Postgres connector with query folding.

**Trade-off.** We give up the elasticity and zero-ops nature of Snowflake /
BigQuery / Databricks. For this scale, that's not a real cost.

---

## ADR-2 — Star schema with monthly-partitioned facts

**Context.** Fact rows grow linearly with benchmark runs; analytical queries
filter by date 95% of the time; old data is rarely deleted but sometimes
archived.

**Decision.** Classic Kimball star schema. `fact_benchmark_run` is **range-
partitioned by `run_date`** with one partition per month, pre-created for
2025-01 → 2027-12.

**Why.**
- Most queries hit a small date range → partition pruning gives
  10-100× speedups.
- Archiving = `DETACH PARTITION` + `pg_dump` — seconds, not hours.
- Partition keys are obvious to humans reading the SQL.

**Trade-off.** Adding a new date range past 2027 requires running the
partition-create DDL. Not automated yet — acceptable for a single-host demo.

---

## ADR-3 — SQLAlchemy 2.x + psycopg 3 over psycopg2 / asyncpg

**Context.** Need typed sessions, batch upserts, raw-SQL escape hatches, and
Python 3.14 wheel availability.

**Decision.** SQLAlchemy 2.x (`postgresql+psycopg://` URL) with **psycopg
3 binary**.

**Why.**
- psycopg2 has no Python 3.14 wheels — switching avoided a from-source
  build on Windows.
- psycopg 3 supports server-side cursors, COPY, and adaptive type loading.
- SQLAlchemy 2.x core API gives us typed `Mapped[...]` ORM and a raw
  DBAPI cursor escape hatch (needed for SQL files containing
  `format('%I', ...)` which psycopg's `%`-parameter parser otherwise
  trips on).
- Stays sync — async wouldn't help a single-host workload and adds
  complexity to every test.

**Trade-off.** Sync = one process per concurrent request in the API. Good
enough for the audience this serves; Gunicorn workers solve it horizontally.

---

## ADR-4 — FastAPI + PyJWT + stdlib scrypt

**Context.** Need a small REST API with JWT auth, RBAC, and OpenAPI docs.

**Decision.** **FastAPI** for routing + Pydantic validation; **PyJWT** for
tokens; **`hashlib.scrypt`** (stdlib) for password hashing.

**Why.**
- FastAPI gives free OpenAPI docs (`/docs`) — eliminates a documentation
  task.
- Pydantic shares schema definitions with config validation in the rest of
  the codebase.
- PyJWT is the minimal dependency that does HS256 well.
- `passlib`/`bcrypt` have no Python 3.14 wheels yet; stdlib `scrypt` is
  comparable in security and removes a dependency.

**Trade-off.** No password-reset flows, no refresh-token rotation. Out of
scope for a demo.

---

## ADR-5 — APScheduler over Prefect / Airflow

**Context.** Need a daily cron-style trigger that runs one job per enabled
source.

**Decision.** **APScheduler** `BackgroundScheduler` wrapped in a small
Typer command (`benchlens scheduler start`).

**Why.**
- Single dependency, already in `requirements.txt`.
- No server, no agent, no database — job state lives in the same container
  as the worker.
- A single-host demo doesn't need Prefect's UI/orchestration features.
- Our `benchlens/scheduler/` wrapper is intentionally thin (~80 lines), so
  swapping in Prefect later means rewriting only `runner.py`.

**Trade-off.** No retry-on-failure built in; no UI; no concurrent run
limiting beyond `max_instances=1`. Sufficient at this scale.

---

## ADR-6 — Power BI Desktop for dashboards

**Context.** Target users (HW evaluation engineers, ML engineers, SREs,
leadership) already use Power BI internally.

**Decision.** Power BI Desktop authoring, Postgres native connector,
optional Power BI Service for publishing. Commit **dashboard specs as
markdown** (`powerbi/reports/*.md`) and a **`.pbids` connection file** so
any reviewer can reproduce the report from scratch.

**Why.**
- Zero cost for authoring (Desktop is free).
- Audience familiarity — no training tax.
- Specs-as-code means dashboards are reviewable in PRs without binary
  diffs.

**Trade-off.** `.pbix` files are still binary, so the canonical source of
truth for visuals is the markdown spec + DAX library. Anyone can rebuild
the `.pbix` deterministically.

---

## ADR-7 — Multi-stage Docker, non-root, PYTHONPATH=/app

**Context.** Need an image that runs the API, the scheduler, or a one-shot
CLI — all from the same artifact.

**Decision.** Multi-stage build, `python:3.12-slim` runtime, non-root
`benchlens` user, `ENTRYPOINT ["benchlens"]`, and `PYTHONPATH=/app` so the
`scripts/` directory (not part of the installed package) remains
importable from the console script.

**Why.**
- Stage 1 builds a venv with `pip install -e .` → console script wired up.
- Stage 2 has no `pip`, no build tools → smaller and lower CVE surface.
- Single image, different `command:` per compose service → no duplication.
- Non-root is table stakes for hardening.

**Trade-off.** `python:3.12-slim` differs from the local dev Python 3.14.5.
We accept this because the platform's `pyproject.toml` declares
`requires-python = ">=3.11"` and pandas/psycopg wheels on 3.12 are far
more numerous than 3.14.

---

## ADR-8 — Ruff as the only linter/formatter

**Context.** Need a fast, opinionated quality gate that runs in CI and
pre-commit.

**Decision.** **Ruff** (`check` + `format`), rule selection
`["E", "F", "I", "UP", "B"]`, line length 100, target `py314`.

**Why.**
- Replaces `flake8` + `isort` + `black` + `pyupgrade` with one binary.
- Sub-second on the full codebase.
- Auto-fixes legacy `typing.*` → `collections.abc.*` and
  `timezone.utc` → `datetime.UTC` — kept the codebase modern with one
  command (~40 files cleaned automatically on Day 9).

**Trade-off.** No type-checking (no mypy/pyright in CI). Acceptable for a
project that already uses Pydantic + SQLAlchemy `Mapped[...]` at every
boundary.

---

## ADR-9 — Specs over `.pbix` binaries in source control

**Context.** `.pbix` files are zipped JSON + binary blobs — diffing is
useless and they balloon the repo.

**Decision.** Commit **markdown specs** for every dashboard
(`powerbi/reports/<name>.md`), a **shared DAX measure library**
(`powerbi/datasets/dax_measures.md`), and a **`.pbids` connection file**.
Keep `.pbix` files out of git (gitignored) and rebuild on demand from the
specs.

**Why.**
- Reviewable changes in PRs.
- No LFS, no repo bloat.
- Anyone (including the CI runner that doesn't have Power BI) can verify
  that the underlying views and measures exist.

**Trade-off.** You need Power BI Desktop installed to render the
dashboards. Screenshots are committed under `docs/screenshots/` as the
human-readable archive.

---

## ADR-10 — Skip `data/` in the Docker build context

**Context.** CI builds the Docker image fresh on every push. The repo's
`data/` directory has only gitignored runtime artifacts — git doesn't
track empty directories, so the dir simply doesn't exist in CI.

**Decision.** Don't `COPY data ./data` in the Dockerfile. Create empty
`data/raw`, `data/raw_extracts`, `data/state`, `data/staging`,
`data/quarantine` with `mkdir -p` at build time.

**Why.**
- Otherwise CI fails with `failed to compute cache key: "/data": not
  found`.
- Pipeline writes those dirs at runtime anyway.

**Trade-off.** None — strictly better.
