from __future__ import annotations

import unittest
from datetime import date

from sec_edgar_ingestor.pipeline.modes import (
    CheckpointValue,
    resolve_window,
    should_skip_for_checkpoint,
)


class PipelineModesTestCase(unittest.TestCase):
    def test_resolve_daily_window_uses_checkpoint_overlap(self) -> None:
        checkpoint = CheckpointValue(
            last_processed_filing_date=date(2024, 5, 15),
            last_processed_accession="0001067983-24-000010",
        )

        window = resolve_window(
            "daily",
            from_date=None,
            to_date=None,
            checkpoint=checkpoint,
            today=date(2024, 5, 20),
        )

        self.assertEqual(window.start_date, date(2024, 5, 8))
        self.assertEqual(window.end_date, date(2024, 5, 20))

    def test_should_skip_for_checkpoint(self) -> None:
        checkpoint = CheckpointValue(
            last_processed_filing_date=date(2024, 5, 15),
            last_processed_accession="0001067983-24-000010",
        )

        self.assertTrue(
            should_skip_for_checkpoint(
                date(2024, 5, 14),
                "0001067983-24-000999",
                checkpoint,
            )
        )
        self.assertTrue(
            should_skip_for_checkpoint(
                date(2024, 5, 15),
                "0001067983-24-000001",
                checkpoint,
            )
        )
        self.assertFalse(
            should_skip_for_checkpoint(
                date(2024, 5, 15),
                "0001067983-24-000999",
                checkpoint,
            )
        )


if __name__ == "__main__":
    unittest.main()
