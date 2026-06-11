from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

import httpx

from sec_edgar_ingestor.config import Settings


DEFAULT_PROFILE_NAME = "default"
EMBEDDING_PROVIDER_KIND = "openai-compatible"
EMBEDDING_DISTANCE_METRIC = "cosine"
EMBEDDING_INPUT_TEMPLATE_VERSION = "periodic-chunk-v1"
MAX_INDEXED_VECTOR_DIMENSIONS = 2000


class EmbeddingConfigurationError(RuntimeError):
    """Raised when embedding backfill is requested without configuration."""


class EmbeddingStoreUnavailable(RuntimeError):
    """Raised when the database does not expose the pgvector embedding table."""


@dataclass(frozen=True)
class EmbeddingProfile:
    embedding_profile_id: int
    profile_name: str
    provider_kind: str
    embedding_model: str
    embedding_dimension: int
    distance_metric: str
    input_template_version: str


@dataclass(frozen=True)
class EmbeddingChunk:
    chunk_id: int
    accession_number: str
    cik: str
    company_name: str
    ticker: str | None
    form_type: str
    filed_date: date | None
    report_period: date | None
    section_key: str
    section_title: str
    item_label: str | None
    chunk_ordinal: int
    chunk_text: str
    content_hash: str
    embedding_input: str
    embedding_input_hash: str


@dataclass(frozen=True)
class CandidateBatch:
    chunks: list[EmbeddingChunk]
    scanned_count: int
    skipped_count: int
    last_chunk_id: int | None


@dataclass(frozen=True)
class EmbeddingBatch:
    embeddings: list[list[float]]
    usage: dict[str, Any]


@dataclass(frozen=True)
class BackfillOptions:
    profile_name: str | None = None
    limit: int | None = None
    batch_size: int | None = None
    cik: str | None = None
    ticker: str | None = None
    form_type: str = "all"
    filed_from: date | None = None
    filed_to: date | None = None
    rebuild: bool = False
    dry_run: bool = False


class OpenAICompatibleEmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.embedding_api_key:
            raise EmbeddingConfigurationError("SEC_EDGAR_EMBEDDING_API_KEY is required")
        self._api_url = settings.embedding_api_url
        self._api_key = settings.embedding_api_key
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self._max_retries = settings.embedding_max_retries
        self._client = httpx.Client(timeout=settings.embedding_timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenAICompatibleEmbeddingClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def embed(self, inputs: Sequence[str]) -> EmbeddingBatch:
        if not inputs:
            return EmbeddingBatch(embeddings=[], usage={})

        payload = {
            "model": self._model,
            "input": list(inputs),
            "dimensions": self._dimensions,
        }
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.post(
                    self._api_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                return _parse_embedding_response(
                    response.json(),
                    expected_count=len(inputs),
                    expected_dimensions=self._dimensions,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                if attempt == self._max_retries:
                    raise
            except httpx.HTTPError:
                if attempt == self._max_retries:
                    raise
            time.sleep(min(2 ** (attempt - 1), 8))
        raise EmbeddingConfigurationError("Embedding request failed after retries")


def _parse_embedding_response(
    payload: dict[str, Any],
    *,
    expected_count: int,
    expected_dimensions: int,
) -> EmbeddingBatch:
    data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
    embeddings = [list(item["embedding"]) for item in data]
    if len(embeddings) != expected_count:
        raise EmbeddingConfigurationError(
            f"Embedding provider returned {len(embeddings)} vectors for {expected_count} inputs"
        )
    for index, embedding in enumerate(embeddings):
        if len(embedding) != expected_dimensions:
            raise EmbeddingConfigurationError(
                f"Embedding {index} has {len(embedding)} dimensions, expected {expected_dimensions}"
            )
    usage = payload.get("usage")
    return EmbeddingBatch(
        embeddings=embeddings,
        usage=usage if isinstance(usage, dict) else {},
    )


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _normalize_profile_name(value: str | None) -> str:
    cleaned = (value or DEFAULT_PROFILE_NAME).strip()
    if not cleaned:
        return DEFAULT_PROFILE_NAME
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", cleaned):
        raise EmbeddingConfigurationError(
            "Embedding profile names may only contain letters, numbers, dots, dashes, and underscores"
        )
    return cleaned


def _normalize_cik(cik: str | None) -> str | None:
    if cik is None:
        return None
    cleaned = cik.strip().lstrip("0")
    return cleaned or "0"


def _normalize_form_type(form_type: str) -> str:
    normalized = form_type.strip().upper()
    if normalized == "ALL":
        return "all"
    if normalized not in {"10-K", "10-Q"}:
        raise EmbeddingConfigurationError("form_type must be one of: all, 10-K, 10-Q")
    return normalized


def embedding_store_available(connection: object) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'periodic_chunk_embeddings'
            )
            AND EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'periodic_embedding_profiles'
            )
            """
        )
        return bool(cursor.fetchone()[0])


def get_or_create_embedding_profile(
    connection: object,
    *,
    profile_name: str,
    model: str,
    dimensions: int,
) -> EmbeddingProfile:
    profile_name = _normalize_profile_name(profile_name)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                embedding_profile_id,
                profile_name,
                provider_kind,
                embedding_model,
                embedding_dimension,
                distance_metric,
                input_template_version,
                active
            FROM periodic_embedding_profiles
            WHERE profile_name = %s
            """,
            (profile_name,),
        )
        existing = cursor.fetchone()
        if existing:
            changed = (
                existing[2] != EMBEDDING_PROVIDER_KIND
                or existing[3] != model
                or existing[4] != dimensions
                or existing[5] != EMBEDDING_DISTANCE_METRIC
                or existing[6] != EMBEDDING_INPUT_TEMPLATE_VERSION
                or existing[7] is not True
            )
            if changed:
                cursor.execute(
                    """
                    UPDATE periodic_embedding_profiles
                    SET
                        provider_kind = %s,
                        embedding_model = %s,
                        embedding_dimension = %s,
                        distance_metric = %s,
                        input_template_version = %s,
                        active = TRUE,
                        updated_at = NOW()
                    WHERE embedding_profile_id = %s
                    RETURNING
                        embedding_profile_id,
                        profile_name,
                        provider_kind,
                        embedding_model,
                        embedding_dimension,
                        distance_metric,
                        input_template_version
                    """,
                    (
                        EMBEDDING_PROVIDER_KIND,
                        model,
                        dimensions,
                        EMBEDDING_DISTANCE_METRIC,
                        EMBEDDING_INPUT_TEMPLATE_VERSION,
                        existing[0],
                    ),
                )
                row = cursor.fetchone()
                cursor.execute(
                    "DELETE FROM periodic_chunk_embeddings WHERE embedding_profile_id = %s",
                    (existing[0],),
                )
            else:
                row = existing[:7]
        else:
            cursor.execute(
                """
                INSERT INTO periodic_embedding_profiles (
                profile_name,
                provider_kind,
                embedding_model,
                embedding_dimension,
                distance_metric,
                input_template_version,
                active,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())
            ON CONFLICT (profile_name)
            DO UPDATE SET
                provider_kind = EXCLUDED.provider_kind,
                embedding_model = EXCLUDED.embedding_model,
                embedding_dimension = EXCLUDED.embedding_dimension,
                distance_metric = EXCLUDED.distance_metric,
                input_template_version = EXCLUDED.input_template_version,
                active = TRUE,
                updated_at = NOW()
            RETURNING
                embedding_profile_id,
                profile_name,
                provider_kind,
                embedding_model,
                embedding_dimension,
                distance_metric,
                input_template_version
            """,
                (
                    profile_name,
                    EMBEDDING_PROVIDER_KIND,
                    model,
                    dimensions,
                    EMBEDDING_DISTANCE_METRIC,
                    EMBEDDING_INPUT_TEMPLATE_VERSION,
                ),
            )
            row = cursor.fetchone()
    connection.commit()
    return EmbeddingProfile(
        embedding_profile_id=row[0],
        profile_name=row[1],
        provider_kind=row[2],
        embedding_model=row[3],
        embedding_dimension=row[4],
        distance_metric=row[5],
        input_template_version=row[6],
    )


def enable_vector_for_profile(
    connection: object,
    *,
    profile_name: str,
    model: str,
    dimensions: int,
) -> EmbeddingProfile:
    if dimensions > MAX_INDEXED_VECTOR_DIMENSIONS:
        raise EmbeddingConfigurationError(
            f"pgvector HNSW indexes support vector dimensions up to {MAX_INDEXED_VECTOR_DIMENSIONS}; "
            "configure a smaller embedding dimension for this profile"
    )
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute(
            """
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
            )
            """
        )
    connection.commit()
    profile = get_or_create_embedding_profile(
        connection,
        profile_name=profile_name,
        model=model,
        dimensions=dimensions,
    )
    index_name = f"periodic_chunk_embeddings_p{profile.embedding_profile_id}_{dimensions}_hnsw_idx"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS periodic_chunk_embeddings_profile_idx
            ON periodic_chunk_embeddings (embedding_profile_id, content_hash, embedding_input_hash)
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON periodic_chunk_embeddings
            USING hnsw ((embedding::vector({dimensions})) vector_cosine_ops)
            WHERE embedding_profile_id = %s
            """,
            (profile.embedding_profile_id,),
        )
    connection.commit()
    return profile


def build_embedding_input(chunk: EmbeddingChunk | dict[str, Any]) -> str:
    getter = chunk.get if isinstance(chunk, dict) else lambda name, default=None: getattr(chunk, name, default)
    parts = [
        f"Company: {getter('company_name')}",
        f"CIK: {getter('cik')}",
        f"Ticker: {getter('ticker') or 'unknown'}",
        f"Form: {getter('form_type')}",
        f"Filed date: {getter('filed_date') or 'unknown'}",
        f"Report period: {getter('report_period') or 'unknown'}",
        f"Accession: {getter('accession_number')}",
        f"Section: {getter('section_key')} - {getter('section_title')}",
        f"Item: {getter('item_label') or 'unknown'}",
        f"Chunk ordinal: {getter('chunk_ordinal')}",
        "",
        str(getter("chunk_text")),
    ]
    return "\n".join(parts)


def embedding_input_hash(embedding_input: str) -> str:
    digest_input = f"{EMBEDDING_INPUT_TEMPLATE_VERSION}\n{embedding_input}"
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def _candidate_filters(options: BackfillOptions) -> tuple[list[str], list[object]]:
    where = ["c.chunk_id > %s"]
    params: list[object] = []
    cik = _normalize_cik(options.cik)
    if cik:
        where.append("f.cik = %s")
        params.append(cik)
    if options.ticker:
        where.append(
            """
            EXISTS (
                SELECT 1 FROM sec_company_tickers st
                WHERE st.cik = f.cik AND upper(st.ticker) = upper(%s)
            )
            """
        )
        params.append(options.ticker.strip())
    form_type = _normalize_form_type(options.form_type)
    if form_type != "all":
        where.append("f.form_type IN (%s, %s)")
        params.extend([form_type, f"{form_type}/A"])
    if options.filed_from:
        where.append("f.filed_date >= %s")
        params.append(options.filed_from)
    if options.filed_to:
        where.append("f.filed_date <= %s")
        params.append(options.filed_to)
    return where, params


def list_chunks_needing_embeddings(
    connection: object,
    *,
    profile: EmbeddingProfile,
    options: BackfillOptions,
    limit: int,
    after_chunk_id: int = 0,
) -> CandidateBatch:
    if not embedding_store_available(connection):
        raise EmbeddingStoreUnavailable("periodic_chunk_embeddings table is unavailable")
    where, params = _candidate_filters(options)
    scan_limit = max(limit * 5, limit)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                c.chunk_id,
                f.accession_number,
                f.cik,
                f.company_name,
                (SELECT MIN(t.ticker) FROM sec_company_tickers t WHERE t.cik = f.cik) AS ticker,
                f.form_type,
                f.filed_date,
                COALESCE(pr.report_period, f.period_of_report) AS report_period,
                c.section_key,
                c.section_title,
                c.item_label,
                c.chunk_ordinal,
                c.chunk_text,
                c.content_hash,
                e.content_hash AS existing_content_hash,
                e.embedding_input_hash AS existing_embedding_input_hash
            FROM periodic_report_chunks c
            INNER JOIN filings f
                ON f.accession_number = c.accession_number
            INNER JOIN periodic_reports pr
                ON pr.accession_number = c.accession_number
            LEFT JOIN periodic_chunk_embeddings e
                ON e.chunk_id = c.chunk_id
               AND e.embedding_profile_id = %s
            WHERE {' AND '.join(where)}
            ORDER BY c.chunk_id
            LIMIT %s
            """,
            tuple([profile.embedding_profile_id, after_chunk_id] + params + [scan_limit]),
        )
        rows = cursor.fetchall()

    chunks: list[EmbeddingChunk] = []
    skipped_count = 0
    last_chunk_id = None
    for row in rows:
        last_chunk_id = int(row[0])
        payload = {
            "chunk_id": int(row[0]),
            "accession_number": row[1],
            "cik": row[2],
            "company_name": row[3],
            "ticker": row[4],
            "form_type": row[5],
            "filed_date": row[6],
            "report_period": row[7],
            "section_key": row[8],
            "section_title": row[9],
            "item_label": row[10],
            "chunk_ordinal": int(row[11]),
            "chunk_text": row[12],
            "content_hash": row[13],
        }
        embedding_input = build_embedding_input(payload)
        input_hash = embedding_input_hash(embedding_input)
        if (
            not options.rebuild
            and row[14] == payload["content_hash"]
            and row[15] == input_hash
        ):
            skipped_count += 1
            continue
        chunks.append(
            EmbeddingChunk(
                **payload,
                embedding_input=embedding_input,
                embedding_input_hash=input_hash,
            )
        )
        if len(chunks) >= limit:
            break
    return CandidateBatch(
        chunks=chunks,
        scanned_count=len(rows),
        skipped_count=skipped_count,
        last_chunk_id=last_chunk_id,
    )


def create_embedding_run(
    connection: object,
    *,
    profile: EmbeddingProfile,
    options: BackfillOptions,
) -> int:
    filters = {
        "profile_name": profile.profile_name,
        "limit": options.limit,
        "batch_size": options.batch_size,
        "cik": options.cik,
        "ticker": options.ticker,
        "form_type": options.form_type,
        "filed_from": options.filed_from.isoformat() if options.filed_from else None,
        "filed_to": options.filed_to.isoformat() if options.filed_to else None,
        "rebuild": options.rebuild,
        "dry_run": options.dry_run,
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO periodic_embedding_runs (
                embedding_profile_id,
                status,
                filters_json
            )
            VALUES (%s, %s, %s::jsonb)
            RETURNING embedding_run_id
            """,
            (
                profile.embedding_profile_id,
                "dry_run" if options.dry_run else "running",
                json.dumps(filters),
            ),
        )
        run_id = int(cursor.fetchone()[0])
    connection.commit()
    return run_id


def update_embedding_run(
    connection: object,
    *,
    run_id: int,
    chunks_embedded: int,
    chunks_skipped: int,
    chunks_failed: int,
    last_chunk_id: int | None,
    status: str | None = None,
    error_summary: str | None = None,
) -> None:
    finished_sql = ", finished_at = NOW()" if status in {"completed", "failed", "dry_run"} else ""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE periodic_embedding_runs
            SET
                chunks_embedded = %s,
                chunks_skipped = %s,
                chunks_failed = %s,
                last_chunk_id = COALESCE(%s, last_chunk_id),
                status = COALESCE(%s, status),
                error_summary = COALESCE(%s, error_summary)
                {finished_sql}
            WHERE embedding_run_id = %s
            """,
            (
                chunks_embedded,
                chunks_skipped,
                chunks_failed,
                last_chunk_id,
                status,
                error_summary,
                run_id,
            ),
        )
    connection.commit()


def upsert_chunk_embeddings(
    connection: object,
    *,
    profile: EmbeddingProfile,
    chunks: Sequence[EmbeddingChunk],
    embeddings: Sequence[Sequence[float]],
    usage: dict[str, Any],
) -> None:
    with connection.cursor() as cursor:
        for chunk, embedding in zip(chunks, embeddings):
            cursor.execute(
                """
                INSERT INTO periodic_chunk_embeddings (
                    chunk_id,
                    embedding_profile_id,
                    content_hash,
                    embedding_input_hash,
                    embedding,
                    last_usage_json,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb, NOW(), NOW())
                ON CONFLICT (chunk_id, embedding_profile_id)
                DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    embedding_input_hash = EXCLUDED.embedding_input_hash,
                    embedding = EXCLUDED.embedding,
                    last_usage_json = EXCLUDED.last_usage_json,
                    updated_at = NOW()
                """,
                (
                    chunk.chunk_id,
                    profile.embedding_profile_id,
                    chunk.content_hash,
                    chunk.embedding_input_hash,
                    vector_literal(embedding),
                    json.dumps(usage),
                ),
            )
    connection.commit()


def run_periodic_embedding_backfill(
    settings: Settings,
    *,
    limit: int | None = None,
    options: BackfillOptions | None = None,
) -> int:
    resolved_options = options or BackfillOptions(limit=limit)
    if limit is not None and options is not None:
        resolved_options = BackfillOptions(**{**options.__dict__, "limit": limit})
    if not settings.embeddings_enabled and not resolved_options.dry_run:
        raise EmbeddingConfigurationError("SEC_EDGAR_EMBEDDINGS_ENABLED must be true")

    from sec_edgar_ingestor.db.connection import connect_db

    batch_size = resolved_options.batch_size or settings.embedding_batch_size
    total_limit = resolved_options.limit
    total_embedded = 0
    total_skipped = 0
    total_failed = 0
    after_chunk_id = 0

    with connect_db(settings.require_db()) as connection:
        if not embedding_store_available(connection):
            raise EmbeddingStoreUnavailable(
                "periodic_chunk_embeddings table is unavailable; install pgvector and rerun migrations"
            )
        profile = get_or_create_embedding_profile(
            connection,
            profile_name=resolved_options.profile_name or settings.embedding_profile_name,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        run_id = create_embedding_run(
            connection,
            profile=profile,
            options=resolved_options,
        )
        try:
            client_context = (
                None
                if resolved_options.dry_run
                else OpenAICompatibleEmbeddingClient(settings)
            )
            with (client_context if client_context is not None else _null_context()) as client:
                while True:
                    limit_progress = total_skipped if resolved_options.dry_run else total_embedded
                    remaining = None if total_limit is None else total_limit - limit_progress
                    if remaining is not None and remaining <= 0:
                        break
                    batch_limit = min(batch_size, remaining) if remaining is not None else batch_size
                    batch = list_chunks_needing_embeddings(
                        connection,
                        profile=profile,
                        options=resolved_options,
                        limit=batch_limit,
                        after_chunk_id=after_chunk_id,
                    )
                    total_skipped += batch.skipped_count
                    if batch.last_chunk_id is not None:
                        after_chunk_id = batch.last_chunk_id
                    if not batch.chunks:
                        update_embedding_run(
                            connection,
                            run_id=run_id,
                            chunks_embedded=total_embedded,
                            chunks_skipped=total_skipped,
                            chunks_failed=total_failed,
                            last_chunk_id=batch.last_chunk_id,
                        )
                        if batch.scanned_count == 0:
                            break
                        continue
                    if resolved_options.dry_run:
                        total_skipped += len(batch.chunks)
                        print(
                            json.dumps(
                                {
                                    "embedding_run_id": run_id,
                                    "dry_run": True,
                                    "candidate_chunks": total_skipped,
                                }
                            )
                        )
                    else:
                        assert client is not None
                        embedding_batch = client.embed([chunk.embedding_input for chunk in batch.chunks])
                        upsert_chunk_embeddings(
                            connection,
                            profile=profile,
                            chunks=batch.chunks,
                            embeddings=embedding_batch.embeddings,
                            usage=embedding_batch.usage,
                        )
                        total_embedded += len(batch.chunks)
                        print(
                            json.dumps(
                                {
                                    "embedding_run_id": run_id,
                                    "embedded_chunks": total_embedded,
                                    "skipped_chunks": total_skipped,
                                    "last_chunk_id": after_chunk_id,
                                }
                            )
                        )
                    update_embedding_run(
                        connection,
                        run_id=run_id,
                        chunks_embedded=total_embedded,
                        chunks_skipped=total_skipped,
                        chunks_failed=total_failed,
                        last_chunk_id=after_chunk_id,
                    )
            update_embedding_run(
                connection,
                run_id=run_id,
                chunks_embedded=total_embedded,
                chunks_skipped=total_skipped,
                chunks_failed=total_failed,
                last_chunk_id=after_chunk_id or None,
                status="dry_run" if resolved_options.dry_run else "completed",
            )
        except Exception as exc:
            total_failed += 1
            update_embedding_run(
                connection,
                run_id=run_id,
                chunks_embedded=total_embedded,
                chunks_skipped=total_skipped,
                chunks_failed=total_failed,
                last_chunk_id=after_chunk_id or None,
                status="failed",
                error_summary=str(exc),
            )
            raise
    return 0


class _null_context:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_: object) -> None:
        return None
