# Schema

## Design Goals

- Preserve provenance to the original SEC filing.
- Support repeatable parsing and reprocessing.
- Make SQL queries straightforward for future MCP tools.
- Keep the initial schema extensible for later filing families.

## Core Tables

### `schema_migrations`

Tracks applied SQL migrations.

### `ingestion_runs`

Tracks each pipeline execution, mode, timing, and run status.

### `ingestion_checkpoints`

Stores resumable progress by filing family and ingestion mode.

### `filers`

Stores filer-level identifiers and latest known display metadata keyed by CIK.

### `filings`

Stores filing metadata keyed by accession number:

- form type,
- filer CIK,
- company name from the index,
- filed date,
- SEC archive paths and URLs,
- acceptance timestamp if available.

### `filing_artifacts`

Stores metadata for raw artifacts:

- filing accession number,
- artifact role,
- source URL,
- original filename,
- local cache path,
- sha256,
- size,
- content type.

### `filing_processing`

Tracks parser runs by accession number and parser version so improvements can be rerun without redesigning the schema.

## 13F Tables

### `security_references`

Stores the exact filed security identity tuple. This is intentionally not a global canonical security master.

### `thirteenf_filings`

Stores normalized filing-level 13F data:

- report period,
- amendment and notice flags,
- summary counts,
- total reported value in raw and normalized units,
- filing manager and signature metadata.

### `thirteenf_other_managers`

Stores referenced managers included in the filing.

### `thirteenf_holdings`

Stores one row per reported holding with:

- issuer and class details,
- CUSIP and FIGI if present,
- reported value,
- normalized USD value,
- share/principal amount,
- put/call metadata,
- discretion,
- voting authority.

## Effective Views

### `thirteenf_effective_filings`

Selects the most recent accepted filing per filer, report period, and form category so downstream queries do not need to hand-code amendment-selection logic.

### `thirteenf_effective_holdings`

Joins effective filings to holdings for reporting and future MCP use.

## Reprocessing Model

- Raw artifacts are cached on disk.
- The database records enough metadata to locate and validate them.
- Parser versioning lives in `filing_processing`.
- Reprocessing can rebuild normalized records from local artifacts without re-downloading immutable SEC files.

## Loading Semantics

- Core parent tables use `INSERT ... ON CONFLICT DO UPDATE`.
- 13F child tables for holdings and other managers are replaced per accession during reload.
- This keeps reprocessing deterministic without accumulating stale child rows.
