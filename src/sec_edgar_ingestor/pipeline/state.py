from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sec_edgar_ingestor.pipeline.modes import CheckpointValue
from sec_edgar_ingestor.sec.indexes import IndexEntry
from sec_edgar_ingestor.storage.artifact_store import StoredArtifact


@dataclass(frozen=True)
class FilingRecord:
    accession_number: str
    form_type: str
    cik: str
    company_name: str
    filed_date: date
    archive_path: str
    submission_url: str
    filing_directory_url: str
    index_url: str | None
    primary_document_filename: str | None
    information_table_filename: str | None

    def to_index_entry(self) -> IndexEntry:
        return IndexEntry(
            cik=self.cik,
            company_name=self.company_name,
            form_type=self.form_type,
            filed_date=self.filed_date,
            archive_path=self.archive_path,
        )


def start_ingestion_run(
    connection: object,
    *,
    filing_family: str,
    mode: str,
    from_date: date | None,
    to_date: date | None,
    details_json: str,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_runs (
                filing_family,
                mode,
                status,
                from_date,
                to_date,
                details_json
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (filing_family, mode, "RUNNING", from_date, to_date, details_json),
        )
        run_id = cursor.fetchone()[0]
    connection.commit()
    return run_id


def finish_ingestion_run(
    connection: object,
    *,
    run_id: int,
    status: str,
    details_json: str,
    error_message: str | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ingestion_runs
            SET completed_at = NOW(),
                status = %s,
                details_json = %s::jsonb,
                error_message = %s
            WHERE id = %s
            """,
            (status, details_json, error_message, run_id),
        )
    connection.commit()


def load_checkpoint(connection: object, *, filing_family: str, mode: str) -> CheckpointValue | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT last_processed_filing_date, last_processed_accession
            FROM ingestion_checkpoints
            WHERE filing_family = %s AND mode = %s
            """,
            (filing_family, mode),
        )
        row = cursor.fetchone()

    if row is None:
        return None
    return CheckpointValue(
        last_processed_filing_date=row[0],
        last_processed_accession=row[1],
    )


def save_checkpoint(
    connection: object,
    *,
    filing_family: str,
    mode: str,
    filed_date: date,
    accession_number: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_checkpoints (
                filing_family,
                mode,
                last_processed_filing_date,
                last_processed_accession,
                updated_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (filing_family, mode)
            DO UPDATE SET
                last_processed_filing_date = EXCLUDED.last_processed_filing_date,
                last_processed_accession = EXCLUDED.last_processed_accession,
                updated_at = NOW()
            """,
            (filing_family, mode, filed_date, accession_number),
        )
    connection.commit()


def list_filings_for_reprocess(
    connection: object,
    *,
    filing_family: str,
    accession: str | None,
    from_date: date | None,
    to_date: date | None,
) -> list[FilingRecord]:
    clauses = ["filing_family = %s"]
    params: list[object] = [filing_family]
    if accession:
        clauses.append("accession_number = %s")
        params.append(accession)
    if from_date:
        clauses.append("filed_date >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("filed_date <= %s")
        params.append(to_date)

    sql = f"""
        SELECT
            accession_number,
            form_type,
            cik,
            company_name,
            filed_date,
            archive_path,
            submission_url,
            filing_directory_url,
            index_url,
            primary_document_filename,
            information_table_filename
        FROM filings
        WHERE {' AND '.join(clauses)}
        ORDER BY filed_date, accession_number
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    return [FilingRecord(*row) for row in rows]


def list_artifacts_for_accession(connection: object, accession_number: str) -> list[StoredArtifact]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT role, source_url, original_filename, local_path, sha256, content_type, byte_size
            FROM filing_artifacts
            WHERE accession_number = %s
            ORDER BY role
            """,
            (accession_number,),
        )
        rows = cursor.fetchall()

    return [
        StoredArtifact(
            role=row[0],
            source_url=row[1],
            original_filename=row[2],
            local_path=Path(row[3]),
            sha256=row[4],
            content_type=row[5],
            byte_size=row[6],
        )
        for row in rows
    ]
