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

## Analytics Materialized Views

### `thirteenf_filer_identities`

Provides a filer lookup surface keyed by `cik`:

- stable filer identifier for analytics,
- canonical display name,
- observed company-name aliases,
- observed filing-manager aliases.

This is the recommended surface for mapping user-facing filer names to a stable internal key.

### `thirteenf_filer_positions`

Pre-aggregates effective 13F holdings by:

- `report_period`,
- `cik`,
- `security_reference_key`,
- option/share shape keys.

It also joins back to `security_references` so issuer display fields come from the stable security tuple rather than raw per-row filing spellings. This is the primary fast surface for:

- top holdings for a filer,
- top holders for an issuer,
- option/share aggregations by filer or issuer.

### `thirteenf_filer_position_changes`

Precomputes quarter-over-quarter deltas from `thirteenf_filer_positions` for each filer/security combination. This is the primary fast surface for:

- biggest adds and trims by filer,
- broad cross-filer scans for a given issuer,
- MCP-style “who added” and “who sold” tools.

### `thirteenf_compare_filer_holdings(...)`

Compares two filing periods for one filer directly from `thirteenf_filer_positions`.

It matches positions in two passes:

- exact `security_reference_key` matches first,
- then a conservative fallback for one-to-one unmatched rows with the same issuer and identical share count.

The fallback exists to reduce false “sold” plus “new position” pairs when a filing reports the same economic position under a renamed or reclassified security reference across quarters.

## Indexing Strategy

The schema now includes:

- base indexes that speed joins and materialized-view refreshes,
- issuer/CUSIP/FIGI indexes for lookup patterns,
- report-period and delta/value indexes on the analytics materialized views.

For downstream analytics and MCP work, use `cik` as the filer key and treat raw `company_name` as provenance, not identity.

## Reprocessing Model

- Raw artifacts are cached on disk.
- The database records enough metadata to locate and validate them.
- Parser versioning lives in `filing_processing`.
- Reprocessing can rebuild normalized records from local artifacts without re-downloading immutable SEC files.

## Loading Semantics

- Core parent tables use `INSERT ... ON CONFLICT DO UPDATE`.
- 13F child tables for holdings and other managers are replaced per accession during reload.
- This keeps reprocessing deterministic without accumulating stale child rows.
