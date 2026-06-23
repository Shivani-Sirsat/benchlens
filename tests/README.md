# Tests

- `unit/` — fast, isolated tests (no DB / network)
- `integration/` — pipeline + API tests against a real Postgres
- `fixtures/` — sample CSV / JSON benchmark payloads

Run with: `pytest` or `make test`.
