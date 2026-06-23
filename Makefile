# BenchLens Makefile
# Works on Linux / macOS / Windows (with GNU make installed; on Windows use:
#   choco install make    OR    scoop install make
# All targets also work standalone — just copy the command body.

.PHONY: help install install-dev lint format test test-unit test-integration \
        run serve bootstrap-db docker-up docker-down clean

help:
	@echo "BenchLens — available targets:"
	@echo "  install            Install runtime + dev dependencies"
	@echo "  lint               Run ruff + black --check"
	@echo "  format             Auto-format with black + ruff --fix"
	@echo "  test               Run all tests with coverage"
	@echo "  test-unit          Run only unit tests"
	@echo "  test-integration   Run only integration tests"
	@echo "  bootstrap-db       Create DB schema (requires Postgres running)"
	@echo "  serve              Start FastAPI server"
	@echo "  docker-up          Start full stack (postgres + api + etl)"
	@echo "  docker-down        Stop full stack"
	@echo "  clean              Remove caches and build artifacts"

install:
	pip install -r requirements.txt

lint:
	ruff check benchlens tests
	black --check benchlens tests

format:
	ruff check --fix benchlens tests
	black benchlens tests

test:
	pytest --cov=benchlens --cov-report=term-missing

test-unit:
	pytest -m unit

test-integration:
	pytest -m integration

bootstrap-db:
	python scripts/bootstrap_db.py

serve:
	uvicorn benchlens.api.server:app --host 0.0.0.0 --port 8000 --reload

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
