from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sec_edgar_ingestor.filings.thirteenf.parser import (
    UNKNOWN_AMENDMENT_TYPE,
    normalize_reported_value,
    parse_thirteenf,
    value_unit_for_filed_date,
)
from sec_edgar_ingestor.sec.indexes import IndexEntry


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "13f"


def _entry(form_type: str, filed_date: date, accession_suffix: str) -> IndexEntry:
    return IndexEntry(
        cik="1067983",
        company_name="Example Capital LP",
        form_type=form_type,
        filed_date=filed_date,
        archive_path=f"edgar/data/1067983/0001067983{accession_suffix}/{accession_suffix}.txt",
    )


class ThirteenFParserTestCase(unittest.TestCase):
    def test_parses_holdings_report(self) -> None:
        entry = IndexEntry(
            cik="1067983",
            company_name="Example Capital LP",
            form_type="13F-HR",
            filed_date=date(2024, 5, 15),
            archive_path="edgar/data/1067983/000106798324000001/0001067983-24-000001.txt",
        )
        primary_xml = (FIXTURES_DIR / "hr_primary.xml").read_bytes()
        info_xml = (FIXTURES_DIR / "hr_infotable.xml").read_bytes()

        parsed = parse_thirteenf(
            entry,
            submission_type="13F-HR",
            acceptance_datetime=datetime(2024, 5, 15, 12, 30, 45),
            primary_document_filename="primary_doc.xml",
            information_table_filename="infotable.xml",
            primary_xml=primary_xml,
            information_table_xml=info_xml,
            index_url=entry.directory_index_url,
        )

        self.assertFalse(parsed.is_notice)
        self.assertFalse(parsed.is_amendment)
        self.assertEqual(parsed.period_of_report, date(2024, 3, 31))
        self.assertEqual(parsed.table_value_total_unit, "USD")
        self.assertEqual(len(parsed.holdings), 2)
        self.assertEqual(parsed.holdings[0].value_usd, Decimal("150"))
        self.assertEqual(parsed.holdings[1].put_call, "PUT")

    def test_parses_amended_holdings_report(self) -> None:
        entry = IndexEntry(
            cik="1067983",
            company_name="Example Capital LP",
            form_type="13F-HR/A",
            filed_date=date(2024, 8, 14),
            archive_path="edgar/data/1067983/000106798324000003/0001067983-24-000003.txt",
        )

        parsed = parse_thirteenf(
            entry,
            submission_type="13F-HR/A",
            acceptance_datetime=datetime(2024, 8, 14, 11, 0, 0),
            primary_document_filename="primary_doc.xml",
            information_table_filename="infotable.xml",
            primary_xml=(FIXTURES_DIR / "hra_primary.xml").read_bytes(),
            information_table_xml=(FIXTURES_DIR / "hr_infotable.xml").read_bytes(),
            index_url=entry.directory_index_url,
        )

        self.assertTrue(parsed.is_amendment)
        self.assertEqual(parsed.amendment_type, "RESTATEMENT")
        self.assertEqual(parsed.amendment_type_code, "RESTATEMENT")

    def test_normalizes_new_holdings_amendment_type(self) -> None:
        entry = _entry("13F-HR/A", date(2024, 8, 14), "-24-000005")
        primary_xml = (FIXTURES_DIR / "hra_primary.xml").read_text(
            encoding="utf-8",
        ).replace("RESTATEMENT", "NEW HOLDINGS")

        parsed = parse_thirteenf(
            entry,
            submission_type="13F-HR/A",
            acceptance_datetime=datetime(2024, 8, 14, 11, 0, 0),
            primary_document_filename="primary_doc.xml",
            information_table_filename="infotable.xml",
            primary_xml=primary_xml.encode("utf-8"),
            information_table_xml=(FIXTURES_DIR / "hr_infotable.xml").read_bytes(),
            index_url=entry.directory_index_url,
        )

        self.assertTrue(parsed.is_amendment)
        self.assertEqual(parsed.amendment_type, "NEW HOLDINGS")
        self.assertEqual(parsed.amendment_type_code, "NEW HOLDINGS")

    def test_unknown_amendment_type_for_missing_blank_or_malformed_values(self) -> None:
        cases = [
            (None, "missing"),
            ("   ", "blank"),
            ("CORRECTION", "malformed"),
        ]
        template = (FIXTURES_DIR / "hra_primary.xml").read_text(encoding="utf-8")

        for amendment_type, label in cases:
            with self.subTest(label=label):
                if amendment_type is None:
                    primary_xml = template.replace(
                        "      <amendmentType>RESTATEMENT</amendmentType>\n",
                        "",
                    )
                else:
                    primary_xml = template.replace("RESTATEMENT", amendment_type)

                parsed = parse_thirteenf(
                    _entry("13F-HR/A", date(2024, 8, 14), f"-24-unknown-{label}"),
                    submission_type="13F-HR/A",
                    acceptance_datetime=datetime(2024, 8, 14, 11, 0, 0),
                    primary_document_filename="primary_doc.xml",
                    information_table_filename="infotable.xml",
                    primary_xml=primary_xml.encode("utf-8"),
                    information_table_xml=(FIXTURES_DIR / "hr_infotable.xml").read_bytes(),
                    index_url=None,
                )

                self.assertTrue(parsed.is_amendment)
                self.assertEqual(parsed.amendment_type_code, UNKNOWN_AMENDMENT_TYPE)

    def test_parses_notice_filing(self) -> None:
        entry = IndexEntry(
            cik="1067983",
            company_name="Example Capital LP",
            form_type="13F-NT",
            filed_date=date(2024, 5, 15),
            archive_path="edgar/data/1067983/000106798324000002/0001067983-24-000002.txt",
        )

        parsed = parse_thirteenf(
            entry,
            submission_type="13F-NT",
            acceptance_datetime=datetime(2024, 5, 15, 13, 0, 0),
            primary_document_filename="notice_doc.xml",
            information_table_filename=None,
            primary_xml=(FIXTURES_DIR / "nt_primary.xml").read_bytes(),
            information_table_xml=None,
            index_url=entry.directory_index_url,
        )

        self.assertTrue(parsed.is_notice)
        self.assertEqual(parsed.holdings, [])

    def test_parses_amended_notice_filing(self) -> None:
        entry = IndexEntry(
            cik="1067983",
            company_name="Example Capital LP",
            form_type="13F-NT/A",
            filed_date=date(2024, 8, 15),
            archive_path="edgar/data/1067983/000106798324000004/0001067983-24-000004.txt",
        )

        parsed = parse_thirteenf(
            entry,
            submission_type="13F-NT/A",
            acceptance_datetime=datetime(2024, 8, 15, 10, 0, 0),
            primary_document_filename="notice_doc.xml",
            information_table_filename=None,
            primary_xml=(FIXTURES_DIR / "nta_primary.xml").read_bytes(),
            information_table_xml=None,
            index_url=entry.directory_index_url,
        )

        self.assertTrue(parsed.is_notice)
        self.assertTrue(parsed.is_amendment)
        self.assertEqual(parsed.amendment_type_code, "RESTATEMENT")

    def test_normalizes_pre_2023_values(self) -> None:
        self.assertEqual(value_unit_for_filed_date(date(2022, 11, 14)), "THOUSANDS_USD")
        self.assertEqual(normalize_reported_value(Decimal("15"), date(2022, 11, 14)), Decimal("15000"))


if __name__ == "__main__":
    unittest.main()
