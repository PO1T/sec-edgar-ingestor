CREATE TABLE IF NOT EXISTS ingestion_runs (
    id BIGSERIAL PRIMARY KEY,
    filing_family TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    from_date DATE,
    to_date DATE,
    details_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
    filing_family TEXT NOT NULL,
    mode TEXT NOT NULL,
    last_processed_filing_date DATE,
    last_processed_accession TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (filing_family, mode)
);

CREATE TABLE IF NOT EXISTS filers (
    cik TEXT PRIMARY KEY,
    filer_name TEXT NOT NULL,
    latest_form_type TEXT,
    first_seen_filed_date DATE,
    last_seen_filed_date DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS filings (
    accession_number TEXT PRIMARY KEY,
    filing_family TEXT NOT NULL,
    form_type TEXT NOT NULL,
    cik TEXT NOT NULL REFERENCES filers (cik),
    company_name TEXT NOT NULL,
    filed_date DATE NOT NULL,
    period_of_report DATE,
    acceptance_datetime TIMESTAMPTZ,
    archive_path TEXT NOT NULL,
    submission_url TEXT NOT NULL,
    filing_directory_url TEXT NOT NULL,
    index_url TEXT,
    primary_document_filename TEXT,
    information_table_filename TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS filings_family_filed_date_idx
    ON filings (filing_family, filed_date);

CREATE INDEX IF NOT EXISTS filings_cik_filed_date_idx
    ON filings (cik, filed_date);

CREATE TABLE IF NOT EXISTS filing_artifacts (
    id BIGSERIAL PRIMARY KEY,
    accession_number TEXT NOT NULL REFERENCES filings (accession_number) ON DELETE CASCADE,
    role TEXT NOT NULL,
    source_url TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    local_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    content_type TEXT,
    byte_size BIGINT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (accession_number, role)
);

CREATE TABLE IF NOT EXISTS filing_processing (
    accession_number TEXT NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    status TEXT NOT NULL,
    artifact_fingerprint TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    PRIMARY KEY (accession_number, parser_name, parser_version)
);

CREATE TABLE IF NOT EXISTS security_references (
    security_reference_key TEXT PRIMARY KEY,
    issuer_name TEXT NOT NULL,
    class_title TEXT NOT NULL,
    cusip TEXT NOT NULL,
    figi TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS thirteenf_filings (
    accession_number TEXT PRIMARY KEY REFERENCES filings (accession_number) ON DELETE CASCADE,
    submission_type TEXT NOT NULL,
    report_period DATE NOT NULL,
    report_calendar_or_quarter DATE,
    is_notice BOOLEAN NOT NULL DEFAULT FALSE,
    is_amendment BOOLEAN NOT NULL DEFAULT FALSE,
    amendment_type TEXT,
    amendment_number INTEGER,
    filing_manager_name TEXT,
    street1 TEXT,
    street2 TEXT,
    city TEXT,
    state_or_country TEXT,
    zip_code TEXT,
    report_type TEXT,
    form13f_file_number TEXT,
    crd_number TEXT,
    sec_file_number TEXT,
    provide_info_for_instruction5 BOOLEAN,
    additional_information TEXT,
    other_included_managers_count INTEGER,
    table_entry_total INTEGER,
    table_value_total_reported NUMERIC(20, 2),
    table_value_total_unit TEXT,
    table_value_total_usd NUMERIC(20, 2),
    is_confidential_omitted BOOLEAN,
    signature_name TEXT,
    signature_title TEXT,
    signature_phone TEXT,
    signature_city TEXT,
    signature_state_or_country TEXT,
    signature_date DATE,
    parser_version TEXT NOT NULL,
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS thirteenf_other_managers (
    id BIGSERIAL PRIMARY KEY,
    accession_number TEXT NOT NULL REFERENCES thirteenf_filings (accession_number) ON DELETE CASCADE,
    manager_sequence INTEGER,
    manager_name TEXT,
    cik TEXT,
    form13f_file_number TEXT,
    crd_number TEXT,
    sec_file_number TEXT
);

CREATE INDEX IF NOT EXISTS thirteenf_other_managers_accession_idx
    ON thirteenf_other_managers (accession_number);

CREATE TABLE IF NOT EXISTS thirteenf_holdings (
    accession_number TEXT NOT NULL REFERENCES thirteenf_filings (accession_number) ON DELETE CASCADE,
    holding_sequence INTEGER NOT NULL,
    security_reference_key TEXT NOT NULL REFERENCES security_references (security_reference_key),
    issuer_name TEXT NOT NULL,
    class_title TEXT NOT NULL,
    cusip TEXT NOT NULL,
    figi TEXT,
    value_reported NUMERIC(20, 2),
    value_unit TEXT NOT NULL,
    value_usd NUMERIC(20, 2),
    shares_principal_amount NUMERIC(20, 2),
    shares_principal_type TEXT,
    put_call TEXT,
    investment_discretion TEXT,
    other_manager TEXT,
    voting_authority_sole NUMERIC(20, 2),
    voting_authority_shared NUMERIC(20, 2),
    voting_authority_none NUMERIC(20, 2),
    PRIMARY KEY (accession_number, holding_sequence)
);

CREATE INDEX IF NOT EXISTS thirteenf_holdings_security_reference_idx
    ON thirteenf_holdings (security_reference_key);

CREATE INDEX IF NOT EXISTS thirteenf_holdings_cusip_idx
    ON thirteenf_holdings (cusip);

CREATE OR REPLACE VIEW thirteenf_effective_filings AS
SELECT
    ranked.accession_number,
    ranked.cik,
    ranked.company_name,
    ranked.form_type,
    ranked.report_period,
    ranked.report_calendar_or_quarter,
    ranked.filing_manager_name,
    ranked.is_notice,
    ranked.is_amendment,
    ranked.table_entry_total,
    ranked.table_value_total_usd,
    ranked.filed_date,
    ranked.acceptance_datetime
FROM (
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
        tf.table_entry_total,
        tf.table_value_total_usd,
        f.filed_date,
        f.acceptance_datetime,
        ROW_NUMBER() OVER (
            PARTITION BY
                f.cik,
                tf.report_period,
                CASE WHEN tf.is_notice THEN 'NOTICE' ELSE 'HOLDINGS' END
            ORDER BY
                COALESCE(f.acceptance_datetime, f.filed_date::TIMESTAMPTZ) DESC,
                f.accession_number DESC
        ) AS version_rank
    FROM thirteenf_filings tf
    INNER JOIN filings f
        ON f.accession_number = tf.accession_number
) AS ranked
WHERE ranked.version_rank = 1;

CREATE OR REPLACE VIEW thirteenf_effective_holdings AS
SELECT
    ef.cik,
    ef.company_name,
    ef.report_period,
    ef.filing_manager_name,
    h.*
FROM thirteenf_effective_filings ef
INNER JOIN thirteenf_holdings h
    ON h.accession_number = ef.accession_number
WHERE ef.is_notice = FALSE;
