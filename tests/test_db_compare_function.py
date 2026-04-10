from __future__ import annotations

import os
import unittest
from decimal import Decimal
from uuid import uuid4

from sec_edgar_ingestor.db.analytics import refresh_analytics_views
from sec_edgar_ingestor.db.migrations import apply_migrations


SEED_SQL = """
INSERT INTO filers (
    cik,
    filer_name,
    latest_form_type,
    first_seen_filed_date,
    last_seen_filed_date
)
VALUES
    ('1067983', 'Berkshire Hathaway Inc', '13F-HR', '2025-11-14', '2026-02-17');

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
    information_table_filename
)
VALUES
    (
        '0001193125-25-282901',
        '13F',
        '13F-HR',
        '1067983',
        'Berkshire Hathaway Inc',
        '2025-11-14',
        '2025-09-30',
        '2025-11-14T16:05:03Z',
        'archive/q3',
        'https://example/q3.txt',
        'https://example/q3/',
        'https://example/q3/index.json',
        'primary.xml',
        'info.xml'
    ),
    (
        '0001193125-26-054580',
        '13F',
        '13F-HR',
        '1067983',
        'Berkshire Hathaway Inc',
        '2026-02-17',
        '2025-12-31',
        '2026-02-17T16:05:04Z',
        'archive/q4',
        'https://example/q4.txt',
        'https://example/q4/',
        'https://example/q4/index.json',
        'primary.xml',
        'info.xml'
    );

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
    table_entry_total,
    table_value_total_reported,
    table_value_total_unit,
    table_value_total_usd,
    parser_version
)
VALUES
    (
        '0001193125-25-282901',
        '13F-HR',
        '2025-09-30',
        '2025-09-30',
        FALSE,
        FALSE,
        NULL,
        NULL,
        'Berkshire Hathaway Inc',
        5,
        1673.00,
        'USD',
        1673.00,
        '1.0.0'
    ),
    (
        '0001193125-26-054580',
        '13F-HR',
        '2025-12-31',
        '2025-12-31',
        FALSE,
        FALSE,
        NULL,
        NULL,
        'Berkshire Hathaway Inc',
        4,
        1445.00,
        'USD',
        1445.00,
        '1.0.0'
    );

INSERT INTO security_references (
    security_reference_key,
    issuer_name,
    class_title,
    cusip,
    figi
)
VALUES
    (
        'exact-co-com',
        'EXACT CO',
        'COM',
        '123456789',
        'BBG000000001'
    ),
    (
        'bank-amer-corp',
        'BANK AMER CORP',
        'COM',
        '060505104',
        NULL
    ),
    (
        'bank-america-corp',
        'BANK AMERICA CORP',
        'COM',
        '060505104',
        NULL
    ),
    (
        'liberty-live-c-old',
        'LIBERTY MEDIA CORP DEL',
        'COM LBTY LIV S C',
        '531229722',
        NULL
    ),
    (
        'liberty-formula-c',
        'LIBERTY MEDIA CORP DEL',
        'COM SER C FRMLA',
        '531229854',
        NULL
    ),
    (
        'liberty-live-c-new',
        'LIBERTY LIVE HOLDINGS INC',
        'COM SHS SER C',
        '530909308',
        NULL
    ),
    (
        'liberty-one-c',
        'LIBERTY MEDIA CORP DEL',
        'COM LBTY ONE S C',
        '531229755',
        NULL
    );

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
VALUES
    (
        '0001193125-25-282901',
        1,
        'exact-co-com',
        'EXACT CO',
        'COM',
        '123456789',
        'BBG000000001',
        100.00,
        'USD',
        100.00,
        10.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        10.00,
        0.00,
        0.00
    ),
    (
        '0001193125-26-054580',
        1,
        'exact-co-com',
        'EXACT CO',
        'COM',
        '123456789',
        'BBG000000001',
        150.00,
        'USD',
        150.00,
        15.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        15.00,
        0.00,
        0.00
    ),
    (
        '0001193125-25-282901',
        2,
        'bank-amer-corp',
        'BANK AMER CORP',
        'COM',
        '060505104',
        NULL,
        100.00,
        'USD',
        100.00,
        1000.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        1000.00,
        0.00,
        0.00
    ),
    (
        '0001193125-26-054580',
        2,
        'bank-america-corp',
        'BANK AMERICA CORP',
        'COM',
        '060505104',
        NULL,
        90.00,
        'USD',
        90.00,
        900.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        900.00,
        0.00,
        0.00
    ),
    (
        '0001193125-25-282901',
        3,
        'liberty-live-c-old',
        'LIBERTY MEDIA CORP DEL',
        'COM LBTY LIV S C',
        '531229722',
        NULL,
        1058.00,
        'USD',
        1058.00,
        10917661.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        10917661.00,
        0.00,
        0.00
    ),
    (
        '0001193125-25-282901',
        4,
        'liberty-formula-c',
        'LIBERTY MEDIA CORP DEL',
        'COM SER C FRMLA',
        '531229854',
        NULL,
        315.00,
        'USD',
        315.00,
        3018555.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        3018555.00,
        0.00,
        0.00
    ),
    (
        '0001193125-26-054580',
        3,
        'liberty-live-c-new',
        'LIBERTY LIVE HOLDINGS INC',
        'COM SHS SER C',
        '530909308',
        NULL,
        908.00,
        'USD',
        908.00,
        10917661.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        10917661.00,
        0.00,
        0.00
    ),
    (
        '0001193125-26-054580',
        4,
        'liberty-one-c',
        'LIBERTY MEDIA CORP DEL',
        'COM LBTY ONE S C',
        '531229755',
        NULL,
        297.00,
        'USD',
        297.00,
        3018555.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        3018555.00,
        0.00,
        0.00
    );
"""


class CompareFilerHoldingsFunctionIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base_dsn = os.environ.get("SEC_EDGAR_TEST_DB_DSN")
        if not base_dsn:
            raise unittest.SkipTest("SEC_EDGAR_TEST_DB_DSN is not set")
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest("psycopg is not installed") from exc

        schema_name = f"compare_test_{uuid4().hex[:8]}"
        cls._schema_name = schema_name
        cls._base_dsn = base_dsn
        cls._search_path_options = f"-csearch_path={schema_name},public"
        try:
            cls._admin_connection = psycopg.connect(base_dsn, autocommit=True)
            with cls._admin_connection.cursor() as cursor:
                cursor.execute(f'CREATE SCHEMA "{schema_name}"')

            connection = psycopg.connect(base_dsn, options=cls._search_path_options)
            apply_migrations(connection)
            with connection.cursor() as cursor:
                cursor.execute(SEED_SQL)
            connection.commit()
            refresh_analytics_views(connection)
            connection.close()
        except Exception:
            if hasattr(cls, "_admin_connection"):
                with cls._admin_connection.cursor() as cursor:
                    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
                cls._admin_connection.close()
            raise

        cls._psycopg = psycopg

    @classmethod
    def tearDownClass(cls) -> None:
        if not hasattr(cls, "_admin_connection"):
            return
        with cls._admin_connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{cls._schema_name}" CASCADE')
        cls._admin_connection.close()

    def setUp(self) -> None:
        self.connection = self._psycopg.connect(
            self._base_dsn,
            options=self._search_path_options,
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_compare_matches_renamed_positions_by_same_share_count(self) -> None:
        with self.connection.cursor(row_factory=self._psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    issuer_name,
                    class_title,
                    previous_class_title,
                    current_value_usd,
                    prior_value_usd,
                    value_change_usd,
                    current_shares_principal_amount,
                    prior_shares_principal_amount,
                    new_position,
                    disposed_position,
                    match_strategy
                FROM thirteenf_compare_filer_holdings(
                    %s,
                    %s,
                    %s
                )
                WHERE issuer_name IN ('LIBERTY LIVE HOLDINGS INC', 'LIBERTY MEDIA CORP DEL')
                ORDER BY class_title
                """,
                ("1067983", "2025-12-31", "2025-09-30"),
            )
            rows = cursor.fetchall()

        self.assertEqual(len(rows), 2)

        live_row = next(row for row in rows if row["class_title"] == "COM SHS SER C")
        one_row = next(row for row in rows if row["class_title"] == "COM LBTY ONE S C")

        self.assertEqual(live_row["previous_class_title"], "COM LBTY LIV S C")
        self.assertEqual(live_row["value_change_usd"], Decimal("-150.00"))
        self.assertEqual(live_row["current_shares_principal_amount"], Decimal("10917661.00"))
        self.assertEqual(live_row["prior_shares_principal_amount"], Decimal("10917661.00"))
        self.assertFalse(live_row["new_position"])
        self.assertFalse(live_row["disposed_position"])
        self.assertEqual(live_row["match_strategy"], "issuer_or_primary_token_same_shares")

        self.assertEqual(one_row["previous_class_title"], "COM SER C FRMLA")
        self.assertEqual(one_row["value_change_usd"], Decimal("-18.00"))
        self.assertEqual(one_row["current_shares_principal_amount"], Decimal("3018555.00"))
        self.assertEqual(one_row["prior_shares_principal_amount"], Decimal("3018555.00"))
        self.assertFalse(one_row["new_position"])
        self.assertFalse(one_row["disposed_position"])
        self.assertEqual(one_row["match_strategy"], "issuer_or_primary_token_same_shares")

    def test_compare_matches_same_cusip_when_only_label_changes(self) -> None:
        with self.connection.cursor(row_factory=self._psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    issuer_name,
                    previous_cusip,
                    value_change_usd,
                    share_change,
                    new_position,
                    disposed_position,
                    match_strategy
                FROM thirteenf_compare_filer_holdings(
                    %s,
                    %s,
                    %s
                )
                WHERE issuer_name = 'BANK AMERICA CORP'
                """,
                ("1067983", "2025-12-31", "2025-09-30"),
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["previous_cusip"], "060505104")
        self.assertEqual(row["value_change_usd"], Decimal("-10.00"))
        self.assertEqual(row["share_change"], Decimal("-100.00"))
        self.assertFalse(row["new_position"])
        self.assertFalse(row["disposed_position"])
        self.assertEqual(row["match_strategy"], "figi_or_cusip")

    def test_compare_preserves_exact_security_matches(self) -> None:
        with self.connection.cursor(row_factory=self._psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    issuer_name,
                    value_change_usd,
                    share_change,
                    new_position,
                    disposed_position,
                    match_strategy
                FROM thirteenf_compare_filer_holdings(
                    %s,
                    %s,
                    %s
                )
                WHERE issuer_name = 'EXACT CO'
                """,
                ("1067983", "2025-12-31", "2025-09-30"),
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["value_change_usd"], Decimal("50.00"))
        self.assertEqual(row["share_change"], Decimal("5.00"))
        self.assertFalse(row["new_position"])
        self.assertFalse(row["disposed_position"])
        self.assertEqual(row["match_strategy"], "exact_security_reference_key")


if __name__ == "__main__":
    unittest.main()
