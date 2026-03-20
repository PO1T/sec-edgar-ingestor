# AGENTS.md

This file records durable instructions for future coding-agent sessions working in this repository.

## Project Identity

- Repository: `sec-edgar-ingestor`
- Purpose: ingest SEC EDGAR filings into PostgreSQL as the data foundation for a future MCP server
- Immediate implementation target: 13F only
- Long-term goal: support multiple filing families without redesigning the storage model

## Engineering Guardrails

- Keep the project anonymized and publishable as open source.
- Do not hard-code personal paths, usernames, machine-specific settings, or private infrastructure.
- Keep Python code compatible with Python 3.10.
- Use `pip` packaging and local virtual environments; do not introduce Docker.
- Keep dependencies intentionally small and mature.
- Favor explainable, SQL-friendly schemas over clever abstractions.
- Preserve provenance back to raw SEC artifacts.
- Optimize for resumability and reprocessing.

## Architecture Constraints

- The primary ingestion strategy is EDGAR index files plus filing archives.
- `data.sec.gov` and SEC datasets are secondary validation or enrichment sources, not the canonical ingestion backbone.
- Raw artifacts should live on disk with database metadata that points to them.
- Database schema should separate:
  - core filing metadata,
  - filing-family-specific normalized tables,
  - future enrichment/canonicalization layers.
- 13F support must include amendments and notice filings, not only standard holdings reports.

## Workflow Expectations

- Inspect existing code before changing it.
- Keep docs updated in the same change set as behavior changes.
- Prefer small, reviewable commits with conventional commit messages.
- Add or update tests for all non-trivial parsing and loading behavior.
- Do not silently defer risky edge cases; document them in `docs/OPEN_QUESTIONS.md` or `docs/NEXT_STEPS.md`.

## Repo Conventions

- Source code lives under `src/sec_edgar_ingestor/`.
- SQL migrations live under `src/sec_edgar_ingestor/db/migrations/`.
- Tests live under `tests/`.
- Fixtures should be deterministic and checked into git.
- CLI entry point should remain `sec-edgar`.
- Keep the standard library `unittest` runner working even if `pytest` is not installed locally.

## Safety Notes

- Never delete cached raw artifacts automatically.
- Never treat issuer names or tickers as globally canonical without an explicit normalization layer.
- Keep parser versioning explicit so reprocessing is possible when logic changes.
