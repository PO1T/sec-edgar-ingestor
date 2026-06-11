from __future__ import annotations

import unittest
from pathlib import Path

from sec_edgar_ingestor.filings.thirteenf.discovery import parse_submission_documents
from sec_edgar_ingestor.filings.periodic.discovery import select_periodic_documents


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "periodic"


class PeriodicDiscoveryTestCase(unittest.TestCase):
    def test_selects_primary_html_and_xbrl_artifacts(self) -> None:
        documents = parse_submission_documents(
            (FIXTURES_DIR / "submission_10k.txt").read_text(encoding="utf-8")
        )

        selection = select_periodic_documents("10-K", documents)

        self.assertEqual(selection.primary_document.filename, "exfoods-20241231.htm")
        self.assertEqual(len(selection.xbrl_documents), 1)
        self.assertEqual(selection.xbrl_documents[0].doc_type, "EX-101.INS")


if __name__ == "__main__":
    unittest.main()
