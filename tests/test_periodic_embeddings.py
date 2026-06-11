from __future__ import annotations

import unittest
from datetime import date

from sec_edgar_ingestor.filings.periodic.embeddings import (
    EmbeddingConfigurationError,
    _parse_embedding_response,
    build_embedding_input,
    embedding_input_hash,
)


class PeriodicEmbeddingsTestCase(unittest.TestCase):
    def test_build_embedding_input_includes_citation_metadata(self) -> None:
        embedding_input = build_embedding_input(
            {
                "accession_number": "0000123456-25-000001",
                "cik": "123456",
                "company_name": "Example Foods Inc.",
                "ticker": "EXF",
                "form_type": "10-K",
                "filed_date": date(2025, 2, 1),
                "report_period": date(2024, 12, 31),
                "section_key": "market_risk",
                "section_title": "Quantitative and Qualitative Disclosures About Market Risk",
                "item_label": "Item 7A",
                "chunk_ordinal": 3,
                "chunk_text": "Swiss franc costs were not designated as accounting hedges.",
            }
        )

        self.assertIn("Company: Example Foods Inc.", embedding_input)
        self.assertIn("Section: market_risk", embedding_input)
        self.assertIn("Chunk ordinal: 3", embedding_input)
        self.assertIn("Swiss franc costs", embedding_input)
        self.assertEqual(len(embedding_input_hash(embedding_input)), 64)

    def test_parse_embedding_response_validates_count_and_dimensions(self) -> None:
        parsed = _parse_embedding_response(
            {
                "data": [
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                ],
                "usage": {"total_tokens": 12},
            },
            expected_count=2,
            expected_dimensions=3,
        )

        self.assertEqual(parsed.embeddings[0], [0.1, 0.2, 0.3])
        self.assertEqual(parsed.usage["total_tokens"], 12)

    def test_parse_embedding_response_rejects_dimension_mismatch(self) -> None:
        with self.assertRaises(EmbeddingConfigurationError):
            _parse_embedding_response(
                {"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
                expected_count=1,
                expected_dimensions=3,
            )


if __name__ == "__main__":
    unittest.main()
