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
    ('0000001000', 'Supplement Manager LLC', '13F-HR/A', '2024-05-15', '2024-05-17'),
    ('0000002000', 'Restatement Manager LLC', '13F-HR/A', '2024-05-15', '2024-05-18'),
    ('0000003000', 'Orphan Manager LLC', '13F-HR/A', '2024-05-16', '2024-05-16');

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
        '0000001000-24-000001',
        '13F',
        '13F-HR',
        '0000001000',
        'Supplement Manager LLC',
        '2024-05-15',
        '2024-03-31',
        '2024-05-15T10:00:00Z',
        'archive/supplement/base',
        'https://example/supplement/base.txt',
        'https://example/supplement/base/',
        'https://example/supplement/base/index.json',
        'primary.xml',
        'info.xml'
    ),
    (
        '0000001000-24-000002',
        '13F',
        '13F-HR/A',
        '0000001000',
        'Supplement Manager LLC',
        '2024-05-16',
        '2024-03-31',
        '2024-05-16T10:00:00Z',
        'archive/supplement/new',
        'https://example/supplement/new.txt',
        'https://example/supplement/new/',
        'https://example/supplement/new/index.json',
        'primary.xml',
        'info.xml'
    ),
    (
        '0000001000-24-000003',
        '13F',
        '13F-HR/A',
        '0000001000',
        'Supplement Manager LLC',
        '2024-05-17',
        '2024-03-31',
        '2024-05-17T10:00:00Z',
        'archive/supplement/unknown',
        'https://example/supplement/unknown.txt',
        'https://example/supplement/unknown/',
        'https://example/supplement/unknown/index.json',
        'primary.xml',
        'info.xml'
    ),
    (
        '0000002000-24-000001',
        '13F',
        '13F-HR',
        '0000002000',
        'Restatement Manager LLC',
        '2024-05-15',
        '2024-03-31',
        '2024-05-15T11:00:00Z',
        'archive/restatement/base',
        'https://example/restatement/base.txt',
        'https://example/restatement/base/',
        'https://example/restatement/base/index.json',
        'primary.xml',
        'info.xml'
    ),
    (
        '0000002000-24-000002',
        '13F',
        '13F-HR/A',
        '0000002000',
        'Restatement Manager LLC',
        '2024-05-16',
        '2024-03-31',
        '2024-05-16T11:00:00Z',
        'archive/restatement/new',
        'https://example/restatement/new.txt',
        'https://example/restatement/new/',
        'https://example/restatement/new/index.json',
        'primary.xml',
        'info.xml'
    ),
    (
        '0000002000-24-000003',
        '13F',
        '13F-HR/A',
        '0000002000',
        'Restatement Manager LLC',
        '2024-05-18',
        '2024-03-31',
        '2024-05-18T11:00:00Z',
        'archive/restatement/final',
        'https://example/restatement/final.txt',
        'https://example/restatement/final/',
        'https://example/restatement/final/index.json',
        'primary.xml',
        'info.xml'
    ),
    (
        '0000003000-24-000001',
        '13F',
        '13F-HR/A',
        '0000003000',
        'Orphan Manager LLC',
        '2024-05-16',
        '2024-03-31',
        '2024-05-16T12:00:00Z',
        'archive/orphan/new',
        'https://example/orphan/new.txt',
        'https://example/orphan/new/',
        'https://example/orphan/new/index.json',
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
    amendment_type_code,
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
        '0000001000-24-000001',
        '13F-HR',
        '2024-03-31',
        '2024-03-31',
        FALSE,
        FALSE,
        NULL,
        NULL,
        NULL,
        'Supplement Manager LLC',
        2,
        300.00,
        'USD',
        300.00,
        '1.0.0'
    ),
    (
        '0000001000-24-000002',
        '13F-HR/A',
        '2024-03-31',
        '2024-03-31',
        FALSE,
        TRUE,
        'NEW HOLDINGS',
        'NEW HOLDINGS',
        1,
        'Supplement Manager LLC',
        1,
        300.00,
        'USD',
        300.00,
        '1.0.0'
    ),
    (
        '0000001000-24-000003',
        '13F-HR/A',
        '2024-03-31',
        '2024-03-31',
        FALSE,
        TRUE,
        'CORRECTION',
        'UNKNOWN_AMENDMENT_TYPE',
        2,
        'Supplement Manager LLC',
        1,
        500.00,
        'USD',
        500.00,
        '1.0.0'
    ),
    (
        '0000002000-24-000001',
        '13F-HR',
        '2024-03-31',
        '2024-03-31',
        FALSE,
        FALSE,
        NULL,
        NULL,
        NULL,
        'Restatement Manager LLC',
        2,
        300.00,
        'USD',
        300.00,
        '1.0.0'
    ),
    (
        '0000002000-24-000002',
        '13F-HR/A',
        '2024-03-31',
        '2024-03-31',
        FALSE,
        TRUE,
        'NEW HOLDINGS',
        'NEW HOLDINGS',
        1,
        'Restatement Manager LLC',
        1,
        300.00,
        'USD',
        300.00,
        '1.0.0'
    ),
    (
        '0000002000-24-000003',
        '13F-HR/A',
        '2024-03-31',
        '2024-03-31',
        FALSE,
        TRUE,
        'RESTATEMENT',
        'RESTATEMENT',
        2,
        'Restatement Manager LLC',
        1,
        400.00,
        'USD',
        400.00,
        '1.0.0'
    ),
    (
        '0000003000-24-000001',
        '13F-HR/A',
        '2024-03-31',
        '2024-03-31',
        FALSE,
        TRUE,
        'NEW HOLDINGS',
        'NEW HOLDINGS',
        1,
        'Orphan Manager LLC',
        1,
        700.00,
        'USD',
        700.00,
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
    ('base-a', 'BASE A CORP', 'COM', '000000001', NULL),
    ('base-b', 'BASE B CORP', 'COM', '000000002', NULL),
    ('added-c', 'ADDED C CORP', 'COM', '000000003', NULL),
    ('unknown-e', 'UNKNOWN E CORP', 'COM', '000000004', NULL),
    ('restated-d', 'RESTATED D CORP', 'COM', '000000005', NULL),
    ('orphan-z', 'ORPHAN Z CORP', 'COM', '000000006', NULL);

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
        '0000001000-24-000001',
        1,
        'base-a',
        'BASE A CORP',
        'COM',
        '000000001',
        NULL,
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
        '0000001000-24-000001',
        2,
        'base-b',
        'BASE B CORP',
        'COM',
        '000000002',
        NULL,
        200.00,
        'USD',
        200.00,
        20.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        20.00,
        0.00,
        0.00
    ),
    (
        '0000001000-24-000002',
        1,
        'added-c',
        'ADDED C CORP',
        'COM',
        '000000003',
        NULL,
        300.00,
        'USD',
        300.00,
        30.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        30.00,
        0.00,
        0.00
    ),
    (
        '0000001000-24-000003',
        1,
        'unknown-e',
        'UNKNOWN E CORP',
        'COM',
        '000000004',
        NULL,
        500.00,
        'USD',
        500.00,
        50.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        50.00,
        0.00,
        0.00
    ),
    (
        '0000002000-24-000001',
        1,
        'base-a',
        'BASE A CORP',
        'COM',
        '000000001',
        NULL,
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
        '0000002000-24-000001',
        2,
        'base-b',
        'BASE B CORP',
        'COM',
        '000000002',
        NULL,
        200.00,
        'USD',
        200.00,
        20.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        20.00,
        0.00,
        0.00
    ),
    (
        '0000002000-24-000002',
        1,
        'added-c',
        'ADDED C CORP',
        'COM',
        '000000003',
        NULL,
        300.00,
        'USD',
        300.00,
        30.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        30.00,
        0.00,
        0.00
    ),
    (
        '0000002000-24-000003',
        1,
        'restated-d',
        'RESTATED D CORP',
        'COM',
        '000000005',
        NULL,
        400.00,
        'USD',
        400.00,
        40.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        40.00,
        0.00,
        0.00
    ),
    (
        '0000003000-24-000001',
        1,
        'orphan-z',
        'ORPHAN Z CORP',
        'COM',
        '000000006',
        NULL,
        700.00,
        'USD',
        700.00,
        70.00,
        'SH',
        NULL,
        'SOLE',
        NULL,
        70.00,
        0.00,
        0.00
    );
"""


class AmendmentResolutionIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base_dsn = os.environ.get("SEC_EDGAR_TEST_DB_DSN")
        if not base_dsn:
            raise unittest.SkipTest("SEC_EDGAR_TEST_DB_DSN is not set")
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest("psycopg is not installed") from exc

        schema_name = f"amendment_test_{uuid4().hex[:8]}"
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

    def test_effective_holdings_apply_new_holdings_and_restatement_semantics(self) -> None:
        with self.connection.cursor(row_factory=self._psycopg.rows.dict_row) as cursor:
            cursor.execute("SELECT COUNT(*) AS raw_count FROM thirteenf_holdings")
            raw_count = cursor.fetchone()["raw_count"]

            cursor.execute(
                """
                SELECT cik, issuer_name, accession_number, value_usd
                FROM thirteenf_effective_holdings
                ORDER BY cik, issuer_name
                """
            )
            effective_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT cik, issuer_name, total_value_usd
                FROM thirteenf_filer_positions
                ORDER BY cik, issuer_name
                """
            )
            position_rows = cursor.fetchall()

        self.assertEqual(raw_count, 9)
        self.assertEqual(
            [
                (row["cik"], row["issuer_name"], row["accession_number"], row["value_usd"])
                for row in effective_rows
            ],
            [
                (
                    "0000001000",
                    "ADDED C CORP",
                    "0000001000-24-000002",
                    Decimal("300.00"),
                ),
                (
                    "0000001000",
                    "BASE A CORP",
                    "0000001000-24-000001",
                    Decimal("100.00"),
                ),
                (
                    "0000001000",
                    "BASE B CORP",
                    "0000001000-24-000001",
                    Decimal("200.00"),
                ),
                (
                    "0000002000",
                    "RESTATED D CORP",
                    "0000002000-24-000003",
                    Decimal("400.00"),
                ),
            ],
        )
        self.assertEqual(
            [
                (row["cik"], row["issuer_name"], row["total_value_usd"])
                for row in position_rows
            ],
            [
                ("0000001000", "ADDED C CORP", Decimal("300.00")),
                ("0000001000", "BASE A CORP", Decimal("100.00")),
                ("0000001000", "BASE B CORP", Decimal("200.00")),
                ("0000002000", "RESTATED D CORP", Decimal("400.00")),
            ],
        )

    def test_unknown_and_orphan_amendments_are_not_effective(self) -> None:
        with self.connection.cursor(row_factory=self._psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT accession_number, amendment_type, amendment_type_code
                FROM thirteenf_filings
                WHERE accession_number = '0000001000-24-000003'
                """
            )
            unknown_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*) AS effective_count
                FROM thirteenf_effective_holdings
                WHERE accession_number IN (
                    '0000001000-24-000003',
                    '0000003000-24-000001'
                )
                """
            )
            effective_count = cursor.fetchone()["effective_count"]

        self.assertEqual(unknown_row["amendment_type"], "CORRECTION")
        self.assertEqual(unknown_row["amendment_type_code"], "UNKNOWN_AMENDMENT_TYPE")
        self.assertEqual(effective_count, 0)


if __name__ == "__main__":
    unittest.main()
