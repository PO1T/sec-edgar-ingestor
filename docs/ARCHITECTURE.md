# Architecture

## System Intent

This repository is the ingestion and normalization layer for SEC EDGAR data. It is not the future MCP server itself. The ingestor is responsible for reliable acquisition, structured parsing, normalization, storage, and provenance.

The future MCP server should sit downstream and query PostgreSQL through purpose-built SQL tools. That downstream layer should not need to understand raw SEC transport details.

## High-Level Flow

1. Discover candidate filings from EDGAR index files.
2. Fetch filing artifacts from SEC archive URLs.
3. Store raw artifacts on local disk with hashes and metadata.
4. Parse filing-family-specific content into normalized models.
5. Load normalized records into PostgreSQL with idempotent upserts.
6. Expose query-friendly tables and views for downstream analytics and MCP tools.

## Implemented Module Layout

- `config.py`: environment and settings loading
- `db/`: Postgres connection helpers and SQL migrations
- `sec/`: SEC HTTP client and EDGAR index parsing
- `storage/`: raw artifact cache
- `pipeline/`: ingestion modes, checkpoints, orchestration
- `filings/thirteenf/`: submission discovery, parser, loader

## Why Index Files Plus Archives

The chosen ingestion backbone is EDGAR index files plus archive-hosted filing artifacts.

Benefits:

- uniform across many filing families,
- preserves exact source artifacts for provenance,
- supports full backfills and small incremental updates,
- avoids overfitting the system to one SEC API surface,
- makes reprocessing possible without redownloading once artifacts are cached locally.

Tradeoffs:

- requires more low-level ingestion code than using one structured API,
- daily index polling must tolerate weekends and holidays,
- some filing families will still need special parsers.

## Storage Model

### Raw Layer

- cached SEC artifacts on local filesystem,
- database metadata for every fetched artifact,
- file hashes to support integrity checks and reprocessing.

### Core Relational Layer

- filer metadata,
- filing metadata,
- processing state,
- ingestion runs and checkpoints.

### Filing-Family Layer

For 13F:

- normalized filing-level metadata,
- other-manager data,
- structured holdings rows,
- security-reference rows keyed to the exact filed identity tuple.

### Future Enrichment Layer

Deferred to later phases:

- ticker aliases,
- issuer canonicalization,
- sector or industry mappings,
- external identifiers and classifications.

## MCP Readiness Principles

- Every answerable question should trace back to a specific accession number and filing artifact.
- SQL-friendly grain matters more than early canonicalization.
- Quarter-over-quarter comparisons should be achievable through stable report period and filer keys.
- Future MCP tools should consume views that encode filing-family-specific “effective” logic, such as picking the latest valid amendment for a quarter.

## 13F Boundaries

13F can answer:

- filer-level reported AUM by quarter,
- largest reported positions,
- changes in holdings between quarters,
- option put/call aggregation within filed 13F data.

The implemented v1 code supports those foundations through `thirteenf_effective_filings` and `thirteenf_effective_holdings`.

13F alone cannot fully answer:

- true long vs short market exposure,
- sector exposure without enrichment,
- ticker-driven questions without alias mapping,
- structured notes, fund portfolio, or registration-statement questions from other filing families.
