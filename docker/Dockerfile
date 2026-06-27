# syntax=docker/dockerfile:1.7
#
# BenchLens — multi-stage Docker image.
#
# Stage 1 ("builder") installs Python dependencies into a virtualenv.
# Stage 2 ("runtime") copies that venv + the source tree into a slim base
# and runs the `benchlens` Typer CLI as a non-root user.
#
# Single image, multiple roles:
#   - API:        docker run benchlens serve --host 0.0.0.0 --port 8000
#   - Scheduler:  docker run benchlens scheduler start
#   - One-shot:   docker run benchlens db bootstrap
#
# Python 3.12-slim chosen for wide wheel coverage on pandas/psycopg/numpy.
# pyproject.toml is "requires-python = >=3.11", so 3.12 is in range.

# ---------- Stage 1: build ----------
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv "$VIRTUAL_ENV"

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Install the project itself (editable so the `benchlens` console_script is wired up).
COPY pyproject.toml README.md ./
COPY benchlens ./benchlens
RUN pip install --no-deps -e .


# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    BENCHLENS_HOME=/app

# Non-root user for security.
RUN groupadd --system --gid 1000 benchlens && \
    useradd --system --uid 1000 --gid benchlens --home-dir /app --shell /usr/sbin/nologin benchlens

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Runtime-only directories the app writes to.
COPY config ./config
COPY scripts ./scripts
COPY data ./data

RUN mkdir -p /app/logs /app/data/raw_extracts /app/data/quarantine && \
    chown -R benchlens:benchlens /app

USER benchlens

EXPOSE 8000

# Default to the CLI help so `docker run benchlens` is self-documenting.
# `docker-compose` overrides this for the api / scheduler services.
ENTRYPOINT ["benchlens"]
CMD ["--help"]
