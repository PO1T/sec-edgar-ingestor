from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class DatabaseDependencyError(RuntimeError):
    """Raised when psycopg is not installed but a DB operation is requested."""


@contextmanager
def connect_db(dsn: str) -> Iterator[object]:
    try:
        import psycopg
    except ImportError as exc:
        raise DatabaseDependencyError(
            "psycopg is required for database operations; install project dependencies first"
        ) from exc

    connection = psycopg.connect(dsn)
    try:
        yield connection
    finally:
        connection.close()
