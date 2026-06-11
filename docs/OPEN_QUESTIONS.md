# Open Questions

## Product / Data

- Which enrichment source should be preferred later for ticker aliases and security canonicalization?
- How should future non-XML historical backfills be prioritized once XML-era coverage is stable?

## Operations

- What backup policy should be recommended for local raw artifact storage?
- Should future releases support compressed raw artifact storage for large backfills?
- Should large backfills persist index-file fetch metadata for easier auditing and restart behavior?
- Should the analytics refresh path move to `REFRESH MATERIALIZED VIEW CONCURRENTLY` or another staged refresh model for lower read disruption?
- Should daily runs refresh every analytical surface every time, or should some views move to a separate scheduled refresh cadence?

## Data Quality

- How should amended 13F notice filings interact with prior holdings filings in downstream “effective” reporting views?
- Which data-quality checks should become hard failures versus warnings during ingestion?
