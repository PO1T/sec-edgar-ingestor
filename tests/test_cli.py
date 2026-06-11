from __future__ import annotations

import unittest

from sec_edgar_ingestor.cli import build_parser


class CliParserTestCase(unittest.TestCase):
    def test_db_refresh_analytics_command_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["db", "refresh-analytics"])

        self.assertEqual(args.command, "db")
        self.assertEqual(args.db_command, "refresh-analytics")

    def test_ingest_skip_analytics_refresh_flag_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["ingest", "13f", "--mode", "dev", "--skip-analytics-refresh"]
        )

        self.assertTrue(args.skip_analytics_refresh)

    def test_reprocess_skip_analytics_refresh_flag_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["reprocess", "13f", "--accession", "0000000000-00-000001", "--skip-analytics-refresh"]
        )

        self.assertTrue(args.skip_analytics_refresh)

    def test_periodic_ingest_options_parse(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "ingest",
                "periodic",
                "--mode",
                "dev",
                "--form-type",
                "10-K",
                "--exclude-amendments",
            ]
        )

        self.assertEqual(args.filing_family, "periodic")
        self.assertEqual(args.form_type, "10-K")
        self.assertTrue(args.exclude_amendments)

    def test_periodic_embedding_backfill_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["embeddings", "backfill", "periodic", "--limit", "10"])

        self.assertEqual(args.embeddings_command, "backfill")
        self.assertEqual(args.embeddings_family, "periodic")
        self.assertEqual(args.limit, 10)


if __name__ == "__main__":
    unittest.main()
