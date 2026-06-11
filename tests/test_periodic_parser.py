from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sec_edgar_ingestor.filings.periodic.parser import parse_periodic_report
from sec_edgar_ingestor.sec.indexes import IndexEntry


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "periodic"


def _entry(form_type: str) -> IndexEntry:
    return IndexEntry(
        cik="123456",
        company_name="Example Foods Inc.",
        form_type=form_type,
        filed_date=date(2025, 2, 1),
        archive_path="edgar/data/123456/000012345624000010/0000123456-24-000010.txt",
    )


class PeriodicParserTestCase(unittest.TestCase):
    def test_parses_10k_sections_chunks_and_xbrl_facts(self) -> None:
        parsed = parse_periodic_report(
            _entry("10-K"),
            acceptance_datetime=datetime(2025, 2, 1, 9, 0, 0),
            primary_document_filename="exfoods-20241231.htm",
            primary_document=(FIXTURES_DIR / "10k_primary.htm").read_bytes(),
            index_url="https://example/index.json",
            chunk_chars=180,
            chunk_overlap_chars=20,
        )

        section_keys = {section.section_key for section in parsed.sections}
        self.assertIn("risk_factors", section_keys)
        self.assertIn("mda", section_keys)
        self.assertIn("market_risk", section_keys)
        self.assertEqual(parsed.report_period, date(2024, 12, 31))
        self.assertEqual(parsed.fiscal_year, 2024)
        self.assertEqual(parsed.fiscal_period, "FY")
        self.assertGreaterEqual(len(parsed.chunks), len(parsed.sections))
        revenues = [fact for fact in parsed.xbrl_facts if fact.local_name == "Revenues"][0]
        self.assertEqual(revenues.numeric_value, Decimal("4250000000"))
        self.assertEqual(revenues.period_end, date(2024, 12, 31))

    def test_parses_10q_item_taxonomy(self) -> None:
        parsed = parse_periodic_report(
            _entry("10-Q"),
            acceptance_datetime=None,
            primary_document_filename="exfoods-20250331.htm",
            primary_document=(FIXTURES_DIR / "10q_primary.htm").read_bytes(),
        )

        section_keys = [section.section_key for section in parsed.sections]
        self.assertIn("financial_statements", section_keys)
        self.assertIn("controls", section_keys)
        self.assertIn("risk_factors", section_keys)
        self.assertEqual(parsed.fiscal_period, "Q1")


if __name__ == "__main__":
    unittest.main()
