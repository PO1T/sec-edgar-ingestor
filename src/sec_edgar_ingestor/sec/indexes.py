from __future__ import annotations

import gzip
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import PurePosixPath
from typing import Iterable, Iterator


ARCHIVES_BASE_URL = "https://www.sec.gov/Archives"
THIRTEENF_FORM_TYPES = frozenset({"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"})


@dataclass(frozen=True)
class IndexEntry:
    cik: str
    company_name: str
    form_type: str
    filed_date: date
    archive_path: str

    @property
    def accession_number(self) -> str:
        return PurePosixPath(self.archive_path).stem

    @property
    def archive_url(self) -> str:
        return f"{ARCHIVES_BASE_URL}/{self.archive_path}"

    @property
    def filing_directory_url(self) -> str:
        return f"{ARCHIVES_BASE_URL}/{PurePosixPath(self.archive_path).parent}"

    @property
    def directory_index_url(self) -> str:
        return f"{self.filing_directory_url}/index.json"


def decode_index_payload(url: str, payload: bytes) -> str:
    content = gzip.decompress(payload) if url.endswith(".gz") else payload
    return content.decode("utf-8", errors="replace")


def parse_master_idx(text: str) -> list[IndexEntry]:
    entries: list[IndexEntry] = []
    in_rows = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not in_rows:
            if line.startswith("----"):
                in_rows = True
            continue

        parts = line.split("|")
        if len(parts) != 5:
            continue

        cik, company_name, form_type, filed_date_raw, archive_path = parts
        entries.append(
            IndexEntry(
                cik=cik.strip(),
                company_name=company_name.strip(),
                form_type=form_type.strip(),
                filed_date=date.fromisoformat(filed_date_raw.strip()),
                archive_path=archive_path.strip(),
            )
        )

    return entries


def filter_entries(
    entries: Iterable[IndexEntry],
    form_types: set[str] | frozenset[str],
    start_date: date,
    end_date: date,
) -> list[IndexEntry]:
    return [
        entry
        for entry in entries
        if entry.form_type in form_types and start_date <= entry.filed_date <= end_date
    ]


def quarterly_index_urls(start_date: date, end_date: date) -> list[str]:
    urls: list[str] = []
    year = start_date.year
    quarter = _quarter_for_date(start_date)
    while (year, quarter) <= (end_date.year, _quarter_for_date(end_date)):
        urls.append(
            f"{ARCHIVES_BASE_URL}/edgar/full-index/{year}/QTR{quarter}/master.idx"
        )
        year, quarter = _next_quarter(year, quarter)
    return urls


def daily_index_urls(start_date: date, end_date: date) -> list[str]:
    urls: list[str] = []
    for current in _iter_dates(start_date, end_date):
        if current.weekday() >= 5:
            continue
        urls.append(
            (
                f"{ARCHIVES_BASE_URL}/edgar/daily-index/{current.year}/"
                f"QTR{_quarter_for_date(current)}/master.{current:%Y%m%d}.idx"
            )
        )
    return urls


def _iter_dates(start_date: date, end_date: date) -> Iterator[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _quarter_for_date(value: date) -> int:
    return ((value.month - 1) // 3) + 1


def _next_quarter(year: int, quarter: int) -> tuple[int, int]:
    if quarter == 4:
        return year + 1, 1
    return year, quarter + 1
