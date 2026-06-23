# Changelog

All notable changes to BenchLens will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — Day 1: Scaffolding & Foundation
### Added
- Initial project structure for all 10 days of work
- Python package layout (`benchlens/`) with submodule stubs
- Root config: `README.md`, `LICENSE` (MIT), `.gitignore`, `.env.example`
- Build config: `requirements.txt`, `pyproject.toml`, `Makefile`
- Container stub: `docker-compose.yml` (PostgreSQL placeholder, expanded on Day 9)
- YAML configs: `settings.yaml`, `logging.yaml`, `sources.yaml`, `kpi_definitions.yaml`
- Utilities: `logger.py`, `config_loader.py`, `db.py`
- CLI entry point (`benchlens.main`) with subcommand skeletons:
  `version`, `bootstrap-db`, `ingest`, `run-pipeline`, `serve`
