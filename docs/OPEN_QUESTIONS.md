# Open Questions

## Product / Data

- Which enrichment source should be preferred later for ticker aliases and security canonicalization?
- How should future non-XML historical backfills be prioritized once XML-era coverage is stable?
- Should the long-term effective-filing logic distinguish restatements from “adds new holdings” amendments more explicitly?

## Operations

- What backup policy should be recommended for local raw artifact storage?
- Should future releases support compressed raw artifact storage for large backfills?
- Should large backfills persist index-file fetch metadata for easier auditing and restart behavior?

## Data Quality

- How should amended 13F notice filings interact with prior holdings filings in downstream “effective” reporting views?
- Which data-quality checks should become hard failures versus warnings during ingestion?
