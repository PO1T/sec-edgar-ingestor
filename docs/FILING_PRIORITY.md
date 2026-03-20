# Filing Priority

Ranking from easiest to hardest for ingestion, parsing, and normalization after 13F:

1. `144`
   Relatively bounded and form-centric, with a narrower parsing surface than broad narrative disclosures.
2. `N-PORT`
   Highly structured and analytically rich, but materially denser than 13F.
3. `13G`
   Narrower domain than periodic reports, but ownership/amendment history gets messy.
4. `13GA`
   Same family as `13G` with additional amendment semantics.
5. `10-Q`
   XBRL helps, but narratives and footnotes complicate normalization.
6. `10-K`
   Similar to `10-Q` but larger and more irregular.
7. `8-K`
   Event-driven and heavily text/exhibit dependent.
8. `N-1A`
   Mixed structure with significant prospectus-like content.
9. `485POS`
   Hardest because interpretation often depends on amendment context and surrounding registration history.

Why 13F goes first:

- it is one of the most useful filing families for holder and position analysis,
- it has a structured XML-era format,
- it provides a strong proving ground for acquisition, provenance, normalization, and query-oriented schema design.
