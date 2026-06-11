CREATE TABLE IF NOT EXISTS periodic_embedding_profiles (
    embedding_profile_id BIGSERIAL PRIMARY KEY,
    profile_name TEXT NOT NULL UNIQUE,
    provider_kind TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0),
    distance_metric TEXT NOT NULL DEFAULT 'cosine',
    input_template_version TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS periodic_embedding_profiles_active_idx
    ON periodic_embedding_profiles (profile_name, active);

INSERT INTO periodic_embedding_profiles (
    profile_name,
    provider_kind,
    embedding_model,
    embedding_dimension,
    distance_metric,
    input_template_version,
    active
)
VALUES (
    'default',
    'openai-compatible',
    'text-embedding-3-small',
    1536,
    'cosine',
    'periodic-chunk-v1',
    TRUE
)
ON CONFLICT (profile_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS periodic_embedding_runs (
    embedding_run_id BIGSERIAL PRIMARY KEY,
    embedding_profile_id BIGINT REFERENCES periodic_embedding_profiles (embedding_profile_id),
    status TEXT NOT NULL,
    filters_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    chunks_embedded INTEGER NOT NULL DEFAULT 0,
    chunks_skipped INTEGER NOT NULL DEFAULT 0,
    chunks_failed INTEGER NOT NULL DEFAULT 0,
    last_chunk_id BIGINT,
    error_summary TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS periodic_embedding_runs_profile_idx
    ON periodic_embedding_runs (embedding_profile_id, started_at DESC);

DO $$
DECLARE
    default_profile_id BIGINT;
BEGIN
    SELECT embedding_profile_id
    INTO default_profile_id
    FROM periodic_embedding_profiles
    WHERE profile_name = 'default';

    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS periodic_chunk_embeddings (
        chunk_id BIGINT NOT NULL REFERENCES periodic_report_chunks (chunk_id) ON DELETE CASCADE,
        embedding_profile_id BIGINT NOT NULL REFERENCES periodic_embedding_profiles (embedding_profile_id) ON DELETE CASCADE,
        content_hash TEXT NOT NULL,
        embedding_input_hash TEXT NOT NULL,
        embedding vector,
        last_usage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (chunk_id, embedding_profile_id)
    );

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'periodic_chunk_embeddings'
          AND column_name = 'embedding_model'
    ) THEN
        INSERT INTO periodic_embedding_profiles (
            profile_name,
            provider_kind,
            embedding_model,
            embedding_dimension,
            distance_metric,
            input_template_version,
            active
        )
        SELECT DISTINCT
            CASE
                WHEN embedding_model = 'text-embedding-3-small' AND embedding_dimension = 1536
                    THEN 'default'
                ELSE 'legacy-' || md5(embedding_model || ':' || embedding_dimension::TEXT)
            END,
            'openai-compatible',
            embedding_model,
            embedding_dimension,
            'cosine',
            'periodic-chunk-v1',
            TRUE
        FROM periodic_chunk_embeddings
        ON CONFLICT (profile_name) DO NOTHING;

        ALTER TABLE periodic_chunk_embeddings
            ADD COLUMN IF NOT EXISTS embedding_profile_id BIGINT;
        ALTER TABLE periodic_chunk_embeddings
            ADD COLUMN IF NOT EXISTS embedding_input_hash TEXT;
        ALTER TABLE periodic_chunk_embeddings
            ADD COLUMN IF NOT EXISTS last_usage_json JSONB NOT NULL DEFAULT '{}'::JSONB;

        UPDATE periodic_chunk_embeddings e
        SET embedding_profile_id = p.embedding_profile_id
        FROM periodic_embedding_profiles p
        WHERE e.embedding_profile_id IS NULL
          AND p.embedding_model = e.embedding_model
          AND p.embedding_dimension = e.embedding_dimension;

        UPDATE periodic_chunk_embeddings
        SET embedding_profile_id = default_profile_id
        WHERE embedding_profile_id IS NULL;

        UPDATE periodic_chunk_embeddings
        SET embedding_input_hash = content_hash
        WHERE embedding_input_hash IS NULL;

        ALTER TABLE periodic_chunk_embeddings
            ALTER COLUMN embedding_profile_id SET NOT NULL;
        ALTER TABLE periodic_chunk_embeddings
            ALTER COLUMN embedding_input_hash SET NOT NULL;

        ALTER TABLE periodic_chunk_embeddings
            DROP CONSTRAINT IF EXISTS periodic_chunk_embeddings_pkey;
        ALTER TABLE periodic_chunk_embeddings
            ADD PRIMARY KEY (chunk_id, embedding_profile_id);

        ALTER TABLE periodic_chunk_embeddings
            DROP COLUMN IF EXISTS embedding_model;
        ALTER TABLE periodic_chunk_embeddings
            DROP COLUMN IF EXISTS embedding_dimension;
    END IF;

    DROP INDEX IF EXISTS periodic_chunk_embeddings_model_idx;
    DROP INDEX IF EXISTS periodic_chunk_embeddings_hnsw_idx;

    CREATE INDEX IF NOT EXISTS periodic_chunk_embeddings_profile_idx
        ON periodic_chunk_embeddings (embedding_profile_id, content_hash, embedding_input_hash);

    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS periodic_chunk_embeddings_default_1536_hnsw_idx
         ON periodic_chunk_embeddings
         USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
         WHERE embedding_profile_id = %s',
        default_profile_id
    );
EXCEPTION
    WHEN insufficient_privilege OR undefined_file OR feature_not_supported THEN
        RAISE NOTICE 'pgvector is unavailable; semantic periodic retrieval can be enabled later.';
    WHEN OTHERS THEN
        RAISE NOTICE 'Skipping periodic embedding vector upgrade: %', SQLERRM;
END $$;
