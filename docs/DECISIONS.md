# Decisions

## ADR-001: Use EDGAR Index Files Plus Archive URLs As The Primary Ingestion Backbone

Status: accepted

Why:

- works across filing families,
- supports both full and incremental ingestion,
- preserves provenance and raw artifacts,
- keeps future filing-family expansion on one acquisition foundation.

Tradeoffs:

- more implementation work than relying on a single structured endpoint,
- must handle missing daily index files on holidays and other no-filing days.

## ADR-002: Start With XML-Era 13F Only

Status: accepted

Why:

- XML-era 13F is structured and tractable,
- it avoids the complexity of pre-2013 text parsing,
- it delivers useful normalized holdings data quickly.

Tradeoffs:

- historical completeness before `2013-05-20` is deferred.

## ADR-003: Store Raw Artifacts On Disk And Metadata In PostgreSQL

Status: accepted

Why:

- keeps the database smaller,
- supports reprocessing,
- preserves exact source documents.

Tradeoffs:

- operators must retain local artifact storage,
- backup procedures must include both PostgreSQL and the artifact directory.

## ADR-004: Delay Canonical Security/Ticker Normalization

Status: accepted

Why:

- raw filed identifiers are safer than premature canonicalization,
- future enrichment can happen on top of trustworthy source-derived tables.

Tradeoffs:

- some natural-language ticker queries will remain incomplete until enrichment is added.

## ADR-005: Use Plain SQL Migrations And A Minimal Standard-Library CLI

Status: accepted

Why:

- keeps the first implementation lightweight,
- avoids taking on an ORM before the schema is stable,
- makes database behavior explicit for an analytics-first project.

Tradeoffs:

- schema evolution ergonomics are more manual than with a full migration framework,
- some future complexity may justify revisiting this choice.
