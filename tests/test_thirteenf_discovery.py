from __future__ import annotations

import unittest
from pathlib import Path

from sec_edgar_ingestor.filings.thirteenf.discovery import (
    parse_submission_documents,
    parse_submission_header,
    select_thirteenf_documents,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "13f"


class SubmissionDiscoveryTestCase(unittest.TestCase):
    def test_discovers_holdings_documents(self) -> None:
        submission_text = (FIXTURES_DIR / "submission_hr.txt").read_text(encoding="utf-8")

        header = parse_submission_header(submission_text)
        documents = parse_submission_documents(submission_text)
        primary, information = select_thirteenf_documents("13F-HR", documents)

        self.assertEqual(header.accession_number, "0001067983-24-000001")
        self.assertEqual(header.acceptance_datetime.isoformat(), "2024-05-15T12:30:45")
        self.assertEqual(primary.filename, "primary_doc.xml")
        self.assertEqual(information.filename, "infotable.xml")

    def test_discovers_notice_documents(self) -> None:
        submission_text = (FIXTURES_DIR / "submission_nt.txt").read_text(encoding="utf-8")

        documents = parse_submission_documents(submission_text)
        primary, information = select_thirteenf_documents("13F-NT", documents)

        self.assertEqual(primary.filename, "notice_doc.xml")
        self.assertIsNone(information)


if __name__ == "__main__":
    unittest.main()
