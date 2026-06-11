from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sec_edgar_ingestor.filings.periodic.loader import upsert_parsed_filing
from sec_edgar_ingestor.filings.periodic.models import (
    ParsedPeriodicReport,
    PeriodicChunk,
    PeriodicSection,
    XbrlFact,
)
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


class PeriodicLoaderTestCase(unittest.TestCase):
    def test_upsert_replaces_periodic_children(self) -> None:
        filing = ParsedPeriodicReport(
            accession_number="0000123456-24-000010",
            form_type="10-K",
            cik="123456",
            company_name="Example Foods Inc.",
            filed_date=date(2025, 2, 1),
            archive_path="archive.txt",
            submission_url="https://example/submission.txt",
            filing_directory_url="https://example",
            index_url="https://example/index.json",
            period_of_report=date(2024, 12, 31),
            acceptance_datetime=datetime(2025, 2, 1, 9, 0, 0),
            primary_document_filename="primary.htm",
            information_table_filename=None,
            report_period=date(2024, 12, 31),
            fiscal_year=2024,
            fiscal_period="FY",
            is_amendment=False,
            primary_document_title="Example 10-K",
            sections=[
                PeriodicSection(
                    section_key="risk_factors",
                    item_label="Item 1A",
                    section_title="Risk Factors",
                    char_start=0,
                    char_end=20,
                    text_content="Risk factors text",
                )
            ],
            chunks=[
                PeriodicChunk(
                    section_key="risk_factors",
                    item_label="Item 1A",
                    section_title="Risk Factors",
                    chunk_ordinal=1,
                    char_start=0,
                    char_end=20,
                    chunk_text="Risk factors text",
                    content_hash="a" * 64,
                )
            ],
            xbrl_facts=[
                XbrlFact(
                    concept="us-gaap:Revenues",
                    namespace_prefix="us-gaap",
                    local_name="Revenues",
                    context_ref="FY2024",
                    unit_ref="usd",
                    decimals="-6",
                    scale=6,
                    raw_value="1",
                    numeric_value=Decimal("1000000"),
                    fact_value=None,
                    period_start=None,
                    period_end=date(2024, 12, 31),
                    instant=None,
                )
            ],
        )
        connection = RecordingConnection()
        artifact = StoredArtifact(
            role="primary_document",
            source_url="https://example/primary.htm",
            original_filename="primary.htm",
            local_path=Path("/tmp/primary.htm"),
            sha256="b" * 64,
            content_type="text/html",
            byte_size=100,
        )

        upsert_parsed_filing(connection, filing=filing, artifacts=[artifact])

        executed_sql = "\n".join(statement for statement, _ in connection.statements)
        self.assertIn("INSERT INTO periodic_reports", executed_sql)
        self.assertIn("DELETE FROM periodic_report_sections", executed_sql)
        self.assertIn("DELETE FROM periodic_report_chunks", executed_sql)
        self.assertIn("DELETE FROM periodic_report_xbrl_facts", executed_sql)


if __name__ == "__main__":
    unittest.main()
