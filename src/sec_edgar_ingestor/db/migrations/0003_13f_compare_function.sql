CREATE OR REPLACE FUNCTION thirteenf_compare_filer_holdings(
    p_cik TEXT,
    p_current_report_period DATE,
    p_prior_report_period DATE,
    p_position_filter TEXT DEFAULT 'all',
    p_put_call TEXT DEFAULT NULL
)
RETURNS TABLE (
    cik TEXT,
    canonical_filer_name TEXT,
    report_period DATE,
    previous_report_period DATE,
    security_reference_key TEXT,
    previous_security_reference_key TEXT,
    issuer_name TEXT,
    class_title TEXT,
    previous_class_title TEXT,
    cusip TEXT,
    previous_cusip TEXT,
    figi TEXT,
    previous_figi TEXT,
    put_call TEXT,
    shares_principal_type TEXT,
    current_accession_number TEXT,
    prior_accession_number TEXT,
    current_value_usd NUMERIC,
    prior_value_usd NUMERIC,
    value_change_usd NUMERIC,
    current_shares_principal_amount NUMERIC,
    prior_shares_principal_amount NUMERIC,
    share_change NUMERIC,
    new_position BOOLEAN,
    disposed_position BOOLEAN,
    match_strategy TEXT
)
LANGUAGE SQL
STABLE
AS $$
WITH current_positions AS (
    SELECT
        fp.*,
        ef.accession_number AS current_accession_number,
        COALESCE(NULLIF(fp.figi, ''), NULLIF(fp.cusip, '')) AS comparison_identifier,
        NULLIF(
            SPLIT_PART(
                REGEXP_REPLACE(UPPER(TRIM(fp.issuer_name)), '[^A-Z0-9]+', ' ', 'g'),
                ' ',
                1
            ),
            ''
        ) AS issuer_primary_token
    FROM thirteenf_filer_positions fp
    LEFT JOIN thirteenf_effective_filings ef
        ON ef.cik = fp.cik
       AND ef.report_period = fp.report_period
       AND ef.is_notice = FALSE
    WHERE fp.cik = p_cik
      AND fp.report_period = p_current_report_period
      AND (
          p_position_filter = 'all'
          OR (p_position_filter = 'shares_only' AND fp.put_call_key = 'NONE')
          OR (p_position_filter = 'options_only' AND fp.put_call_key <> 'NONE')
      )
      AND (p_put_call IS NULL OR fp.put_call_key = UPPER(p_put_call))
),
prior_positions AS (
    SELECT
        fp.*,
        ef.accession_number AS prior_accession_number,
        COALESCE(NULLIF(fp.figi, ''), NULLIF(fp.cusip, '')) AS comparison_identifier,
        NULLIF(
            SPLIT_PART(
                REGEXP_REPLACE(UPPER(TRIM(fp.issuer_name)), '[^A-Z0-9]+', ' ', 'g'),
                ' ',
                1
            ),
            ''
        ) AS issuer_primary_token
    FROM thirteenf_filer_positions fp
    LEFT JOIN thirteenf_effective_filings ef
        ON ef.cik = fp.cik
       AND ef.report_period = fp.report_period
       AND ef.is_notice = FALSE
    WHERE fp.cik = p_cik
      AND fp.report_period = p_prior_report_period
      AND (
          p_position_filter = 'all'
          OR (p_position_filter = 'shares_only' AND fp.put_call_key = 'NONE')
          OR (p_position_filter = 'options_only' AND fp.put_call_key <> 'NONE')
      )
      AND (p_put_call IS NULL OR fp.put_call_key = UPPER(p_put_call))
),
exact_matches AS (
    SELECT
        c.cik,
        COALESCE(c.canonical_filer_name, p.canonical_filer_name) AS canonical_filer_name,
        c.report_period,
        p.report_period AS previous_report_period,
        c.security_reference_key,
        p.security_reference_key AS previous_security_reference_key,
        c.issuer_name,
        c.class_title,
        p.class_title AS previous_class_title,
        c.cusip,
        p.cusip AS previous_cusip,
        c.figi,
        p.figi AS previous_figi,
        NULLIF(c.put_call_key, 'NONE') AS put_call,
        NULLIF(c.shares_principal_type_key, 'UNKNOWN') AS shares_principal_type,
        c.current_accession_number,
        p.prior_accession_number,
        c.total_value_usd AS current_value_usd,
        p.total_value_usd AS prior_value_usd,
        c.total_value_usd - p.total_value_usd AS value_change_usd,
        c.total_shares_principal_amount AS current_shares_principal_amount,
        p.total_shares_principal_amount AS prior_shares_principal_amount,
        c.total_shares_principal_amount - p.total_shares_principal_amount AS share_change,
        FALSE AS new_position,
        FALSE AS disposed_position,
        'exact_security_reference_key'::TEXT AS match_strategy
    FROM current_positions c
    INNER JOIN prior_positions p
        ON p.cik = c.cik
       AND p.security_reference_key = c.security_reference_key
       AND p.put_call_key = c.put_call_key
       AND p.shares_principal_type_key = c.shares_principal_type_key
),
unmatched_current AS (
    SELECT c.*
    FROM current_positions c
    LEFT JOIN prior_positions p
        ON p.cik = c.cik
       AND p.security_reference_key = c.security_reference_key
       AND p.put_call_key = c.put_call_key
       AND p.shares_principal_type_key = c.shares_principal_type_key
    WHERE p.security_reference_key IS NULL
),
unmatched_prior AS (
    SELECT p.*
    FROM prior_positions p
    LEFT JOIN current_positions c
        ON c.cik = p.cik
       AND c.security_reference_key = p.security_reference_key
       AND c.put_call_key = p.put_call_key
       AND c.shares_principal_type_key = p.shares_principal_type_key
    WHERE c.security_reference_key IS NULL
),
identifier_candidate_matches AS (
    SELECT
        c.cik,
        COALESCE(c.canonical_filer_name, p.canonical_filer_name) AS canonical_filer_name,
        c.report_period,
        p.report_period AS previous_report_period,
        c.security_reference_key,
        p.security_reference_key AS previous_security_reference_key,
        c.issuer_name,
        c.class_title,
        p.class_title AS previous_class_title,
        c.cusip,
        p.cusip AS previous_cusip,
        c.figi,
        p.figi AS previous_figi,
        NULLIF(c.put_call_key, 'NONE') AS put_call,
        NULLIF(c.shares_principal_type_key, 'UNKNOWN') AS shares_principal_type,
        c.current_accession_number,
        p.prior_accession_number,
        c.total_value_usd AS current_value_usd,
        p.total_value_usd AS prior_value_usd,
        c.total_value_usd - p.total_value_usd AS value_change_usd,
        c.total_shares_principal_amount AS current_shares_principal_amount,
        p.total_shares_principal_amount AS prior_shares_principal_amount,
        c.total_shares_principal_amount - p.total_shares_principal_amount AS share_change,
        COUNT(*) OVER (
            PARTITION BY c.cik, c.report_period, c.security_reference_key
        ) AS current_candidate_count,
        COUNT(*) OVER (
            PARTITION BY p.cik, c.report_period, p.security_reference_key
        ) AS prior_candidate_count
    FROM unmatched_current c
    INNER JOIN unmatched_prior p
        ON p.cik = c.cik
       AND p.put_call_key = c.put_call_key
       AND p.shares_principal_type_key = c.shares_principal_type_key
       AND p.comparison_identifier = c.comparison_identifier
       AND c.comparison_identifier IS NOT NULL
),
identifier_matches AS (
    SELECT
        cik,
        canonical_filer_name,
        report_period,
        previous_report_period,
        security_reference_key,
        previous_security_reference_key,
        issuer_name,
        class_title,
        previous_class_title,
        cusip,
        previous_cusip,
        figi,
        previous_figi,
        put_call,
        shares_principal_type,
        current_accession_number,
        prior_accession_number,
        current_value_usd,
        prior_value_usd,
        value_change_usd,
        current_shares_principal_amount,
        prior_shares_principal_amount,
        share_change,
        FALSE AS new_position,
        FALSE AS disposed_position,
        'figi_or_cusip'::TEXT AS match_strategy
    FROM identifier_candidate_matches
    WHERE current_candidate_count = 1
      AND prior_candidate_count = 1
),
remaining_current_after_identifier AS (
    SELECT c.*
    FROM unmatched_current c
    LEFT JOIN identifier_matches im
        ON im.cik = c.cik
       AND im.report_period = c.report_period
       AND im.security_reference_key = c.security_reference_key
    WHERE im.security_reference_key IS NULL
),
remaining_prior_after_identifier AS (
    SELECT p.*
    FROM unmatched_prior p
    LEFT JOIN identifier_matches im
        ON im.cik = p.cik
       AND im.previous_report_period = p.report_period
       AND im.previous_security_reference_key = p.security_reference_key
    WHERE im.previous_security_reference_key IS NULL
),
rename_candidate_matches AS (
    SELECT
        c.cik,
        COALESCE(c.canonical_filer_name, p.canonical_filer_name) AS canonical_filer_name,
        c.report_period,
        p.report_period AS previous_report_period,
        c.security_reference_key,
        p.security_reference_key AS previous_security_reference_key,
        c.issuer_name,
        c.class_title,
        p.class_title AS previous_class_title,
        c.cusip,
        p.cusip AS previous_cusip,
        c.figi,
        p.figi AS previous_figi,
        NULLIF(c.put_call_key, 'NONE') AS put_call,
        NULLIF(c.shares_principal_type_key, 'UNKNOWN') AS shares_principal_type,
        c.current_accession_number,
        p.prior_accession_number,
        c.total_value_usd AS current_value_usd,
        p.total_value_usd AS prior_value_usd,
        c.total_value_usd - p.total_value_usd AS value_change_usd,
        c.total_shares_principal_amount AS current_shares_principal_amount,
        p.total_shares_principal_amount AS prior_shares_principal_amount,
        c.total_shares_principal_amount - p.total_shares_principal_amount AS share_change,
        COUNT(*) OVER (
            PARTITION BY c.cik, c.report_period, c.security_reference_key
        ) AS current_candidate_count,
        COUNT(*) OVER (
            PARTITION BY p.cik, c.report_period, p.security_reference_key
        ) AS prior_candidate_count
    FROM remaining_current_after_identifier c
    INNER JOIN remaining_prior_after_identifier p
        ON p.cik = c.cik
       AND p.put_call_key = c.put_call_key
       AND p.shares_principal_type_key = c.shares_principal_type_key
       AND p.total_shares_principal_amount = c.total_shares_principal_amount
       AND c.total_shares_principal_amount IS NOT NULL
       AND c.total_shares_principal_amount <> 0
       AND ABS(c.total_value_usd - p.total_value_usd)
           <= GREATEST(c.total_value_usd, p.total_value_usd) * 0.5
       AND (
           p.issuer_name = c.issuer_name
           OR (
               p.issuer_primary_token IS NOT NULL
               AND p.issuer_primary_token = c.issuer_primary_token
           )
       )
),
rename_matches AS (
    SELECT
        cik,
        canonical_filer_name,
        report_period,
        previous_report_period,
        security_reference_key,
        previous_security_reference_key,
        issuer_name,
        class_title,
        previous_class_title,
        cusip,
        previous_cusip,
        figi,
        previous_figi,
        put_call,
        shares_principal_type,
        current_accession_number,
        prior_accession_number,
        current_value_usd,
        prior_value_usd,
        value_change_usd,
        current_shares_principal_amount,
        prior_shares_principal_amount,
        share_change,
        FALSE AS new_position,
        FALSE AS disposed_position,
        'issuer_or_primary_token_same_shares'::TEXT AS match_strategy
    FROM rename_candidate_matches
    WHERE current_candidate_count = 1
      AND prior_candidate_count = 1
),
remaining_current AS (
    SELECT c.*
    FROM remaining_current_after_identifier c
    LEFT JOIN rename_matches rm
        ON rm.cik = c.cik
       AND rm.report_period = c.report_period
       AND rm.security_reference_key = c.security_reference_key
    WHERE rm.security_reference_key IS NULL
),
remaining_prior AS (
    SELECT p.*
    FROM remaining_prior_after_identifier p
    LEFT JOIN rename_matches rm
        ON rm.cik = p.cik
       AND rm.previous_report_period = p.report_period
       AND rm.previous_security_reference_key = p.security_reference_key
    WHERE rm.previous_security_reference_key IS NULL
),
new_positions AS (
    SELECT
        c.cik,
        c.canonical_filer_name,
        c.report_period,
        p_prior_report_period AS previous_report_period,
        c.security_reference_key,
        NULL::TEXT AS previous_security_reference_key,
        c.issuer_name,
        c.class_title,
        NULL::TEXT AS previous_class_title,
        c.cusip,
        NULL::TEXT AS previous_cusip,
        c.figi,
        NULL::TEXT AS previous_figi,
        NULLIF(c.put_call_key, 'NONE') AS put_call,
        NULLIF(c.shares_principal_type_key, 'UNKNOWN') AS shares_principal_type,
        c.current_accession_number,
        NULL::TEXT AS prior_accession_number,
        c.total_value_usd AS current_value_usd,
        0::NUMERIC AS prior_value_usd,
        c.total_value_usd AS value_change_usd,
        c.total_shares_principal_amount AS current_shares_principal_amount,
        0::NUMERIC AS prior_shares_principal_amount,
        c.total_shares_principal_amount AS share_change,
        TRUE AS new_position,
        FALSE AS disposed_position,
        'new_position'::TEXT AS match_strategy
    FROM remaining_current c
),
disposed_positions AS (
    SELECT
        p.cik,
        p.canonical_filer_name,
        p_current_report_period AS report_period,
        p.report_period AS previous_report_period,
        p.security_reference_key,
        p.security_reference_key AS previous_security_reference_key,
        p.issuer_name,
        p.class_title,
        p.class_title AS previous_class_title,
        p.cusip,
        p.cusip AS previous_cusip,
        p.figi,
        p.figi AS previous_figi,
        NULLIF(p.put_call_key, 'NONE') AS put_call,
        NULLIF(p.shares_principal_type_key, 'UNKNOWN') AS shares_principal_type,
        NULL::TEXT AS current_accession_number,
        p.prior_accession_number,
        0::NUMERIC AS current_value_usd,
        p.total_value_usd AS prior_value_usd,
        0::NUMERIC - p.total_value_usd AS value_change_usd,
        0::NUMERIC AS current_shares_principal_amount,
        p.total_shares_principal_amount AS prior_shares_principal_amount,
        0::NUMERIC - p.total_shares_principal_amount AS share_change,
        FALSE AS new_position,
        TRUE AS disposed_position,
        'disposed_position'::TEXT AS match_strategy
    FROM remaining_prior p
)
SELECT * FROM exact_matches
UNION ALL
SELECT * FROM identifier_matches
UNION ALL
SELECT * FROM rename_matches
UNION ALL
SELECT * FROM new_positions
UNION ALL
SELECT * FROM disposed_positions
$$;
