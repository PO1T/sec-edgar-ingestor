from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


class DocumentSelectionError(ValueError):
    """Raised when a filing does not contain the expected 13F XML documents."""


_TAG_TEMPLATE = r"(?im)^\s*<{tag}>\s*([^\r\n<]+)"
_HEADER_LINE_TEMPLATE = r"(?im)^\s*{label}:\s*([^\r\n]+)"
_DOCUMENT_RE = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class SubmissionHeader:
    accession_number: str | None
    acceptance_datetime: datetime | None


@dataclass(frozen=True)
class SubmissionDocument:
    doc_type: str
    sequence: str | None
    filename: str
    description: str | None


def parse_submission_header(submission_text: str) -> SubmissionHeader:
    accession_number = _find_tag(submission_text, "ACCESSION-NUMBER")
    acceptance_raw = (
        _find_tag(submission_text, "ACCEPTANCE-DATETIME")
        or _find_header_line(submission_text, "ACCEPTANCE-DATETIME")
    )
    acceptance_datetime = None
    if acceptance_raw:
        acceptance_datetime = datetime.strptime(acceptance_raw.strip(), "%Y%m%d%H%M%S")

    return SubmissionHeader(
        accession_number=accession_number,
        acceptance_datetime=acceptance_datetime,
    )


def parse_submission_documents(submission_text: str) -> list[SubmissionDocument]:
    documents: list[SubmissionDocument] = []
    for block in _DOCUMENT_RE.findall(submission_text):
        filename = _find_tag(block, "FILENAME")
        doc_type = _find_tag(block, "TYPE")
        if not filename or not doc_type:
            continue
        documents.append(
            SubmissionDocument(
                doc_type=doc_type.strip(),
                sequence=_find_tag(block, "SEQUENCE"),
                filename=filename.strip(),
                description=_find_tag(block, "DESCRIPTION"),
            )
        )
    return documents


def select_thirteenf_documents(
    form_type: str,
    documents: list[SubmissionDocument],
) -> tuple[SubmissionDocument, SubmissionDocument | None]:
    xml_docs = [doc for doc in documents if doc.filename.lower().endswith(".xml")]
    if not xml_docs:
        raise DocumentSelectionError("No XML documents found in 13F submission")

    primary_document = next(
        (
            doc
            for doc in xml_docs
            if doc.doc_type.upper() == form_type.upper()
        ),
        None,
    )
    if primary_document is None:
        primary_document = next(
            (
                doc
                for doc in xml_docs
                if doc.doc_type.upper().startswith("13F-")
                and "INFORMATION" not in doc.doc_type.upper()
            ),
            None,
        )
    if primary_document is None:
        raise DocumentSelectionError("Unable to identify primary 13F XML document")

    information_document = next(
        (
            doc
            for doc in xml_docs
            if "INFORMATION TABLE" in doc.doc_type.upper()
            or "INFOTABLE" in doc.filename.upper()
        ),
        None,
    )

    if form_type in {"13F-HR", "13F-HR/A"} and information_document is None:
        raise DocumentSelectionError("13F holdings report is missing the information table XML")

    return primary_document, information_document


def _find_tag(text: str, tag: str) -> str | None:
    match = re.search(_TAG_TEMPLATE.format(tag=re.escape(tag)), text)
    return match.group(1).strip() if match else None


def _find_header_line(text: str, label: str) -> str | None:
    match = re.search(_HEADER_LINE_TEMPLATE.format(label=re.escape(label)), text)
    return match.group(1).strip() if match else None
