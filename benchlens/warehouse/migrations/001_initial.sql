-- ============================================================================
-- Migration 001: initial schema
-- ----------------------------------------------------------------------------
-- This is the first migration. It loads the full DDL from schema.sql and
-- records the version. bootstrap_db.py reads schema_version to skip already
-- applied migrations on subsequent runs.
-- ============================================================================

-- Schema DDL is applied separately from schema.sql by bootstrap_db.py.
-- This file only records that version 1 is now installed.

INSERT INTO schema_version (version, description)
VALUES (1, 'Initial star schema: 6 dimensions, 2 facts, etl_run_log')
ON CONFLICT (version) DO NOTHING;
