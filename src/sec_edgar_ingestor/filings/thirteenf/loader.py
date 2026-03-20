from __future__ import annotations

import hashlib
from typing import Iterable

from sec_edgar_ingestor.filings.thirteenf.models import ParsedThirteenF
from sec_edgar_ingestor.filings.thirteenf.parser import PARSER_NAME, PARSER_VERSION
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
    filing: ParsedThirteenF,
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
                filing.filing_manager_name or filing.company_name,
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
                "13F",
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
            INSERT INTO thirteenf_filings (
                accession_number,
                submission_type,
                report_period,
                report_calendar_or_quarter,
                is_notice,
                is_amendment,
                amendment_type,
                amendment_number,
                filing_manager_name,
                street1,
                street2,
                city,
                state_or_country,
                zip_code,
                report_type,
                form13f_file_number,
                crd_number,
                sec_file_number,
                provide_info_for_instruction5,
                additional_information,
                other_included_managers_count,
                table_entry_total,
                table_value_total_reported,
                table_value_total_unit,
                table_value_total_usd,
                is_confidential_omitted,
                signature_name,
                signature_title,
                signature_phone,
                signature_city,
                signature_state_or_country,
                signature_date,
                parser_version,
                normalized_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, NOW()
            )
            ON CONFLICT (accession_number)
            DO UPDATE SET
                submission_type = EXCLUDED.submission_type,
                report_period = EXCLUDED.report_period,
                report_calendar_or_quarter = EXCLUDED.report_calendar_or_quarter,
                is_notice = EXCLUDED.is_notice,
                is_amendment = EXCLUDED.is_amendment,
                amendment_type = EXCLUDED.amendment_type,
                amendment_number = EXCLUDED.amendment_number,
                filing_manager_name = EXCLUDED.filing_manager_name,
                street1 = EXCLUDED.street1,
                street2 = EXCLUDED.street2,
                city = EXCLUDED.city,
                state_or_country = EXCLUDED.state_or_country,
                zip_code = EXCLUDED.zip_code,
                report_type = EXCLUDED.report_type,
                form13f_file_number = EXCLUDED.form13f_file_number,
                crd_number = EXCLUDED.crd_number,
                sec_file_number = EXCLUDED.sec_file_number,
                provide_info_for_instruction5 = EXCLUDED.provide_info_for_instruction5,
                additional_information = EXCLUDED.additional_information,
                other_included_managers_count = EXCLUDED.other_included_managers_count,
                table_entry_total = EXCLUDED.table_entry_total,
                table_value_total_reported = EXCLUDED.table_value_total_reported,
                table_value_total_unit = EXCLUDED.table_value_total_unit,
                table_value_total_usd = EXCLUDED.table_value_total_usd,
                is_confidential_omitted = EXCLUDED.is_confidential_omitted,
                signature_name = EXCLUDED.signature_name,
                signature_title = EXCLUDED.signature_title,
                signature_phone = EXCLUDED.signature_phone,
                signature_city = EXCLUDED.signature_city,
                signature_state_or_country = EXCLUDED.signature_state_or_country,
                signature_date = EXCLUDED.signature_date,
                parser_version = EXCLUDED.parser_version,
                normalized_at = NOW()
            """,
            (
                filing.accession_number,
                filing.submission_type,
                filing.period_of_report,
                filing.report_calendar_or_quarter,
                filing.is_notice,
                filing.is_amendment,
                filing.amendment_type,
                filing.amendment_number,
                filing.filing_manager_name,
                filing.street1,
                filing.street2,
                filing.city,
                filing.state_or_country,
                filing.zip_code,
                filing.report_type,
                filing.form13f_file_number,
                filing.crd_number,
                filing.sec_file_number,
                filing.provide_info_for_instruction5,
                filing.additional_information,
                filing.other_included_managers_count,
                filing.table_entry_total,
                filing.table_value_total_reported,
                filing.table_value_total_unit,
                filing.table_value_total_usd,
                filing.is_confidential_omitted,
                filing.signature_name,
                filing.signature_title,
                filing.signature_phone,
                filing.signature_city,
                filing.signature_state_or_country,
                filing.signature_date,
                PARSER_VERSION,
            ),
        )

        cursor.execute(
            "DELETE FROM thirteenf_other_managers WHERE accession_number = %s",
            (filing.accession_number,),
        )
        for manager in filing.other_managers:
            cursor.execute(
                """
                INSERT INTO thirteenf_other_managers (
                    accession_number,
                    manager_sequence,
                    manager_name,
                    cik,
                    form13f_file_number,
                    crd_number,
                    sec_file_number
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    filing.accession_number,
                    manager.manager_sequence,
                    manager.manager_name,
                    manager.cik,
                    manager.form13f_file_number,
                    manager.crd_number,
                    manager.sec_file_number,
                ),
            )

        cursor.execute(
            "DELETE FROM thirteenf_holdings WHERE accession_number = %s",
            (filing.accession_number,),
        )
        for holding in filing.holdings:
            cursor.execute(
                """
                INSERT INTO security_references (
                    security_reference_key,
                    issuer_name,
                    class_title,
                    cusip,
                    figi,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (security_reference_key)
                DO UPDATE SET
                    issuer_name = EXCLUDED.issuer_name,
                    class_title = EXCLUDED.class_title,
                    cusip = EXCLUDED.cusip,
                    figi = EXCLUDED.figi
                """,
                (
                    holding.security_reference_key,
                    holding.issuer_name,
                    holding.class_title,
                    holding.cusip,
                    holding.figi,
                ),
            )
            cursor.execute(
                """
                INSERT INTO thirteenf_holdings (
                    accession_number,
                    holding_sequence,
                    security_reference_key,
                    issuer_name,
                    class_title,
                    cusip,
                    figi,
                    value_reported,
                    value_unit,
                    value_usd,
                    shares_principal_amount,
                    shares_principal_type,
                    put_call,
                    investment_discretion,
                    other_manager,
                    voting_authority_sole,
                    voting_authority_shared,
                    voting_authority_none
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    filing.accession_number,
                    holding.holding_sequence,
                    holding.security_reference_key,
                    holding.issuer_name,
                    holding.class_title,
                    holding.cusip,
                    holding.figi,
                    holding.value_reported,
                    holding.value_unit,
                    holding.value_usd,
                    holding.shares_principal_amount,
                    holding.shares_principal_type,
                    holding.put_call,
                    holding.investment_discretion,
                    holding.other_manager,
                    holding.voting_authority_sole,
                    holding.voting_authority_shared,
                    holding.voting_authority_none,
                ),
            )
