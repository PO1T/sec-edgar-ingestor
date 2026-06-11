from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class PeriodicSection:
    section_key: str
    item_label: str | None
    section_title: str
    char_start: int
    char_end: int
    text_content: str


@dataclass(frozen=True)
class PeriodicChunk:
    section_key: str
    item_label: str | None
    section_title: str
    chunk_ordinal: int
    char_start: int
    char_end: int
    chunk_text: str
    content_hash: str


@dataclass(frozen=True)
class XbrlFact:
    concept: str
    namespace_prefix: str | None
    local_name: str
    context_ref: str | None
    unit_ref: str | None
    decimals: str | None
    scale: int | None
    raw_value: str
    numeric_value: Decimal | None
    fact_value: str | None
    period_start: date | None
    period_end: date | None
    instant: date | None
    dimensions_json: str = "{}"
    source_section_key: str | None = None


@dataclass(frozen=True)
class ParsedPeriodicReport:
    accession_number: str
    form_type: str
    cik: str
    company_name: str
    filed_date: date
    archive_path: str
    submission_url: str
    filing_directory_url: str
    index_url: str | None
    period_of_report: date | None
    acceptance_datetime: datetime | None
    primary_document_filename: str | None
    information_table_filename: str | None
    report_period: date | None
    fiscal_year: int | None
    fiscal_period: str | None
    is_amendment: bool
    primary_document_title: str | None
    sections: list[PeriodicSection] = field(default_factory=list)
    chunks: list[PeriodicChunk] = field(default_factory=list)
    xbrl_facts: list[XbrlFact] = field(default_factory=list)
