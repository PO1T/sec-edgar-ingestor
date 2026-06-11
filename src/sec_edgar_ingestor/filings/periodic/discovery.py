from __future__ import annotations

from dataclasses import dataclass

from sec_edgar_ingestor.filings.thirteenf.discovery import SubmissionDocument


class PeriodicDocumentSelectionError(ValueError):
    """Raised when a periodic filing lacks a usable primary document."""


@dataclass(frozen=True)
class PeriodicDocumentSelection:
    primary_document: SubmissionDocument
    xbrl_documents: list[SubmissionDocument]


def select_periodic_documents(
    form_type: str,
    documents: list[SubmissionDocument],
) -> PeriodicDocumentSelection:
    normalized_form = form_type.upper()
    primary = _find_primary_document(normalized_form, documents)
    if primary is None:
        raise PeriodicDocumentSelectionError("Unable to identify periodic primary document")
    xbrl_documents = [
        doc
        for doc in documents
        if doc.filename != primary.filename and _looks_like_xbrl_artifact(doc)
    ]
    return PeriodicDocumentSelection(
        primary_document=primary,
        xbrl_documents=xbrl_documents,
    )


def _find_primary_document(
    form_type: str,
    documents: list[SubmissionDocument],
) -> SubmissionDocument | None:
    candidates = [
        doc
        for doc in documents
        if _is_html_document(doc.filename)
        and doc.doc_type.upper() in {form_type, form_type.replace("/A", "")}
    ]
    if candidates:
        return sorted(candidates, key=_sequence_sort_key)[0]
    html_documents = [doc for doc in documents if _is_html_document(doc.filename)]
    return sorted(html_documents, key=_sequence_sort_key)[0] if html_documents else None


def _is_html_document(filename: str) -> bool:
    return filename.lower().endswith((".htm", ".html", ".xhtml"))


def _looks_like_xbrl_artifact(document: SubmissionDocument) -> bool:
    doc_type = document.doc_type.upper()
    filename = document.filename.lower()
    return (
        doc_type.startswith("EX-101")
        or filename.endswith((".xml", ".xsd"))
        or any(filename.endswith(f".{suffix}") for suffix in ("cal", "def", "lab", "pre"))
    )


def _sequence_sort_key(document: SubmissionDocument) -> tuple[int, str]:
    try:
        sequence = int(document.sequence or "999999")
    except ValueError:
        sequence = 999999
    return sequence, document.filename
