from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


def build_security_reference_key(
    issuer_name: str,
    class_title: str,
    cusip: str,
    figi: str | None,
) -> str:
    normalized = "|".join(
        [
            " ".join(issuer_name.split()).casefold(),
            " ".join(class_title.split()).casefold(),
            cusip.strip().upper(),
            (figi or "").strip().upper(),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OtherManager:
    manager_sequence: int | None
    manager_name: str | None
    cik: str | None
    form13f_file_number: str | None
    crd_number: str | None
    sec_file_number: str | None


@dataclass(frozen=True)
class Holding:
    holding_sequence: int
    security_reference_key: str
    issuer_name: str
    class_title: str
    cusip: str
    figi: str | None
    value_reported: Decimal | None
    value_unit: str
    value_usd: Decimal | None
    shares_principal_amount: Decimal | None
    shares_principal_type: str | None
    put_call: str | None
    investment_discretion: str | None
    other_manager: str | None
    voting_authority_sole: Decimal | None
    voting_authority_shared: Decimal | None
    voting_authority_none: Decimal | None


@dataclass(frozen=True)
class ParsedThirteenF:
    accession_number: str
    form_type: str
    cik: str
    company_name: str
    filed_date: date
    archive_path: str
    submission_url: str
    filing_directory_url: str
    index_url: str | None
    period_of_report: date
    acceptance_datetime: datetime | None
    primary_document_filename: str | None
    information_table_filename: str | None
    submission_type: str
    report_calendar_or_quarter: date | None
    is_notice: bool
    is_amendment: bool
    amendment_type: str | None
    amendment_type_code: str | None
    amendment_number: int | None
    filing_manager_name: str | None
    street1: str | None
    street2: str | None
    city: str | None
    state_or_country: str | None
    zip_code: str | None
    report_type: str | None
    form13f_file_number: str | None
    crd_number: str | None
    sec_file_number: str | None
    provide_info_for_instruction5: bool | None
    additional_information: str | None
    other_included_managers_count: int | None
    table_entry_total: int | None
    table_value_total_reported: Decimal | None
    table_value_total_unit: str
    table_value_total_usd: Decimal | None
    is_confidential_omitted: bool | None
    signature_name: str | None
    signature_title: str | None
    signature_phone: str | None
    signature_city: str | None
    signature_state_or_country: str | None
    signature_date: date | None
    other_managers: list[OtherManager] = field(default_factory=list)
    holdings: list[Holding] = field(default_factory=list)
