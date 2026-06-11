from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

from bs4 import BeautifulSoup

from sec_edgar_ingestor.filings.periodic.models import (
    ParsedPeriodicReport,
    PeriodicChunk,
    PeriodicSection,
    XbrlFact,
)
from sec_edgar_ingestor.sec.indexes import IndexEntry


PARSER_NAME = "periodic"
PARSER_VERSION = "1.0.0"
DEFAULT_CHUNK_CHARS = 3600
DEFAULT_CHUNK_OVERLAP_CHARS = 250


class PeriodicParseError(ValueError):
    """Raised when a 10-K or 10-Q cannot be parsed."""


@dataclass(frozen=True)
class ItemDefinition:
    section_key: str
    item_label: str
    title: str
    pattern: re.Pattern[str]


ITEM_DEFINITIONS = {
    "10-K": [
        ("business", "Item 1", "Business", r"\bitem\s+1[\.\s:-]+business\b"),
        ("risk_factors", "Item 1A", "Risk Factors", r"\bitem\s+1a[\.\s:-]+risk\s+factors\b"),
        ("unresolved_staff_comments", "Item 1B", "Unresolved Staff Comments", r"\bitem\s+1b[\.\s:-]+unresolved\s+staff\s+comments\b"),
        ("properties", "Item 2", "Properties", r"\bitem\s+2[\.\s:-]+properties\b"),
        ("legal_proceedings", "Item 3", "Legal Proceedings", r"\bitem\s+3[\.\s:-]+legal\s+proceedings\b"),
        ("market_for_registrant_common_equity", "Item 5", "Market for Registrant Common Equity", r"\bitem\s+5[\.\s:-]+market\s+for\s+registrant"),
        ("mda", "Item 7", "Management's Discussion and Analysis", r"\bitem\s+7[\.\s:-]+management"),
        ("market_risk", "Item 7A", "Quantitative and Qualitative Disclosures About Market Risk", r"\bitem\s+7a[\.\s:-]+quantitative\s+and\s+qualitative"),
        ("financial_statements", "Item 8", "Financial Statements and Supplementary Data", r"\bitem\s+8[\.\s:-]+financial\s+statements"),
        ("controls", "Item 9A", "Controls and Procedures", r"\bitem\s+9a[\.\s:-]+controls\s+and\s+procedures"),
    ],
    "10-Q": [
        ("financial_statements", "Part I Item 1", "Financial Statements", r"\bitem\s+1[\.\s:-]+financial\s+statements\b"),
        ("mda", "Part I Item 2", "Management's Discussion and Analysis", r"\bitem\s+2[\.\s:-]+management"),
        ("market_risk", "Part I Item 3", "Quantitative and Qualitative Disclosures About Market Risk", r"\bitem\s+3[\.\s:-]+quantitative\s+and\s+qualitative"),
        ("controls", "Part I Item 4", "Controls and Procedures", r"\bitem\s+4[\.\s:-]+controls\s+and\s+procedures"),
        ("legal_proceedings", "Part II Item 1", "Legal Proceedings", r"\bitem\s+1[\.\s:-]+legal\s+proceedings"),
        ("risk_factors", "Part II Item 1A", "Risk Factors", r"\bitem\s+1a[\.\s:-]+risk\s+factors"),
    ],
}


def parse_periodic_report(
    entry: IndexEntry,
    *,
    acceptance_datetime: datetime | None,
    primary_document_filename: str | None,
    primary_document: bytes,
    index_url: str | None = None,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> ParsedPeriodicReport:
    html = primary_document.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    filing_text = _html_to_text(soup)
    base_form = _base_periodic_form(entry.form_type)
    facts = _extract_xbrl_facts(soup)
    sections = _extract_sections(filing_text, base_form)
    if not sections:
        sections = [
            PeriodicSection(
                section_key="full_text",
                item_label=None,
                section_title="Full Filing Text",
                char_start=0,
                char_end=len(filing_text),
                text_content=filing_text,
            )
        ]
    chunks = _chunk_sections(
        sections,
        chunk_chars=chunk_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )
    report_period = _fact_date(facts, "DocumentPeriodEndDate") or entry.filed_date
    fiscal_year = _fact_int(facts, "DocumentFiscalYearFocus")
    fiscal_period = _fact_value(facts, "DocumentFiscalPeriodFocus")
    title = _title_for_soup(soup)

    return ParsedPeriodicReport(
        accession_number=entry.accession_number,
        form_type=entry.form_type,
        cik=entry.cik,
        company_name=entry.company_name,
        filed_date=entry.filed_date,
        archive_path=entry.archive_path,
        submission_url=entry.archive_url,
        filing_directory_url=entry.filing_directory_url,
        index_url=index_url,
        period_of_report=report_period,
        acceptance_datetime=acceptance_datetime,
        primary_document_filename=primary_document_filename,
        information_table_filename=None,
        report_period=report_period,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        is_amendment=entry.form_type.upper().endswith("/A"),
        primary_document_title=title,
        sections=sections,
        chunks=chunks,
        xbrl_facts=facts,
    )


def _base_periodic_form(form_type: str) -> str:
    normalized = form_type.upper()
    if normalized.startswith("10-K"):
        return "10-K"
    if normalized.startswith("10-Q"):
        return "10-Q"
    raise PeriodicParseError(f"Unsupported periodic form type: {form_type}")


def _compiled_items(form_type: str) -> list[ItemDefinition]:
    return [
        ItemDefinition(key, label, title, re.compile(pattern, re.IGNORECASE | re.DOTALL))
        for key, label, title, pattern in ITEM_DEFINITIONS[form_type]
    ]


def _html_to_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    compact_lines = [line for line in lines if line]
    return "\n".join(compact_lines)


def _title_for_soup(soup: BeautifulSoup) -> str | None:
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split())
        return title or None
    return None


def _extract_sections(filing_text: str, form_type: str) -> list[PeriodicSection]:
    matches: list[tuple[int, ItemDefinition]] = []
    search_start = 0
    body_text = filing_text[search_start:]
    for item in _compiled_items(form_type):
        candidates = list(item.pattern.finditer(body_text))
        if not candidates:
            continue
        match = candidates[-1] if len(candidates) > 1 else candidates[0]
        matches.append((search_start + match.start(), item))
    matches.sort(key=lambda pair: pair[0])

    sections: list[PeriodicSection] = []
    seen: set[str] = set()
    for index, (section_start, item) in enumerate(matches):
        if item.section_key in seen:
            continue
        seen.add(item.section_key)
        section_end = matches[index + 1][0] if index + 1 < len(matches) else len(filing_text)
        content = filing_text[section_start:section_end].strip()
        if not content:
            continue
        sections.append(
            PeriodicSection(
                section_key=item.section_key,
                item_label=item.item_label,
                section_title=item.title,
                char_start=section_start,
                char_end=section_end,
                text_content=content,
            )
        )
    return sections


def _chunk_sections(
    sections: Iterable[PeriodicSection],
    *,
    chunk_chars: int,
    chunk_overlap_chars: int,
) -> list[PeriodicChunk]:
    chunks: list[PeriodicChunk] = []
    for section in sections:
        text = section.text_content
        start = 0
        ordinal = 1
        while start < len(text):
            end = min(start + chunk_chars, len(text))
            if end < len(text):
                paragraph_break = text.rfind("\n", start, end)
                if paragraph_break > start + chunk_chars // 2:
                    end = paragraph_break
            chunk_text = text[start:end].strip()
            if chunk_text:
                absolute_start = section.char_start + start + (len(text[start:end]) - len(text[start:end].lstrip()))
                absolute_end = absolute_start + len(chunk_text)
                chunks.append(
                    PeriodicChunk(
                        section_key=section.section_key,
                        item_label=section.item_label,
                        section_title=section.section_title,
                        chunk_ordinal=ordinal,
                        char_start=absolute_start,
                        char_end=absolute_end,
                        chunk_text=chunk_text,
                        content_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                    )
                )
                ordinal += 1
            if end >= len(text):
                break
            start = max(end - chunk_overlap_chars, start + 1)
    return chunks


def _extract_xbrl_facts(soup: BeautifulSoup) -> list[XbrlFact]:
    contexts = _extract_context_periods(soup)
    facts: list[XbrlFact] = []
    for tag in soup.find_all(_is_inline_xbrl_fact):
        concept = tag.get("name")
        if not concept:
            continue
        raw_value = " ".join(tag.get_text(" ").split())
        if not raw_value:
            continue
        namespace_prefix, local_name = _split_concept(concept)
        context_ref = tag.get("contextref")
        period = contexts.get(context_ref or "", {})
        scale = _parse_int(tag.get("scale"))
        numeric_value = _parse_numeric_value(raw_value, scale)
        facts.append(
            XbrlFact(
                concept=concept,
                namespace_prefix=namespace_prefix,
                local_name=local_name,
                context_ref=context_ref,
                unit_ref=tag.get("unitref"),
                decimals=tag.get("decimals"),
                scale=scale,
                raw_value=raw_value,
                numeric_value=numeric_value,
                fact_value=None if numeric_value is not None else raw_value,
                period_start=period.get("start"),
                period_end=period.get("end"),
                instant=period.get("instant"),
                dimensions_json=json.dumps(period.get("dimensions", {}), sort_keys=True),
            )
        )
    return facts


def _is_inline_xbrl_fact(tag: object) -> bool:
    name = getattr(tag, "name", "")
    return str(name).lower() in {"ix:nonfraction", "ix:nonnumeric", "nonfraction", "nonnumeric"}


def _extract_context_periods(soup: BeautifulSoup) -> dict[str, dict[str, object]]:
    contexts: dict[str, dict[str, object]] = {}
    for context in soup.find_all(lambda tag: str(getattr(tag, "name", "")).lower().endswith("context")):
        context_id = context.get("id")
        if not context_id:
            continue
        period = context.find(lambda tag: str(getattr(tag, "name", "")).lower().endswith("period"))
        entity = context.find(lambda tag: str(getattr(tag, "name", "")).lower().endswith("entity"))
        dimensions: dict[str, str] = {}
        if entity is not None:
            for member in entity.find_all(lambda tag: "member" in str(getattr(tag, "name", "")).lower()):
                dimension = member.get("dimension")
                if dimension:
                    dimensions[dimension] = " ".join(member.get_text(" ").split())
        value: dict[str, object] = {"dimensions": dimensions}
        if period is not None:
            start = _find_text_by_suffix(period, "startdate")
            end = _find_text_by_suffix(period, "enddate")
            instant = _find_text_by_suffix(period, "instant")
            value["start"] = _parse_date(start)
            value["end"] = _parse_date(end)
            value["instant"] = _parse_date(instant)
        contexts[context_id] = value
    return contexts


def _find_text_by_suffix(tag: object, suffix: str) -> str | None:
    child = tag.find(lambda node: str(getattr(node, "name", "")).lower().endswith(suffix))
    return " ".join(child.get_text(" ").split()) if child is not None else None


def _split_concept(concept: str) -> tuple[str | None, str]:
    if ":" not in concept:
        return None, concept
    namespace, local_name = concept.split(":", 1)
    return namespace, local_name


def _parse_numeric_value(raw_value: str, scale: int | None) -> Decimal | None:
    normalized = raw_value.strip()
    if not normalized or normalized in {"--", "-", "—"}:
        return None
    negative = normalized.startswith("(") and normalized.endswith(")")
    normalized = re.sub(r"[$,%\s,()]", "", normalized)
    if not normalized:
        return None
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    if negative:
        value = -value
    if scale is not None:
        value = value * (Decimal(10) ** scale)
    return value


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _fact_value(facts: Iterable[XbrlFact], local_name: str) -> str | None:
    for fact in facts:
        if fact.local_name == local_name:
            return fact.fact_value or fact.raw_value
    return None


def _fact_date(facts: Iterable[XbrlFact], local_name: str) -> date | None:
    value = _fact_value(facts, local_name)
    return _parse_date(value)


def _fact_int(facts: Iterable[XbrlFact], local_name: str) -> int | None:
    return _parse_int(_fact_value(facts, local_name))
