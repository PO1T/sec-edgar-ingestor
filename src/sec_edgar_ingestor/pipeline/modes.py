from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sec_edgar_ingestor.sec.indexes import daily_index_urls, quarterly_index_urls


XML_THIRTEENF_START_DATE = date(2013, 5, 20)
DEV_LOOKBACK_DAYS = 183
DAILY_RESYNC_DAYS = 7


@dataclass(frozen=True)
class CheckpointValue:
    last_processed_filing_date: date | None
    last_processed_accession: str | None


@dataclass(frozen=True)
class DateWindow:
    mode: str
    start_date: date
    end_date: date


def resolve_window(
    mode: str,
    *,
    from_date: date | None,
    to_date: date | None,
    checkpoint: CheckpointValue | None = None,
    today: date | None = None,
) -> DateWindow:
    current_date = today or date.today()
    end_date = to_date or current_date

    if from_date is not None:
        start_date = from_date
    elif mode == "dev":
        start_date = current_date - timedelta(days=DEV_LOOKBACK_DAYS)
    elif mode == "full":
        start_date = XML_THIRTEENF_START_DATE
    elif checkpoint and checkpoint.last_processed_filing_date:
        start_date = checkpoint.last_processed_filing_date - timedelta(days=DAILY_RESYNC_DAYS)
    else:
        start_date = current_date - timedelta(days=DAILY_RESYNC_DAYS)

    if start_date < XML_THIRTEENF_START_DATE:
        start_date = XML_THIRTEENF_START_DATE
    if start_date > end_date:
        raise ValueError("from-date cannot be after to-date")

    return DateWindow(mode=mode, start_date=start_date, end_date=end_date)


def index_urls_for_window(window: DateWindow) -> list[str]:
    if window.mode == "full":
        return quarterly_index_urls(window.start_date, window.end_date)
    return daily_index_urls(window.start_date, window.end_date)


def should_skip_for_checkpoint(
    filed_date: date,
    accession_number: str,
    checkpoint: CheckpointValue | None,
) -> bool:
    if checkpoint is None or checkpoint.last_processed_filing_date is None:
        return False
    if filed_date < checkpoint.last_processed_filing_date:
        return True
    if (
        filed_date == checkpoint.last_processed_filing_date
        and checkpoint.last_processed_accession
        and accession_number <= checkpoint.last_processed_accession
    ):
        return True
    return False
