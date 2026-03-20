CREATE INDEX IF NOT EXISTS thirteenf_filings_report_period_accession_idx
    ON thirteenf_filings (report_period, accession_number);

CREATE INDEX IF NOT EXISTS thirteenf_holdings_accession_security_idx
    ON thirteenf_holdings (accession_number, security_reference_key);

CREATE INDEX IF NOT EXISTS thirteenf_holdings_issuer_name_idx
    ON thirteenf_holdings (issuer_name);

CREATE INDEX IF NOT EXISTS thirteenf_holdings_figi_idx
    ON thirteenf_holdings (figi);

CREATE MATERIALIZED VIEW thirteenf_filer_identities AS
SELECT
    fl.cik,
    COALESCE(NULLIF(fl.filer_name, ''), MIN(f.company_name)) AS canonical_filer_name,
    fl.first_seen_filed_date,
    fl.last_seen_filed_date,
    COALESCE(
        ARRAY_AGG(DISTINCT f.company_name) FILTER (WHERE f.company_name IS NOT NULL),
        ARRAY[]::TEXT[]
    ) AS company_name_aliases,
    COALESCE(
        ARRAY_AGG(DISTINCT tf.filing_manager_name) FILTER (WHERE tf.filing_manager_name IS NOT NULL),
        ARRAY[]::TEXT[]
    ) AS filing_manager_aliases
FROM filers fl
LEFT JOIN filings f
    ON f.cik = fl.cik
   AND f.filing_family = '13F'
LEFT JOIN thirteenf_filings tf
    ON tf.accession_number = f.accession_number
GROUP BY
    fl.cik,
    fl.filer_name,
    fl.first_seen_filed_date,
    fl.last_seen_filed_date;

CREATE UNIQUE INDEX thirteenf_filer_identities_cik_idx
    ON thirteenf_filer_identities (cik);

CREATE INDEX thirteenf_filer_identities_name_idx
    ON thirteenf_filer_identities (canonical_filer_name);

CREATE MATERIALIZED VIEW thirteenf_filer_positions AS
SELECT
    eh.report_period,
    eh.cik,
    COALESCE(
        MAX(fi.canonical_filer_name),
        MAX(eh.filing_manager_name),
        MAX(eh.company_name)
    ) AS canonical_filer_name,
    eh.security_reference_key,
    sr.issuer_name,
    sr.class_title,
    sr.cusip,
    sr.figi,
    COALESCE(eh.put_call, 'NONE') AS put_call_key,
    COALESCE(eh.shares_principal_type, 'UNKNOWN') AS shares_principal_type_key,
    SUM(COALESCE(eh.value_usd, 0)) AS total_value_usd,
    SUM(COALESCE(eh.value_reported, 0)) AS total_value_reported,
    SUM(COALESCE(eh.shares_principal_amount, 0)) AS total_shares_principal_amount,
    COUNT(*) AS source_row_count
FROM thirteenf_effective_holdings eh
LEFT JOIN thirteenf_filer_identities fi
    ON fi.cik = eh.cik
INNER JOIN security_references sr
    ON sr.security_reference_key = eh.security_reference_key
GROUP BY
    eh.report_period,
    eh.cik,
    eh.security_reference_key,
    sr.issuer_name,
    sr.class_title,
    sr.cusip,
    sr.figi,
    COALESCE(eh.put_call, 'NONE'),
    COALESCE(eh.shares_principal_type, 'UNKNOWN');

CREATE UNIQUE INDEX thirteenf_filer_positions_identity_idx
    ON thirteenf_filer_positions (
        report_period,
        cik,
        security_reference_key,
        put_call_key,
        shares_principal_type_key
    );

CREATE INDEX thirteenf_filer_positions_cik_report_period_idx
    ON thirteenf_filer_positions (cik, report_period);

CREATE INDEX thirteenf_filer_positions_report_period_cik_value_idx
    ON thirteenf_filer_positions (report_period, cik, total_value_usd DESC);

CREATE INDEX thirteenf_filer_positions_report_period_issuer_value_idx
    ON thirteenf_filer_positions (report_period, issuer_name, total_value_usd DESC);

CREATE INDEX thirteenf_filer_positions_report_period_cusip_value_idx
    ON thirteenf_filer_positions (report_period, cusip, total_value_usd DESC);

CREATE INDEX thirteenf_filer_positions_report_period_figi_value_idx
    ON thirteenf_filer_positions (report_period, figi, total_value_usd DESC);

CREATE MATERIALIZED VIEW thirteenf_filer_position_changes AS
WITH ordered_positions AS (
    SELECT
        fp.report_period,
        fp.cik,
        fp.canonical_filer_name,
        fp.security_reference_key,
        fp.issuer_name,
        fp.class_title,
        fp.cusip,
        fp.figi,
        fp.put_call_key,
        fp.shares_principal_type_key,
        fp.total_value_usd,
        fp.total_value_reported,
        fp.total_shares_principal_amount,
        LAG(fp.report_period) OVER position_window AS previous_report_period,
        LAG(fp.total_value_usd) OVER position_window AS previous_value_usd,
        LAG(fp.total_shares_principal_amount) OVER position_window AS previous_shares_principal_amount
    FROM thirteenf_filer_positions fp
    WINDOW position_window AS (
        PARTITION BY
            fp.cik,
            fp.security_reference_key,
            fp.put_call_key,
            fp.shares_principal_type_key
        ORDER BY fp.report_period
    )
)
SELECT
    report_period,
    previous_report_period,
    cik,
    canonical_filer_name,
    security_reference_key,
    issuer_name,
    class_title,
    cusip,
    figi,
    put_call_key,
    shares_principal_type_key,
    total_value_usd AS current_value_usd,
    COALESCE(previous_value_usd, 0) AS previous_value_usd,
    total_value_usd - COALESCE(previous_value_usd, 0) AS delta_value_usd,
    total_shares_principal_amount AS current_shares_principal_amount,
    COALESCE(previous_shares_principal_amount, 0) AS previous_shares_principal_amount,
    total_shares_principal_amount - COALESCE(previous_shares_principal_amount, 0)
        AS delta_shares_principal_amount
FROM ordered_positions;

CREATE UNIQUE INDEX thirteenf_filer_position_changes_identity_idx
    ON thirteenf_filer_position_changes (
        report_period,
        cik,
        security_reference_key,
        put_call_key,
        shares_principal_type_key
    );

CREATE INDEX thirteenf_filer_position_changes_report_period_cik_delta_idx
    ON thirteenf_filer_position_changes (report_period, cik, delta_value_usd DESC);

CREATE INDEX thirteenf_filer_position_changes_report_period_issuer_delta_idx
    ON thirteenf_filer_position_changes (report_period, issuer_name, delta_value_usd DESC);

CREATE INDEX thirteenf_filer_position_changes_report_period_cusip_delta_idx
    ON thirteenf_filer_position_changes (report_period, cusip, delta_value_usd DESC);

CREATE INDEX thirteenf_filer_position_changes_report_period_figi_delta_idx
    ON thirteenf_filer_position_changes (report_period, figi, delta_value_usd DESC);
