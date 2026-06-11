from __future__ import annotations

import hashlib
from typing import Iterable

from sec_edgar_ingestor.filings.periodic.models import ParsedPeriodicReport
from sec_edgar_ingestor.filings.periodic.parser import PARSER_NAME, PARSER_VERSION
from sec_edgar_ingestor.storage.artifact_store import StoredArtifact


def artifact_fingerprint(artifacts: Iterable[StoredArtifact]) -> str:
    digest = hashlib.sha256()
    for artifact in sorted(artifacts, key=lambda item: (item.role, item.original_filename)):
        digest.update(artifact.role.encode("utf-8"))
        digest.update(b":")
        digest.update(artifact.sha256.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def mark_processing_state(
    connection: object,
    *,
    accession_number: str,
    status: str,
    artifact_hash: str | None,
    error_message: str | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO filing_processing (
                accession_number,
                parser_name,
                parser_version,
                status,
                artifact_fingerprint,
                started_at,
                completed_at,
                error_message
            )
            VALUES (%s, %s, %s, %s, %s, NOW(), NULL, %s)
            ON CONFLICT (accession_number, parser_name, parser_version)
            DO UPDATE SET
                status = EXCLUDED.status,
                artifact_fingerprint = EXCLUDED.artifact_fingerprint,
                error_message = EXCLUDED.error_message,
                started_at = CASE
                    WHEN EXCLUDED.status = 'RUNNING' THEN NOW()
                    ELSE filing_processing.started_at
                END,
                completed_at = CASE
                    WHEN EXCLUDED.status IN ('SUCCESS', 'FAILED') THEN NOW()
                    ELSE NULL
                END
            """,
            (
                accession_number,
                PARSER_NAME,
                PARSER_VERSION,
                status,
                artifact_hash,
                error_message,
            ),
        )
    connection.commit()


def upsert_parsed_filing(
    connection: object,
    *,
    filing: ParsedPeriodicReport,
    artifacts: list[StoredArtifact],
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO filers (
                cik,
                filer_name,
                latest_form_type,
                first_seen_filed_date,
                last_seen_filed_date,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (cik)
            DO UPDATE SET
                filer_name = EXCLUDED.filer_name,
                latest_form_type = EXCLUDED.latest_form_type,
                first_seen_filed_date = COALESCE(
                    LEAST(filers.first_seen_filed_date, EXCLUDED.first_seen_filed_date),
                    EXCLUDED.first_seen_filed_date,
                    filers.first_seen_filed_date
                ),
                last_seen_filed_date = COALESCE(
                    GREATEST(filers.last_seen_filed_date, EXCLUDED.last_seen_filed_date),
                    EXCLUDED.last_seen_filed_date,
                    filers.last_seen_filed_date
                ),
                updated_at = NOW()
            """,
            (
                filing.cik,
                filing.company_name,
                filing.form_type,
                filing.filed_date,
                filing.filed_date,
            ),
        )

        cursor.execute(
            """
            INSERT INTO filings (
                accession_number,
                filing_family,
                form_type,
                cik,
                company_name,
                filed_date,
                period_of_report,
                acceptance_datetime,
                archive_path,
                submission_url,
                filing_directory_url,
                index_url,
                primary_document_filename,
                information_table_filename,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (accession_number)
            DO UPDATE SET
                filing_family = EXCLUDED.filing_family,
                form_type = EXCLUDED.form_type,
                cik = EXCLUDED.cik,
                company_name = EXCLUDED.company_name,
                filed_date = EXCLUDED.filed_date,
                period_of_report = EXCLUDED.period_of_report,
                acceptance_datetime = EXCLUDED.acceptance_datetime,
                archive_path = EXCLUDED.archive_path,
                submission_url = EXCLUDED.submission_url,
                filing_directory_url = EXCLUDED.filing_directory_url,
                index_url = EXCLUDED.index_url,
                primary_document_filename = EXCLUDED.primary_document_filename,
                information_table_filename = EXCLUDED.information_table_filename,
                updated_at = NOW()
            """,
            (
                filing.accession_number,
                "PERIODIC_REPORTS",
                filing.form_type,
                filing.cik,
                filing.company_name,
                filing.filed_date,
                filing.period_of_report,
                filing.acceptance_datetime,
                filing.archive_path,
                filing.submission_url,
                filing.filing_directory_url,
                filing.index_url,
                filing.primary_document_filename,
                filing.information_table_filename,
            ),
        )

        for artifact in artifacts:
            cursor.execute(
                """
                INSERT INTO filing_artifacts (
                    accession_number,
                    role,
                    source_url,
                    original_filename,
                    local_path,
                    sha256,
                    content_type,
                    byte_size,
                    fetched_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (accession_number, role)
                DO UPDATE SET
                    source_url = EXCLUDED.source_url,
                    original_filename = EXCLUDED.original_filename,
                    local_path = EXCLUDED.local_path,
                    sha256 = EXCLUDED.sha256,
                    content_type = EXCLUDED.content_type,
                    byte_size = EXCLUDED.byte_size,
                    fetched_at = NOW()
                """,
                (
                    filing.accession_number,
                    artifact.role,
                    artifact.source_url,
                    artifact.original_filename,
                    str(artifact.local_path),
                    artifact.sha256,
                    artifact.content_type,
                    artifact.byte_size,
                ),
            )

        cursor.execute(
            """
            INSERT INTO periodic_reports (
                accession_number,
                report_period,
                fiscal_year,
                fiscal_period,
                is_amendment,
                primary_document_title,
                section_count,
                chunk_count,
                xbrl_fact_count,
                parser_version,
                normalized_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (accession_number)
            DO UPDATE SET
                report_period = EXCLUDED.report_period,
                fiscal_year = EXCLUDED.fiscal_year,
                fiscal_period = EXCLUDED.fiscal_period,
                is_amendment = EXCLUDED.is_amendment,
                primary_document_title = EXCLUDED.primary_document_title,
                section_count = EXCLUDED.section_count,
                chunk_count = EXCLUDED.chunk_count,
                xbrl_fact_count = EXCLUDED.xbrl_fact_count,
                parser_version = EXCLUDED.parser_version,
                normalized_at = NOW()
            """,
            (
                filing.accession_number,
                filing.report_period,
                filing.fiscal_year,
                filing.fiscal_period,
                filing.is_amendment,
                filing.primary_document_title,
                len(filing.sections),
                len(filing.chunks),
                len(filing.xbrl_facts),
                PARSER_VERSION,
            ),
        )

        cursor.execute(
            "DELETE FROM periodic_report_sections WHERE accession_number = %s",
            (filing.accession_number,),
        )
        for section in filing.sections:
            cursor.execute(
                """
                INSERT INTO periodic_report_sections (
                    accession_number,
                    section_key,
                    item_label,
                    section_title,
                    char_start,
                    char_end,
                    text_content
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    filing.accession_number,
                    section.section_key,
                    section.item_label,
                    section.section_title,
                    section.char_start,
                    section.char_end,
                    section.text_content,
                ),
            )

        cursor.execute(
            "DELETE FROM periodic_report_chunks WHERE accession_number = %s",
            (filing.accession_number,),
        )
        for chunk in filing.chunks:
            cursor.execute(
                """
                INSERT INTO periodic_report_chunks (
                    accession_number,
                    section_key,
                    item_label,
                    section_title,
                    chunk_ordinal,
                    char_start,
                    char_end,
                    chunk_text,
                    content_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    filing.accession_number,
                    chunk.section_key,
                    chunk.item_label,
                    chunk.section_title,
                    chunk.chunk_ordinal,
                    chunk.char_start,
                    chunk.char_end,
                    chunk.chunk_text,
                    chunk.content_hash,
                ),
            )

        cursor.execute(
            "DELETE FROM periodic_report_xbrl_facts WHERE accession_number = %s",
            (filing.accession_number,),
        )
        for fact in filing.xbrl_facts:
            cursor.execute(
                """
                INSERT INTO periodic_report_xbrl_facts (
                    accession_number,
                    concept,
                    namespace_prefix,
                    local_name,
                    context_ref,
                    unit_ref,
                    decimals,
                    scale,
                    raw_value,
                    numeric_value,
                    fact_value,
                    period_start,
                    period_end,
                    instant,
                    dimensions_json,
                    source_section_key
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s
                )
                """,
                (
                    filing.accession_number,
                    fact.concept,
                    fact.namespace_prefix,
                    fact.local_name,
                    fact.context_ref,
                    fact.unit_ref,
                    fact.decimals,
                    fact.scale,
                    fact.raw_value,
                    fact.numeric_value,
                    fact.fact_value,
                    fact.period_start,
                    fact.period_end,
                    fact.instant,
                    fact.dimensions_json,
                    fact.source_section_key,
                ),
            )
