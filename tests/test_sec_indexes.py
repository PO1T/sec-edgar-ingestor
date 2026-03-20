from __future__ import annotations

import unittest
from datetime import date

from sec_edgar_ingestor.sec.indexes import (
    IndexEntry,
    daily_index_urls,
    parse_master_idx,
    quarterly_index_urls,
)


MASTER_INDEX_SAMPLE = """Description:           Master Index of EDGAR Dissemination Feed
Last Data Received:    May 15, 2024
Comments:              webmaster@sec.gov
Anonymous FTP:         ftp://ftp.sec.gov/edgar/
Cloud HTTP:            https://www.sec.gov/Archives/

--------------------------------------------------------------------------------
1000045|NICHOLAS APPLEGATE INSTITUTIONAL FUNDS|N-CSR|2024-05-15|edgar/data/1000045/000089843224000123/0000898432-24-000123.txt
1067983|EXAMPLE CAPITAL LP|13F-HR|2024-05-15|edgar/data/1067983/000106798324000001/0001067983-24-000001.txt
1067983|EXAMPLE CAPITAL LP|13F-NT|2024-05-16|edgar/data/1067983/000106798324000002/0001067983-24-000002.txt
"""

DAILY_INDEX_SAMPLE = """Description:           Master Index of EDGAR Dissemination Feed
Last Data Received:    May 17, 2024
Comments:              webmaster@sec.gov
Anonymous FTP:         ftp://ftp.sec.gov/edgar/
Cloud HTTP:            https://www.sec.gov/Archives/

--------------------------------------------------------------------------------
1067983|EXAMPLE CAPITAL LP|13F-HR|20240517|edgar/data/1067983/000106798324000001/0001067983-24-000001.txt
"""


class IndexParsingTestCase(unittest.TestCase):
    def test_parse_master_idx(self) -> None:
        entries = parse_master_idx(MASTER_INDEX_SAMPLE)

        self.assertEqual(len(entries), 3)
        self.assertIsInstance(entries[1], IndexEntry)
        self.assertEqual(entries[1].accession_number, "0001067983-24-000001")
        self.assertEqual(
            entries[1].directory_index_url,
            "https://www.sec.gov/Archives/edgar/data/1067983/000106798324000001/000106798324000001/index.json",
        )

    def test_parse_master_idx_supports_compact_dates(self) -> None:
        entries = parse_master_idx(DAILY_INDEX_SAMPLE)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].filed_date, date(2024, 5, 17))

    def test_quarterly_index_urls_cover_range(self) -> None:
        urls = quarterly_index_urls(date(2024, 1, 1), date(2024, 8, 31))
        self.assertEqual(
            urls,
            [
                "https://www.sec.gov/Archives/edgar/full-index/2024/QTR1/master.idx",
                "https://www.sec.gov/Archives/edgar/full-index/2024/QTR2/master.idx",
                "https://www.sec.gov/Archives/edgar/full-index/2024/QTR3/master.idx",
            ],
        )

    def test_daily_index_urls_skip_weekends(self) -> None:
        urls = daily_index_urls(date(2024, 5, 17), date(2024, 5, 20))
        self.assertEqual(
            urls,
            [
                "https://www.sec.gov/Archives/edgar/daily-index/2024/QTR2/master.20240517.idx",
                "https://www.sec.gov/Archives/edgar/daily-index/2024/QTR2/master.20240520.idx",
            ],
        )


if __name__ == "__main__":
    unittest.main()
