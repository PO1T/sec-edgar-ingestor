from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from xml.etree import ElementTree

from sec_edgar_ingestor.filings.thirteenf.models import (
    Holding,
    OtherManager,
    ParsedThirteenF,
    build_security_reference_key,
)
from sec_edgar_ingestor.sec.indexes import IndexEntry


PARSER_NAME = "thirteenf"
PARSER_VERSION = "1.0.0"
VALUE_UNIT_CUTOFF = date(2023, 1, 3)
UNKNOWN_AMENDMENT_TYPE = "UNKNOWN_AMENDMENT_TYPE"
KNOWN_AMENDMENT_TYPE_CODES = frozenset({"RESTATEMENT", "NEW HOLDINGS"})


class ParseError(ValueError):
    """Raised when a 13F filing cannot be parsed into structured records."""


def parse_thirteenf(
    entry: IndexEntry,
    *,
    submission_type: str,
    acceptance_datetime: datetime | None,
    primary_document_filename: str | None,
    information_table_filename: str | None,
    primary_xml: bytes,
    information_table_xml: bytes | None,
    index_url: str | None = None,
) -> ParsedThirteenF:
    primary_root = _strip_namespaces(ElementTree.fromstring(primary_xml))
    info_root = (
        _strip_namespaces(ElementTree.fromstring(information_table_xml))
        if information_table_xml
        else None
    )

    period_of_report = _require_date(
        _first_text(
            primary_root,
            "headerData/filerInfo/periodOfReport",
            "filerInfo/periodOfReport",
            "formData/coverPage/reportCalendarOrQuarter",
        ),
        field_name="period_of_report",
    )
    report_calendar_or_quarter = _parse_date(
        _first_text(primary_root, "formData/coverPage/reportCalendarOrQuarter")
    )

    is_notice = submission_type.upper().startswith("13F-NT")
    is_amendment = submission_type.upper().endswith("/A") or bool(
        _parse_bool(
            _first_text(primary_root, "formData/coverPage/isAmendment")
        )
    )
    value_unit = value_unit_for_filed_date(entry.filed_date)

    filing_manager = primary_root.find("formData/coverPage/filingManager")
    address = filing_manager.find("address") if filing_manager is not None else None
    summary_page = primary_root.find("formData/summaryPage")
    signature_block = primary_root.find("formData/signatureBlock")

    other_managers = _parse_other_managers(primary_root)
    holdings = [] if is_notice else _parse_holdings(
        info_root,
        filed_date=entry.filed_date,
        value_unit=value_unit,
    )

    table_value_total_reported = _parse_decimal(
        _first_text(primary_root, "formData/summaryPage/tableValueTotal")
    )
    table_value_total_usd = normalize_reported_value(
        table_value_total_reported,
        entry.filed_date,
    )

    amendment_type = _first_text(primary_root, "formData/coverPage/amendmentType")

    return ParsedThirteenF(
        accession_number=entry.accession_number,
        form_type=entry.form_type,
        cik=entry.cik,
        company_name=entry.company_name,
        filed_date=entry.filed_date,
        archive_path=entry.archive_path,
        submission_url=entry.archive_url,
        filing_directory_url=entry.filing_directory_url,
        index_url=index_url,
        period_of_report=period_of_report,
        acceptance_datetime=acceptance_datetime,
        primary_document_filename=primary_document_filename,
        information_table_filename=information_table_filename,
        submission_type=submission_type,
        report_calendar_or_quarter=report_calendar_or_quarter,
        is_notice=is_notice,
        is_amendment=is_amendment,
        amendment_type=amendment_type,
        amendment_type_code=normalize_amendment_type_code(
            amendment_type,
            is_amendment=is_amendment,
        ),
        amendment_number=_parse_int(
            _first_text(primary_root, "formData/coverPage/amendmentNumber")
        ),
        filing_manager_name=_first_text(
            primary_root,
            "formData/coverPage/filingManager/name",
            "headerData/filerInfo/filer/name",
        ),
        street1=_first_text(address, "street1") if address is not None else None,
        street2=_first_text(address, "street2") if address is not None else None,
        city=_first_text(address, "city") if address is not None else None,
        state_or_country=_first_text(address, "stateOrCountry") if address is not None else None,
        zip_code=_first_text(address, "zipCode") if address is not None else None,
        report_type=_first_text(primary_root, "formData/coverPage/reportType"),
        form13f_file_number=_first_text(
            primary_root,
            "formData/coverPage/form13FFileNumber",
            "formData/coverPage/fileNumber",
        ),
        crd_number=_first_text(primary_root, "formData/coverPage/crdNumber"),
        sec_file_number=_first_text(primary_root, "formData/coverPage/secFileNumber"),
        provide_info_for_instruction5=_parse_bool(
            _first_text(primary_root, "formData/coverPage/provideInfoForInstruction5")
        ),
        additional_information=_first_text(
            primary_root,
            "formData/coverPage/additionalInformation",
        ),
        other_included_managers_count=_parse_int(
            _first_text(summary_page, "otherIncludedManagersCount")
            if summary_page is not None
            else None
        ),
        table_entry_total=_parse_int(
            _first_text(summary_page, "tableEntryTotal") if summary_page is not None else None
        ),
        table_value_total_reported=table_value_total_reported,
        table_value_total_unit=value_unit,
        table_value_total_usd=table_value_total_usd,
        is_confidential_omitted=_parse_bool(
            _first_text(summary_page, "isConfidentialOmitted")
            if summary_page is not None
            else None
        ),
        signature_name=_first_text(signature_block, "name") if signature_block is not None else None,
        signature_title=_first_text(signature_block, "title") if signature_block is not None else None,
        signature_phone=_first_text(signature_block, "phone") if signature_block is not None else None,
        signature_city=_first_text(signature_block, "city") if signature_block is not None else None,
        signature_state_or_country=(
            _first_text(signature_block, "stateOrCountry")
            if signature_block is not None
            else None
        ),
        signature_date=_parse_date(
            _first_text(signature_block, "signatureDate") if signature_block is not None else None
        ),
        other_managers=other_managers,
        holdings=holdings,
    )


def value_unit_for_filed_date(filed_date: date) -> str:
    if filed_date >= VALUE_UNIT_CUTOFF:
        return "USD"
    return "THOUSANDS_USD"


def normalize_reported_value(value: Decimal | None, filed_date: date) -> Decimal | None:
    if value is None:
        return None
    if filed_date >= VALUE_UNIT_CUTOFF:
        return value
    return value * Decimal("1000")


def normalize_amendment_type_code(
    amendment_type: str | None,
    *,
    is_amendment: bool,
) -> str | None:
    if not is_amendment:
        return None

    if amendment_type is None:
        return UNKNOWN_AMENDMENT_TYPE

    normalized = " ".join(amendment_type.split()).upper()
    if normalized in KNOWN_AMENDMENT_TYPE_CODES:
        return normalized
    return UNKNOWN_AMENDMENT_TYPE


def _parse_holdings(
    root: ElementTree.Element | None,
    *,
    filed_date: date,
    value_unit: str,
) -> list[Holding]:
    if root is None:
        return []

    holdings: list[Holding] = []
    for sequence, info_table in enumerate(root.findall("infoTable"), start=1):
        issuer_name = _require_text(_first_text(info_table, "nameOfIssuer"), "nameOfIssuer")
        class_title = _require_text(_first_text(info_table, "titleOfClass"), "titleOfClass")
        cusip = _require_text(_first_text(info_table, "cusip"), "cusip")
        figi = _first_text(info_table, "figi")
        value_reported = _parse_decimal(_first_text(info_table, "value"))
        holdings.append(
            Holding(
                holding_sequence=sequence,
                security_reference_key=build_security_reference_key(
                    issuer_name=issuer_name,
                    class_title=class_title,
                    cusip=cusip,
                    figi=figi,
                ),
                issuer_name=issuer_name,
                class_title=class_title,
                cusip=cusip,
                figi=figi,
                value_reported=value_reported,
                value_unit=value_unit,
                value_usd=normalize_reported_value(value_reported, filed_date),
                shares_principal_amount=_parse_decimal(
                    _first_text(info_table, "shrsOrPrnAmt/sshPrnamt")
                ),
                shares_principal_type=_first_text(info_table, "shrsOrPrnAmt/sshPrnamtType"),
                put_call=_first_text(info_table, "putCall"),
                investment_discretion=_first_text(info_table, "investmentDiscretion"),
                other_manager=_first_text(info_table, "otherManager"),
                voting_authority_sole=_parse_decimal(
                    _first_text(info_table, "votingAuthority/Sole")
                ),
                voting_authority_shared=_parse_decimal(
                    _first_text(info_table, "votingAuthority/Shared")
                ),
                voting_authority_none=_parse_decimal(
                    _first_text(info_table, "votingAuthority/None")
                ),
            )
        )
    return holdings


def _parse_other_managers(root: ElementTree.Element) -> list[OtherManager]:
    managers: list[OtherManager] = []
    parents = [
        root.find("formData/otherManagersInfo"),
        root.find("formData/otherManagers2Info"),
    ]
    for parent in parents:
        if parent is None:
            continue
        for child in list(parent):
            if not child.tag.lower().startswith("othermanager"):
                continue
            managers.append(
                OtherManager(
                    manager_sequence=_parse_int(_first_text(child, "sequenceNumber")),
                    manager_name=_first_text(child, "name"),
                    cik=_first_text(child, "cik"),
                    form13f_file_number=_first_text(child, "form13FFileNumber"),
                    crd_number=_first_text(child, "crdNumber"),
                    sec_file_number=_first_text(child, "secFileNumber"),
                )
            )
    return managers


def _strip_namespaces(root: ElementTree.Element) -> ElementTree.Element:
    for node in root.iter():
        if isinstance(node.tag, str) and "}" in node.tag:
            node.tag = node.tag.split("}", 1)[1]
    return root


def _first_text(element: ElementTree.Element | None, *paths: str) -> str | None:
    if element is None:
        return None
    for path in paths:
        child = element.find(path)
        if child is not None and child.text is not None:
            text = child.text.strip()
            if text:
                return text
    return None


def _require_text(value: str | None, field_name: str) -> str:
    if not value:
        raise ParseError(f"Missing required 13F field: {field_name}")
    return value


def _parse_date(value: str | None) -> date | None:
    if value is None or value.strip() == "":
        return None
    for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ParseError(f"Unsupported date value: {value}")


def _require_date(value: str | None, *, field_name: str) -> date:
    parsed = _parse_date(value)
    if parsed is None:
        raise ParseError(f"Missing required 13F date: {field_name}")
    return parsed


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "y", "yes", "1"}:
        return True
    if normalized in {"false", "n", "no", "0"}:
        return False
    return None


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    return Decimal(value.strip())


def _parse_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value.strip())
