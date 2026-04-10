# sec-edgar-ingestor

`sec-edgar-ingestor` is a Python ingestion pipeline for SEC EDGAR data with PostgreSQL as the system of record.

The current production slice focuses on 13F. The long-term product goal is to make this repository the structured data foundation for a future EDGAR MCP server that answers natural-language questions with explainable, provenance-backed SQL tools.

## What It Does Today

- discovers 13F filings from official EDGAR index files,
- fetches filing artifacts from SEC archive URLs,
- caches raw artifacts on local disk,
- parses XML-era `13F-HR`, `13F-HR/A`, `13F-NT`, and `13F-NT/A`,
- normalizes filing metadata, manager data, and holdings,
- loads results into PostgreSQL with idempotent upserts,
- materializes CIK-keyed analytical views for fast holder and quarter-over-quarter queries,
- supports `dev`, `full`, `daily`, and `reprocess` workflows.

## Current Boundaries

- Supported family: `13F` only
- Historical scope: XML-era filings from `2013-05-20` onward
- Pre-2013 ASCII 13F support: not implemented
- Ticker, sector, and canonical security enrichment: not implemented
- Docker: intentionally not used

## Requirements

- Python `3.10`
- PostgreSQL
- `pip`

## Quickstart

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env
```

Create a PostgreSQL database and set `SEC_EDGAR_DB_DSN` in `.env`, then run:

```bash
sec-edgar db migrate
```

The migration step creates the base schema and the 13F analytics materialized views used for fast downstream queries.

## Commands

Development ingestion for the last 6 months:

```bash
sec-edgar ingest 13f --mode dev
```

Full XML-era backfill:

```bash
sec-edgar ingest 13f --mode full
```

Daily incremental refresh with checkpoint overlap:

```bash
sec-edgar ingest 13f --mode daily
```

Reprocess cached artifacts without re-downloading:

```bash
sec-edgar reprocess 13f --from-date 2024-01-01 --to-date 2024-03-31
```

Refresh analytics materialized views manually:

```bash
sec-edgar db refresh-analytics
```

If you want to postpone the refresh after a long ingest or reprocess run, use `--skip-analytics-refresh` and run the refresh command later.

## Configuration

Required:

- `SEC_EDGAR_DB_DSN`
- `SEC_EDGAR_USER_AGENT`

Optional:

- `SEC_EDGAR_DATA_DIR`
- `SEC_EDGAR_LOG_LEVEL`
- `SEC_EDGAR_REQUESTS_PER_SECOND`
- `SEC_EDGAR_HTTP_TIMEOUT_SECONDS`

See `.env.example` for defaults.

## Project Structure

```text
src/sec_edgar_ingestor/
  cli.py
  config.py
  db/
  sec/
  storage/
  pipeline/
  filings/thirteenf/
tests/
docs/
```

## Query Surfaces

The recommended downstream query surfaces are:

- `thirteenf_filer_identities` for filer lookup and aliases keyed by `cik`
- `thirteenf_filer_positions` for fast holder and position rollups
- `thirteenf_filer_position_changes` for fast quarter-over-quarter scans
- `thirteenf_compare_filer_holdings(...)` for direct period-vs-period comparisons with conservative rename/reclassification matching

For analytical queries, treat `cik` as the stable filer identity and `canonical_filer_name` as a display label. Raw `company_name` values from EDGAR indexes remain useful for provenance, but they are not a safe entity key.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Master Plan](docs/MASTER_PLAN.md)
- [Schema](docs/SCHEMA.md)
- [Engineering Decisions](docs/DECISIONS.md)
- [Filing Priority](docs/FILING_PRIORITY.md)
- [Ingestion Modes](docs/INGESTION_MODES.md)
- [Operations](docs/OPERATIONS.md)
- [Query Patterns](docs/QUERY_PATTERNS.md)
- [Progress](docs/PROGRESS.md)
- [Next Steps](docs/NEXT_STEPS.md)
- [Open Questions](docs/OPEN_QUESTIONS.md)

## Testing

The test suite is written so it can run with the standard library test runner:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Limitations

- Live PostgreSQL validation has been run against a populated local 13F dataset, including the CIK-keyed analytics materialized views and indexed quarter-over-quarter scans.
- The first slice is intentionally conservative about canonical security identity. Raw filed identifiers are preserved; enrichment comes later.

## License

Apache-2.0. See [LICENSE](LICENSE).
