ALTER TABLE thirteenf_filings
    ADD COLUMN IF NOT EXISTS amendment_type_code TEXT;

UPDATE thirteenf_filings
SET amendment_type_code = CASE
        WHEN is_amendment = FALSE THEN NULL
        WHEN UPPER(REGEXP_REPLACE(BTRIM(COALESCE(amendment_type, '')), '[[:space:]]+', ' ', 'g'))
             IN ('RESTATEMENT', 'NEW HOLDINGS')
            THEN UPPER(REGEXP_REPLACE(BTRIM(COALESCE(amendment_type, '')), '[[:space:]]+', ' ', 'g'))
        ELSE 'UNKNOWN_AMENDMENT_TYPE'
    END;

CREATE OR REPLACE VIEW thirteenf_effective_filings AS
WITH filing_events AS (
    SELECT
        tf.accession_number,
        f.cik,
        f.company_name,
        f.form_type,
        tf.report_period,
        tf.report_calendar_or_quarter,
        tf.filing_manager_name,
        tf.is_notice,
        tf.is_amendment,
        tf.amendment_type_code,
        tf.table_entry_total,
        tf.table_value_total_usd,
        f.filed_date,
        f.acceptance_datetime,
        COALESCE(f.acceptance_datetime, f.filed_date::TIMESTAMPTZ) AS sort_datetime,
        CASE
            WHEN tf.is_notice THEN 'NOTICE'
            WHEN f.form_type = '13F-HR' THEN 'RESET'
            WHEN f.form_type = '13F-HR/A'
             AND tf.amendment_type_code = 'RESTATEMENT' THEN 'RESET'
            WHEN f.form_type = '13F-HR/A'
             AND tf.amendment_type_code = 'NEW HOLDINGS' THEN 'SUPPLEMENT'
            ELSE NULL
        END AS effective_event_kind
    FROM thirteenf_filings tf
    INNER JOIN filings f
        ON f.accession_number = tf.accession_number
),
ordered_holding_events AS (
    SELECT
        filing_events.*,
        SUM(CASE WHEN effective_event_kind = 'RESET' THEN 1 ELSE 0 END) OVER (
            PARTITION BY cik, report_period
            ORDER BY sort_datetime, accession_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS reset_group
    FROM filing_events
    WHERE is_notice = FALSE
),
holding_candidates AS (
    SELECT
        ordered_holding_events.*,
        MAX(reset_group) OVER (
            PARTITION BY cik, report_period
        ) AS latest_reset_group
    FROM ordered_holding_events
),
effective_holding_events AS (
    SELECT *
    FROM holding_candidates
    WHERE latest_reset_group > 0
      AND reset_group = latest_reset_group
      AND effective_event_kind IN ('RESET', 'SUPPLEMENT')
),
latest_holding_filings AS (
    SELECT
        effective_holding_events.*,
        ROW_NUMBER() OVER (
            PARTITION BY cik, report_period
            ORDER BY sort_datetime DESC, accession_number DESC
        ) AS version_rank
    FROM effective_holding_events
),
valid_notice_events AS (
    SELECT *
    FROM filing_events
    WHERE is_notice = TRUE
      AND (
          is_amendment = FALSE
          OR amendment_type_code IN ('RESTATEMENT', 'NEW HOLDINGS')
      )
),
latest_notice_filings AS (
    SELECT
        valid_notice_events.*,
        ROW_NUMBER() OVER (
            PARTITION BY cik, report_period
            ORDER BY sort_datetime DESC, accession_number DESC
        ) AS version_rank
    FROM valid_notice_events
)
SELECT
    accession_number,
    cik,
    company_name,
    form_type,
    report_period,
    report_calendar_or_quarter,
    filing_manager_name,
    is_notice,
    is_amendment,
    table_entry_total,
    table_value_total_usd,
    filed_date,
    acceptance_datetime
FROM latest_holding_filings
WHERE version_rank = 1
UNION ALL
SELECT
    accession_number,
    cik,
    company_name,
    form_type,
    report_period,
    report_calendar_or_quarter,
    filing_manager_name,
    is_notice,
    is_amendment,
    table_entry_total,
    table_value_total_usd,
    filed_date,
    acceptance_datetime
FROM latest_notice_filings
WHERE version_rank = 1;

CREATE OR REPLACE VIEW thirteenf_effective_holdings AS
WITH filing_events AS (
    SELECT
        tf.accession_number,
        f.cik,
        f.company_name,
        f.form_type,
        tf.report_period,
        tf.report_calendar_or_quarter,
        tf.filing_manager_name,
        tf.is_notice,
        tf.is_amendment,
        tf.amendment_type_code,
        tf.table_entry_total,
        tf.table_value_total_usd,
        f.filed_date,
        f.acceptance_datetime,
        COALESCE(f.acceptance_datetime, f.filed_date::TIMESTAMPTZ) AS sort_datetime,
        CASE
            WHEN tf.is_notice THEN 'NOTICE'
            WHEN f.form_type = '13F-HR' THEN 'RESET'
            WHEN f.form_type = '13F-HR/A'
             AND tf.amendment_type_code = 'RESTATEMENT' THEN 'RESET'
            WHEN f.form_type = '13F-HR/A'
             AND tf.amendment_type_code = 'NEW HOLDINGS' THEN 'SUPPLEMENT'
            ELSE NULL
        END AS effective_event_kind
    FROM thirteenf_filings tf
    INNER JOIN filings f
        ON f.accession_number = tf.accession_number
),
ordered_holding_events AS (
    SELECT
        filing_events.*,
        SUM(CASE WHEN effective_event_kind = 'RESET' THEN 1 ELSE 0 END) OVER (
            PARTITION BY cik, report_period
            ORDER BY sort_datetime, accession_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS reset_group
    FROM filing_events
    WHERE is_notice = FALSE
),
holding_candidates AS (
    SELECT
        ordered_holding_events.*,
        MAX(reset_group) OVER (
            PARTITION BY cik, report_period
        ) AS latest_reset_group
    FROM ordered_holding_events
),
effective_holding_events AS (
    SELECT *
    FROM holding_candidates
    WHERE latest_reset_group > 0
      AND reset_group = latest_reset_group
      AND effective_event_kind IN ('RESET', 'SUPPLEMENT')
)
SELECT
    ef.cik,
    ef.company_name,
    ef.report_period,
    ef.filing_manager_name,
    h.*
FROM effective_holding_events ef
INNER JOIN thirteenf_holdings h
    ON h.accession_number = ef.accession_number;
