# Query Patterns

## Recommended Analytical Surfaces

- Use `thirteenf_filer_identities` to resolve names to `cik`.
- Use `thirteenf_filer_positions` for fast holder rankings and filer snapshots.
- Use `thirteenf_filer_position_changes` for fast quarter-over-quarter scans.
- Use `thirteenf_compare_filer_holdings(...)` when you need a direct two-period comparison that can conservatively match renamed or reclassified positions.

For analytical work, filter by `cik` and treat `canonical_filer_name` as a display field. Raw `company_name` is still useful for provenance, but it is not a canonical manager key.

## Example Queries

Resolve a filer name to stable identifiers:

```sql
select cik, canonical_filer_name, company_name_aliases, filing_manager_aliases
from thirteenf_filer_identities
where canonical_filer_name ilike '%berkshire%';
```

Top positions for one filer in a quarter:

```sql
select issuer_name, class_title, cusip, total_value_usd
from thirteenf_filer_positions
where cik = '1067983'
  and report_period = date '2025-12-31'
order by total_value_usd desc
limit 10;
```

Top holders for one issuer in a quarter:

```sql
select cik, canonical_filer_name, total_value_usd
from thirteenf_filer_positions
where report_period = date '2025-12-31'
  and issuer_name = 'APPLE INC'
order by total_value_usd desc
limit 10;
```

Biggest quarter-over-quarter adds for one issuer:

```sql
select cik, canonical_filer_name, delta_value_usd
from thirteenf_filer_position_changes
where report_period = date '2025-12-31'
  and issuer_name = 'APPLE INC'
order by delta_value_usd desc
limit 10;
```

Biggest trims for one issuer:

```sql
select cik, canonical_filer_name, delta_value_usd
from thirteenf_filer_position_changes
where report_period = date '2025-12-31'
  and issuer_name = 'APPLE INC'
order by delta_value_usd asc
limit 10;
```

Quarter-over-quarter changes for one filer:

```sql
select report_period, issuer_name, delta_value_usd, delta_shares_principal_amount
from thirteenf_filer_position_changes
where cik = '1067983'
  and report_period = date '2025-12-31'
order by abs(delta_value_usd) desc
limit 10;
```

Direct comparison between two periods for one filer:

```sql
select issuer_name, class_title, previous_class_title, value_change_usd, match_strategy
from thirteenf_compare_filer_holdings(
    '1067983',
    date '2025-12-31',
    date '2025-09-30'
)
order by abs(value_change_usd) desc;
```
