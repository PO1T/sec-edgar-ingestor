# Master Plan

## Objective

Build a maintainable SEC EDGAR ingestion project that starts with 13F and evolves into the structured data backbone for a future EDGAR MCP server.

## Phase 1: Foundation

- Create the package structure, CLI, configuration layer, and logging.
- Add PostgreSQL migrations and a schema built for provenance and reprocessing.
- Establish documentation and durable project instructions.

## Phase 2: 13F Vertical Slice

- Discover 13F filings through EDGAR index files.
- Fetch filing artifacts from SEC archives.
- Parse XML-era 13F holdings reports and notice filings.
- Normalize filing-level and holding-level data.
- Load structured results into PostgreSQL with idempotent upserts.

## Phase 3: Hardening

- Add better checkpointing and operational reporting.
- Expand tests for amendments, notice filings, and partial reruns.
- Improve data quality validation and observability.

## Phase 4: Filing Family Expansion

- Add the next filing family according to `docs/FILING_PRIORITY.md`.
- Reuse shared acquisition, storage, and provenance primitives.
- Add enrichment layers only when they materially improve queryability.

## Phase 5: MCP Readiness

- Add canonical entity and instrument mapping tables.
- Add query-focused views and validation queries.
- Document downstream MCP tool patterns against the relational model.
