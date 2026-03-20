from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Iterable


@dataclass(frozen=True)
class Migration:
    version: str
    sql: str


def _migration_files() -> Iterable[Migration]:
    migrations_dir = files("sec_edgar_ingestor.db").joinpath("migrations")
    for entry in sorted(migrations_dir.iterdir(), key=lambda path: path.name):
        if entry.name.endswith(".sql"):
            yield Migration(version=entry.name, sql=entry.read_text(encoding="utf-8"))


def apply_migrations(connection: object) -> list[str]:
    applied: list[str] = []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute("SELECT version FROM schema_migrations")
        existing = {row[0] for row in cursor.fetchall()}

        for migration in _migration_files():
            if migration.version in existing:
                continue
            cursor.execute(migration.sql)
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (migration.version,),
            )
            applied.append(migration.version)

    connection.commit()
    return applied
