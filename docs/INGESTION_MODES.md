# Ingestion Modes

## `dev`

- Intended for local development and parser iteration.
- Default window: last 6 months.
- Discovery source: EDGAR daily index files.
- Recommended first run for new contributors.

## `full`

- Intended for XML-era 13F backfill.
- Default window: `2013-05-20` to today.
- Discovery source: quarterly EDGAR full index files.
- Best run in environments with enough disk for raw artifacts and a larger PostgreSQL dataset.

## `daily`

- Intended for steady-state refresh after a backfill.
- Uses saved checkpoints and re-scans the trailing 7 days to tolerate late updates or corrections.
- Discovery source: EDGAR daily index files.

## `reprocess`

- Does not re-download immutable SEC artifacts.
- Reads cached local artifacts and rebuilds normalized rows with the current parser version.
- Useful after parser fixes or schema-preserving normalization changes.
