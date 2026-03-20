# Operations

## Runtime Prerequisites

- Python 3.10
- PostgreSQL
- Enough local disk for cached raw filing artifacts

## Environment Variables

Required:

- `SEC_EDGAR_DB_DSN`
- `SEC_EDGAR_USER_AGENT`

Optional:

- `SEC_EDGAR_DATA_DIR`
- `SEC_EDGAR_LOG_LEVEL`
- `SEC_EDGAR_REQUESTS_PER_SECOND`
- `SEC_EDGAR_HTTP_TIMEOUT_SECONDS`

## Raw Artifact Storage

- Raw filing artifacts are stored under `SEC_EDGAR_DATA_DIR/raw/filings/`.
- The database stores metadata and hashes, not the raw blobs themselves.
- Backups should include both PostgreSQL and the raw artifact directory.

## Recommended Operating Pattern

1. Run `sec-edgar db migrate`.
2. Run `sec-edgar ingest 13f --mode dev`.
3. Validate row counts and sample queries.
4. Run `sec-edgar ingest 13f --mode full` in a longer-lived environment.
5. Schedule `sec-edgar ingest 13f --mode daily`.

## Storage Estimate

These are rough engineering estimates for the current 13F-only implementation, not guarantees.

- 6-month dev dataset:
  - raw artifacts: roughly `200 MB` to `600 MB`
  - PostgreSQL: roughly `1 GB` to `3 GB`
- full XML-era 13F dataset:
  - raw artifacts: roughly `4 GB` to `10 GB`
  - PostgreSQL: roughly `20 GB` to `50 GB`

Actual size depends heavily on retained indexes, PostgreSQL version, fill factor, and future enrichment tables.
