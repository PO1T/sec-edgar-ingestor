# Next Steps

1. Add production-oriented refresh controls for the analytics materialized views, likely including concurrent refresh strategy evaluation.
2. Add richer ingestion run metrics and data quality warning summaries.
3. Design the first enrichment layer for ticker aliases and canonical instrument mapping.
4. Benchmark the heaviest issuer-level and filer-level MCP query shapes and add any remaining targeted indexes.
5. Implement the next filing family, likely `144` or `N-PORT`, on the shared acquisition/storage foundation.
