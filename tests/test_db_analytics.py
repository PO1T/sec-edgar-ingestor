from __future__ import annotations

import unittest

from sec_edgar_ingestor.db.analytics import refresh_analytics_views


class RecordingCursor:
    def __init__(self, statements: list[str]) -> None:
        self._statements = statements

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        self._statements.append(sql)


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.commit_count = 0

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self.statements)

    def commit(self) -> None:
        self.commit_count += 1


class RefreshAnalyticsViewsTestCase(unittest.TestCase):
    def test_refreshes_materialized_views_in_dependency_order(self) -> None:
        connection = RecordingConnection()

        refreshed = refresh_analytics_views(connection)

        self.assertEqual(
            refreshed,
            [
                "thirteenf_filer_identities",
                "thirteenf_filer_positions",
                "thirteenf_filer_position_changes",
            ],
        )
        self.assertEqual(
            connection.statements,
            [
                "REFRESH MATERIALIZED VIEW thirteenf_filer_identities",
                "REFRESH MATERIALIZED VIEW thirteenf_filer_positions",
                "REFRESH MATERIALIZED VIEW thirteenf_filer_position_changes",
            ],
        )
        self.assertEqual(connection.commit_count, 1)


if __name__ == "__main__":
    unittest.main()
