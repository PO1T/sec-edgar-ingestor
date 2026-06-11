from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

import httpx

from sec_edgar_ingestor.config import Settings


class EmbeddingConfigurationError(RuntimeError):
    """Raised when embedding backfill is requested without configuration."""


class EmbeddingStoreUnavailable(RuntimeError):
    """Raised when the database does not expose the pgvector embedding table."""


@dataclass(frozen=True)
class EmbeddingChunk:
    chunk_id: int
    chunk_text: str
    content_hash: str


class OpenAICompatibleEmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.embedding_api_key:
            raise EmbeddingConfigurationError("SEC_EDGAR_EMBEDDING_API_KEY is required")
        self._api_url = settings.embedding_api_url
        self._api_key = settings.embedding_api_key
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self._client = httpx.Client(timeout=settings.embedding_timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenAICompatibleEmbeddingClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        response = self._client.post(
            self._api_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "input": list(inputs),
                "dimensions": self._dimensions,
            },
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        return [list(item["embedding"]) for item in data]


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


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
            """
        )
        return bool(cursor.fetchone()[0])


def list_chunks_needing_embeddings(
    connection: object,
    *,
    model: str,
    dimensions: int,
    limit: int,
) -> list[EmbeddingChunk]:
    if not embedding_store_available(connection):
        raise EmbeddingStoreUnavailable("periodic_chunk_embeddings table is unavailable")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.chunk_id, c.chunk_text, c.content_hash
            FROM periodic_report_chunks c
            LEFT JOIN periodic_chunk_embeddings e
                ON e.chunk_id = c.chunk_id
               AND e.embedding_model = %s
               AND e.embedding_dimension = %s
               AND e.content_hash = c.content_hash
            WHERE e.chunk_id IS NULL
            ORDER BY c.chunk_id
            LIMIT %s
            """,
            (model, dimensions, limit),
        )
        rows = cursor.fetchall()
    return [EmbeddingChunk(chunk_id=row[0], chunk_text=row[1], content_hash=row[2]) for row in rows]


def upsert_chunk_embeddings(
    connection: object,
    *,
    chunks: Sequence[EmbeddingChunk],
    embeddings: Sequence[Sequence[float]],
    model: str,
    dimensions: int,
) -> None:
    with connection.cursor() as cursor:
        for chunk, embedding in zip(chunks, embeddings):
            cursor.execute(
                """
                INSERT INTO periodic_chunk_embeddings (
                    chunk_id,
                    embedding_model,
                    embedding_dimension,
                    content_hash,
                    embedding,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s::vector, NOW(), NOW())
                ON CONFLICT (chunk_id)
                DO UPDATE SET
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_dimension = EXCLUDED.embedding_dimension,
                    content_hash = EXCLUDED.content_hash,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW()
                """,
                (
                    chunk.chunk_id,
                    model,
                    dimensions,
                    chunk.content_hash,
                    vector_literal(embedding),
                ),
            )
    connection.commit()


def run_periodic_embedding_backfill(settings: Settings, *, limit: int | None = None) -> int:
    if not settings.embeddings_enabled:
        raise EmbeddingConfigurationError("SEC_EDGAR_EMBEDDINGS_ENABLED must be true")

    from sec_edgar_ingestor.db.connection import connect_db

    resolved_limit = limit or settings.embedding_batch_size
    total_embedded = 0
    with connect_db(settings.require_db()) as connection:
        if not embedding_store_available(connection):
            raise EmbeddingStoreUnavailable(
                "periodic_chunk_embeddings table is unavailable; install pgvector and rerun migrations"
            )
        with OpenAICompatibleEmbeddingClient(settings) as client:
            while True:
                chunks = list_chunks_needing_embeddings(
                    connection,
                    model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                    limit=min(settings.embedding_batch_size, resolved_limit - total_embedded),
                )
                if not chunks:
                    break
                embeddings = client.embed([chunk.chunk_text for chunk in chunks])
                upsert_chunk_embeddings(
                    connection,
                    chunks=chunks,
                    embeddings=embeddings,
                    model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                )
                total_embedded += len(chunks)
                print(json.dumps({"embedded_chunks": total_embedded}))
                if total_embedded >= resolved_limit:
                    break
    return 0
