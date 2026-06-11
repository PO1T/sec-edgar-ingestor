CREATE TABLE IF NOT EXISTS sec_company_tickers (
    cik TEXT NOT NULL REFERENCES filers (cik) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    company_title TEXT,
    exchange TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cik, ticker)
);

CREATE INDEX IF NOT EXISTS sec_company_tickers_ticker_idx
    ON sec_company_tickers (upper(ticker));

CREATE TABLE IF NOT EXISTS periodic_reports (
    accession_number TEXT PRIMARY KEY REFERENCES filings (accession_number) ON DELETE CASCADE,
    report_period DATE,
    fiscal_year INTEGER,
    fiscal_period TEXT,
    is_amendment BOOLEAN NOT NULL DEFAULT FALSE,
    primary_document_title TEXT,
    section_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    xbrl_fact_count INTEGER NOT NULL DEFAULT 0,
    parser_version TEXT NOT NULL,
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS periodic_reports_period_idx
    ON periodic_reports (report_period, accession_number);

CREATE TABLE IF NOT EXISTS periodic_report_sections (
    accession_number TEXT NOT NULL REFERENCES periodic_reports (accession_number) ON DELETE CASCADE,
    section_key TEXT NOT NULL,
    item_label TEXT,
    section_title TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text_content TEXT NOT NULL,
    PRIMARY KEY (accession_number, section_key)
);

CREATE INDEX IF NOT EXISTS periodic_report_sections_key_idx
    ON periodic_report_sections (section_key);

CREATE TABLE IF NOT EXISTS periodic_report_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    accession_number TEXT NOT NULL REFERENCES periodic_reports (accession_number) ON DELETE CASCADE,
    section_key TEXT NOT NULL,
    item_label TEXT,
    section_title TEXT NOT NULL,
    chunk_ordinal INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (accession_number, section_key, chunk_ordinal)
);

CREATE INDEX IF NOT EXISTS periodic_report_chunks_accession_idx
    ON periodic_report_chunks (accession_number);

CREATE INDEX IF NOT EXISTS periodic_report_chunks_section_idx
    ON periodic_report_chunks (section_key);

CREATE INDEX IF NOT EXISTS periodic_report_chunks_fts_idx
    ON periodic_report_chunks
    USING GIN (to_tsvector('english', chunk_text));

CREATE TABLE IF NOT EXISTS periodic_report_xbrl_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    accession_number TEXT NOT NULL REFERENCES periodic_reports (accession_number) ON DELETE CASCADE,
    concept TEXT NOT NULL,
    namespace_prefix TEXT,
    local_name TEXT NOT NULL,
    context_ref TEXT,
    unit_ref TEXT,
    decimals TEXT,
    scale INTEGER,
    raw_value TEXT NOT NULL,
    numeric_value NUMERIC,
    fact_value TEXT,
    period_start DATE,
    period_end DATE,
    instant DATE,
    dimensions_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    source_section_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS periodic_report_xbrl_facts_accession_idx
    ON periodic_report_xbrl_facts (accession_number);

CREATE INDEX IF NOT EXISTS periodic_report_xbrl_facts_concept_idx
    ON periodic_report_xbrl_facts (concept);

CREATE INDEX IF NOT EXISTS periodic_report_xbrl_facts_local_name_idx
    ON periodic_report_xbrl_facts (local_name);

CREATE OR REPLACE VIEW periodic_report_summaries AS
SELECT
    f.accession_number,
    f.cik,
    f.company_name,
    t.ticker,
    t.tickers,
    f.form_type,
    f.filed_date,
    COALESCE(pr.report_period, f.period_of_report) AS report_period,
    f.acceptance_datetime,
    f.submission_url,
    f.filing_directory_url,
    f.primary_document_filename,
    pr.fiscal_year,
    pr.fiscal_period,
    pr.is_amendment,
    pr.primary_document_title,
    pr.section_count,
    pr.chunk_count,
    pr.xbrl_fact_count
FROM periodic_reports pr
INNER JOIN filings f
    ON f.accession_number = pr.accession_number
LEFT JOIN LATERAL (
    SELECT
        MIN(ticker) AS ticker,
        ARRAY_AGG(DISTINCT ticker ORDER BY ticker) AS tickers
    FROM sec_company_tickers
    WHERE cik = f.cik
) t ON true;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS periodic_chunk_embeddings (
        chunk_id BIGINT PRIMARY KEY REFERENCES periodic_report_chunks (chunk_id) ON DELETE CASCADE,
        embedding_model TEXT NOT NULL,
        embedding_dimension INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        embedding vector,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS periodic_chunk_embeddings_model_idx
        ON periodic_chunk_embeddings (embedding_model, embedding_dimension);

    BEGIN
        CREATE INDEX IF NOT EXISTS periodic_chunk_embeddings_hnsw_idx
            ON periodic_chunk_embeddings
            USING hnsw (embedding vector_cosine_ops);
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Skipping periodic_chunk_embeddings HNSW index: %', SQLERRM;
    END;
EXCEPTION
    WHEN insufficient_privilege OR undefined_file OR feature_not_supported THEN
        RAISE NOTICE 'pgvector is unavailable; semantic periodic retrieval can be enabled later.';
END $$;
