from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sec_edgar_ingestor.filings.thirteenf.loader import artifact_fingerprint, upsert_parsed_filing
from sec_edgar_ingestor.filings.thirteenf.models import Holding, ParsedThirteenF
from sec_edgar_ingestor.storage.artifact_store import StoredArtifact


class RecordingCursor:
    def __init__(self, statements: list[tuple[str, tuple[object, ...] | None]]) -> None:
        self._statements = statements

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self._statements.append((sql, params))


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...] | None]] = []

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self.statements)


def _sample_parsed_filing() -> ParsedThirteenF:
    return ParsedThirteenF(
        accession_number="0001067983-24-000001",
        form_type="13F-HR",
        cik="1067983",
        company_name="Example Capital LP",
        filed_date=date(2024, 5, 15),
        archive_path="edgar/data/1067983/000106798324000001/0001067983-24-000001.txt",
        submission_url="https://www.sec.gov/Archives/edgar/data/1067983/000106798324000001/0001067983-24-000001.txt",
        filing_directory_url="https://www.sec.gov/Archives/edgar/data/1067983/000106798324000001",
        index_url="https://www.sec.gov/Archives/edgar/data/1067983/000106798324000001/index.json",
        period_of_report=date(2024, 3, 31),
        acceptance_datetime=datetime(2024, 5, 15, 12, 30, 45),
        primary_document_filename="primary_doc.xml",
        information_table_filename="infotable.xml",
        submission_type="13F-HR",
        report_calendar_or_quarter=date(2024, 3, 31),
        is_notice=False,
        is_amendment=False,
        amendment_type=None,
        amendment_type_code=None,
        amendment_number=None,
        filing_manager_name="Example Capital LP",
        street1="1 Main Street",
        street2=None,
        city="New York",
        state_or_country="NY",
        zip_code="10001",
        report_type="13F HOLDINGS REPORT",
        form13f_file_number="028-12345",
        crd_number="123456",
        sec_file_number="801-12345",
        provide_info_for_instruction5=False,
        additional_information=None,
        other_included_managers_count=0,
        table_entry_total=1,
        table_value_total_reported=Decimal("150"),
        table_value_total_unit="USD",
        table_value_total_usd=Decimal("150"),
        is_confidential_omitted=False,
        signature_name="Jane Example",
        signature_title="Chief Compliance Officer",
        signature_phone="555-555-0100",
        signature_city="New York",
        signature_state_or_country="NY",
        signature_date=date(2024, 5, 15),
        holdings=[
            Holding(
                holding_sequence=1,
                security_reference_key="security-key-1",
                issuer_name="APPLE INC",
                class_title="COM",
                cusip="037833100",
                figi="BBG000B9XRY4",
                value_reported=Decimal("150"),
                value_unit="USD",
                value_usd=Decimal("150"),
                shares_principal_amount=Decimal("10"),
                shares_principal_type="SH",
                put_call=None,
                investment_discretion="SOLE",
                other_manager=None,
                voting_authority_sole=Decimal("10"),
                voting_authority_shared=Decimal("0"),
                voting_authority_none=Decimal("0"),
            )
        ],
    )


class LoaderTestCase(unittest.TestCase):
    def test_artifact_fingerprint_is_order_insensitive(self) -> None:
        first = StoredArtifact(
            role="submission_text",
            source_url="https://example.com/submission.txt",
            original_filename="submission.txt",
            local_path=Path("/tmp/submission.txt"),
            sha256="a" * 64,
            content_type="text/plain",
            byte_size=10,
        )
        second = StoredArtifact(
            role="primary_xml",
            source_url="https://example.com/primary.xml",
            original_filename="primary.xml",
            local_path=Path("/tmp/primary.xml"),
            sha256="b" * 64,
            content_type="application/xml",
            byte_size=20,
        )

        self.assertEqual(
            artifact_fingerprint([first, second]),
            artifact_fingerprint([second, first]),
        )

    def test_upsert_parsed_filing_executes_replace_semantics_for_children(self) -> None:
        connection = RecordingConnection()
        parsed_filing = _sample_parsed_filing()
        artifacts = [
            StoredArtifact(
                role="submission_text",
                source_url=parsed_filing.submission_url,
                original_filename="submission.txt",
                local_path=Path("/tmp/submission.txt"),
                sha256="a" * 64,
                content_type="text/plain",
                byte_size=100,
            )
        ]

        upsert_parsed_filing(connection, filing=parsed_filing, artifacts=artifacts)

        executed_sql = "\n".join(statement for statement, _ in connection.statements)
        self.assertIn("DELETE FROM thirteenf_other_managers", executed_sql)
        self.assertIn("DELETE FROM thirteenf_holdings", executed_sql)
        self.assertIn("amendment_type_code", executed_sql)
        self.assertIn("INSERT INTO thirteenf_holdings", executed_sql)


if __name__ == "__main__":
    unittest.main()
