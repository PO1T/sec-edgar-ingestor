from __future__ import annotations

import unittest

from sec_edgar_ingestor.config import ConfigurationError, Settings


class SettingsTestCase(unittest.TestCase):
    def test_reads_defaults_from_environment_mapping(self) -> None:
        settings = Settings.from_env(
            env={
                "SEC_EDGAR_DB_DSN": "postgresql://localhost/sec",
                "SEC_EDGAR_USER_AGENT": "sec-edgar-ingestor/0.1.0 support@example.com",
            }
        )

        self.assertEqual(settings.db_dsn, "postgresql://localhost/sec")
        self.assertEqual(settings.user_agent, "sec-edgar-ingestor/0.1.0 support@example.com")
        self.assertEqual(str(settings.data_dir), "data")
        self.assertEqual(settings.requests_per_second, 5.0)

    def test_invalid_numeric_setting_raises(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings.from_env(env={"SEC_EDGAR_REQUESTS_PER_SECOND": "zero"})


if __name__ == "__main__":
    unittest.main()
