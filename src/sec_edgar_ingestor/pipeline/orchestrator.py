from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sec_edgar_ingestor.config import Settings
from sec_edgar_ingestor.db.analytics import refresh_analytics_views
from sec_edgar_ingestor.db.connection import connect_db
from sec_edgar_ingestor.filings.thirteenf.discovery import (
    parse_submission_documents,
    parse_submission_header,
    select_thirteenf_documents,
)
from sec_edgar_ingestor.filings.thirteenf.loader import (
    artifact_fingerprint,
    mark_processing_state,
    upsert_parsed_filing,
)
from sec_edgar_ingestor.filings.thirteenf.parser import parse_thirteenf
from sec_edgar_ingestor.filings.periodic.discovery import select_periodic_documents
from sec_edgar_ingestor.filings.periodic.loader import (
    artifact_fingerprint as periodic_artifact_fingerprint,
)
from sec_edgar_ingestor.filings.periodic.loader import (
    mark_processing_state as periodic_mark_processing_state,
)
from sec_edgar_ingestor.filings.periodic.loader import (
    upsert_parsed_filing as periodic_upsert_parsed_filing,
)
from sec_edgar_ingestor.filings.periodic.parser import parse_periodic_report
from sec_edgar_ingestor.pipeline.modes import (
    CheckpointValue,
    DateWindow,
    index_urls_for_window,
    resolve_window,
    should_skip_for_checkpoint,
)
from sec_edgar_ingestor.pipeline.state import (
    finish_ingestion_run,
    list_artifacts_for_accession,
    list_filings_for_reprocess,
    load_checkpoint,
    save_checkpoint,
    start_ingestion_run,
)
from sec_edgar_ingestor.sec.client import SecClient
from sec_edgar_ingestor.sec.indexes import (
    PERIODIC_REPORT_FORM_TYPES,
    THIRTEENF_FORM_TYPES,
    IndexEntry,
    decode_index_payload,
    filter_entries,
    parse_master_idx,
)
from sec_edgar_ingestor.storage.artifact_store import ArtifactStore, StoredArtifact


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestOptions:
    mode: str
    from_date: date | None
    to_date: date | None
    limit_filings: int | None
    filing_family: str = "13F"
    dry_run: bool = False
    refresh_analytics: bool = True
    form_type: str = "all"
    include_amendments: bool = True


@dataclass(frozen=True)
class ReprocessOptions:
    accession: str | None
    from_date: date | None
    to_date: date | None
    filing_family: str = "13F"
    refresh_analytics: bool = True


def run_ingest(settings: Settings, options: IngestOptions) -> int:
    handler = _handler_for_family(options.filing_family, form_type=options.form_type, include_amendments=options.include_amendments)
    with connect_db(settings.require_db()) as connection:
        checkpoint = (
            load_checkpoint(
                connection,
                filing_family=handler["filing_family"],
                mode=options.mode,
            )
            if options.mode in {"full", "daily"}
            else None
        )
        window = resolve_window(
            options.mode,
            from_date=options.from_date,
            to_date=options.to_date,
            checkpoint=checkpoint,
        )
        run_id = start_ingestion_run(
            connection,
            filing_family=handler["filing_family"],
            mode=options.mode,
            from_date=window.start_date,
            to_date=window.end_date,
            details_json=json.dumps(
                {"dry_run": options.dry_run, "limit_filings": options.limit_filings}
            ),
        )

        artifact_store = ArtifactStore(settings.data_dir)
        stats = {
            "index_files_seen": 0,
            "candidate_filings": 0,
            "processed_filings": 0,
            "failed_filings": 0,
            "skipped_filings": 0,
            "analytics_views_refreshed": 0,
        }

        try:
            with SecClient(
                settings.require_user_agent(),
                timeout_seconds=settings.http_timeout_seconds,
                requests_per_second=settings.requests_per_second,
            ) as sec_client:
                entries = _collect_index_entries(
                    sec_client=sec_client,
                    mode=options.mode,
                    window_start=window.start_date,
                    window_end=window.end_date,
                    checkpoint=checkpoint,
                    stats=stats,
                    form_types=handler["form_types"],
                )
                if options.limit_filings is not None:
                    entries = entries[: options.limit_filings]

                for entry in entries:
                    stats["candidate_filings"] += 1
                    try:
                        parsed_filing, artifacts = _download_and_parse_filing(
                            sec_client=sec_client,
                            artifact_store=artifact_store,
                            entry=entry,
                            handler=handler,
                        )
                        if not options.dry_run:
                            fingerprint = handler["artifact_fingerprint"](artifacts)
                            handler["mark_processing_state"](
                                connection,
                                accession_number=parsed_filing.accession_number,
                                status="RUNNING",
                                artifact_hash=fingerprint,
                            )
                            handler["upsert_parsed_filing"](
                                connection,
                                filing=parsed_filing,
                                artifacts=artifacts,
                            )
                            connection.commit()
                            handler["mark_processing_state"](
                                connection,
                                accession_number=parsed_filing.accession_number,
                                status="SUCCESS",
                                artifact_hash=fingerprint,
                            )
                            if options.mode in {"full", "daily"}:
                                save_checkpoint(
                                    connection,
                                    filing_family=handler["filing_family"],
                                    mode=options.mode,
                                    filed_date=parsed_filing.filed_date,
                                    accession_number=parsed_filing.accession_number,
                                )
                        stats["processed_filings"] += 1
                    except Exception as exc:
                        LOGGER.exception("Failed to process accession %s", entry.accession_number)
                        connection.rollback()
                        if not options.dry_run:
                            handler["mark_processing_state"](
                                connection,
                                accession_number=entry.accession_number,
                                status="FAILED",
                                artifact_hash=None,
                                error_message=str(exc),
                            )
                        stats["failed_filings"] += 1

            if (
                not options.dry_run
                and options.refresh_analytics
                and handler["refresh_analytics"]
                and stats["processed_filings"] > 0
            ):
                refreshed = refresh_analytics_views(connection)
                stats["analytics_views_refreshed"] = len(refreshed)
                LOGGER.info("Refreshed analytics views: %s", ", ".join(refreshed))

            final_status = "SUCCESS" if stats["failed_filings"] == 0 else "PARTIAL_SUCCESS"
            finish_ingestion_run(
                connection,
                run_id=run_id,
                status=final_status,
                details_json=json.dumps(stats),
            )
            return 0 if stats["failed_filings"] == 0 else 1
        except Exception as exc:
            connection.rollback()
            finish_ingestion_run(
                connection,
                run_id=run_id,
                status="FAILED",
                details_json=json.dumps(stats),
                error_message=str(exc),
            )
            raise


def run_reprocess(settings: Settings, options: ReprocessOptions) -> int:
    handler = _handler_for_family(options.filing_family)
    with connect_db(settings.require_db()) as connection:
        run_id = start_ingestion_run(
            connection,
            filing_family=handler["filing_family"],
            mode="reprocess",
            from_date=options.from_date,
            to_date=options.to_date,
            details_json=json.dumps({"accession": options.accession}),
        )
        stats = {
            "processed_filings": 0,
            "failed_filings": 0,
            "analytics_views_refreshed": 0,
        }
        try:
            for filing_record in list_filings_for_reprocess(
                connection,
                filing_family=handler["filing_family"],
                accession=options.accession,
                from_date=options.from_date,
                to_date=options.to_date,
            ):
                try:
                    artifacts = list_artifacts_for_accession(connection, filing_record.accession_number)
                    parsed_filing = _reparse_cached_filing(filing_record, artifacts, handler=handler)
                    fingerprint = handler["artifact_fingerprint"](artifacts)
                    handler["mark_processing_state"](
                        connection,
                        accession_number=parsed_filing.accession_number,
                        status="RUNNING",
                        artifact_hash=fingerprint,
                    )
                    handler["upsert_parsed_filing"](
                        connection,
                        filing=parsed_filing,
                        artifacts=artifacts,
                    )
                    connection.commit()
                    handler["mark_processing_state"](
                        connection,
                        accession_number=parsed_filing.accession_number,
                        status="SUCCESS",
                        artifact_hash=fingerprint,
                    )
                    stats["processed_filings"] += 1
                except Exception as exc:
                    LOGGER.exception(
                        "Failed to reprocess accession %s",
                        filing_record.accession_number,
                    )
                    connection.rollback()
                    handler["mark_processing_state"](
                        connection,
                        accession_number=filing_record.accession_number,
                        status="FAILED",
                        artifact_hash=None,
                        error_message=str(exc),
                    )
                    stats["failed_filings"] += 1

            if options.refresh_analytics and handler["refresh_analytics"] and stats["processed_filings"] > 0:
                refreshed = refresh_analytics_views(connection)
                stats["analytics_views_refreshed"] = len(refreshed)
                LOGGER.info("Refreshed analytics views: %s", ", ".join(refreshed))

            final_status = "SUCCESS" if stats["failed_filings"] == 0 else "PARTIAL_SUCCESS"
            finish_ingestion_run(
                connection,
                run_id=run_id,
                status=final_status,
                details_json=json.dumps(stats),
            )
            return 0 if stats["failed_filings"] == 0 else 1
        except Exception as exc:
            connection.rollback()
            finish_ingestion_run(
                connection,
                run_id=run_id,
                status="FAILED",
                details_json=json.dumps(stats),
                error_message=str(exc),
            )
            raise


def _collect_index_entries(
    *,
    sec_client: SecClient,
    mode: str,
    window_start: date,
    window_end: date,
    checkpoint: CheckpointValue | None,
    stats: dict[str, int],
    form_types: frozenset[str],
) -> list[IndexEntry]:
    entries: list[IndexEntry] = []
    for url in index_urls_for_window(
        DateWindow(mode=mode, start_date=window_start, end_date=window_end)
    ):
        payload = sec_client.get_bytes(url, allow_404=True)
        if payload is None:
            continue
        stats["index_files_seen"] += 1
        index_text = decode_index_payload(url, payload)
        filtered_entries = filter_entries(
            entries=parse_master_idx(index_text),
            form_types=form_types,
            start_date=window_start,
            end_date=window_end,
        )
        for entry in filtered_entries:
            if should_skip_for_checkpoint(entry.filed_date, entry.accession_number, checkpoint):
                stats["skipped_filings"] += 1
                continue
            entries.append(entry)

    entries.sort(key=lambda entry: (entry.filed_date, entry.accession_number))
    return entries


def _download_and_parse_filing(
    *,
    sec_client: SecClient,
    artifact_store: ArtifactStore,
    entry: IndexEntry,
    handler: dict[str, object],
) -> tuple[object, list[StoredArtifact]]:
    if handler["filing_family"] == "PERIODIC_REPORTS":
        return _download_and_parse_periodic(
            sec_client=sec_client,
            artifact_store=artifact_store,
            entry=entry,
        )
    return _download_and_parse_thirteenf(
        sec_client=sec_client,
        artifact_store=artifact_store,
        entry=entry,
    )


def _download_and_parse_thirteenf(
    *,
    sec_client: SecClient,
    artifact_store: ArtifactStore,
    entry: IndexEntry,
) -> tuple[object, list[StoredArtifact]]:
    directory_index_bytes = sec_client.get_bytes(entry.directory_index_url)
    submission_bytes = sec_client.get_bytes(entry.archive_url)
    submission_text = submission_bytes.decode("utf-8", errors="replace")
    submission_header = parse_submission_header(submission_text)
    submission_documents = parse_submission_documents(submission_text)
    primary_document, information_document = select_thirteenf_documents(
        entry.form_type,
        submission_documents,
    )

    artifacts = [
        artifact_store.save_bytes(
            entry.accession_number,
            "directory_index",
            entry.directory_index_url,
            "index.json",
            directory_index_bytes,
            content_type="application/json",
        ),
        artifact_store.save_bytes(
            entry.accession_number,
            "submission_text",
            entry.archive_url,
            Path(entry.archive_path).name,
            submission_bytes,
            content_type="text/plain",
        ),
    ]

    primary_url = f"{entry.filing_directory_url}/{primary_document.filename}"
    primary_bytes = sec_client.get_bytes(primary_url)
    artifacts.append(
        artifact_store.save_bytes(
            entry.accession_number,
            "primary_xml",
            primary_url,
            primary_document.filename,
            primary_bytes,
            content_type="application/xml",
        )
    )

    information_bytes = None
    if information_document is not None:
        information_url = f"{entry.filing_directory_url}/{information_document.filename}"
        information_bytes = sec_client.get_bytes(information_url)
        artifacts.append(
            artifact_store.save_bytes(
                entry.accession_number,
                "information_table_xml",
                information_url,
                information_document.filename,
                information_bytes,
                content_type="application/xml",
            )
        )

    parsed_filing = parse_thirteenf(
        entry,
        submission_type=entry.form_type,
        acceptance_datetime=submission_header.acceptance_datetime,
        primary_document_filename=primary_document.filename,
        information_table_filename=(
            information_document.filename if information_document is not None else None
        ),
        primary_xml=primary_bytes,
        information_table_xml=information_bytes,
        index_url=entry.directory_index_url,
    )

    return parsed_filing, artifacts


def _download_and_parse_periodic(
    *,
    sec_client: SecClient,
    artifact_store: ArtifactStore,
    entry: IndexEntry,
) -> tuple[object, list[StoredArtifact]]:
    directory_index_bytes = sec_client.get_bytes(entry.directory_index_url)
    submission_bytes = sec_client.get_bytes(entry.archive_url)
    submission_text = submission_bytes.decode("utf-8", errors="replace")
    submission_header = parse_submission_header(submission_text)
    submission_documents = parse_submission_documents(submission_text)
    selection = select_periodic_documents(entry.form_type, submission_documents)

    artifacts = [
        artifact_store.save_bytes(
            entry.accession_number,
            "directory_index",
            entry.directory_index_url,
            "index.json",
            directory_index_bytes,
            content_type="application/json",
        ),
        artifact_store.save_bytes(
            entry.accession_number,
            "submission_text",
            entry.archive_url,
            Path(entry.archive_path).name,
            submission_bytes,
            content_type="text/plain",
        ),
    ]

    primary_url = f"{entry.filing_directory_url}/{selection.primary_document.filename}"
    primary_bytes = sec_client.get_bytes(primary_url)
    artifacts.append(
        artifact_store.save_bytes(
            entry.accession_number,
            "primary_document",
            primary_url,
            selection.primary_document.filename,
            primary_bytes,
            content_type="text/html",
        )
    )

    for index, document in enumerate(selection.xbrl_documents, start=1):
        artifact_url = f"{entry.filing_directory_url}/{document.filename}"
        artifact_bytes = sec_client.get_bytes(artifact_url)
        artifacts.append(
            artifact_store.save_bytes(
                entry.accession_number,
                f"xbrl_artifact_{index}",
                artifact_url,
                document.filename,
                artifact_bytes,
                content_type="application/xml",
            )
        )

    parsed_filing = parse_periodic_report(
        entry,
        acceptance_datetime=submission_header.acceptance_datetime,
        primary_document_filename=selection.primary_document.filename,
        primary_document=primary_bytes,
        index_url=entry.directory_index_url,
    )
    return parsed_filing, artifacts


def _reparse_cached_filing(
    filing_record: object,
    artifacts: list[StoredArtifact],
    *,
    handler: dict[str, object],
) -> object:
    if handler["filing_family"] == "PERIODIC_REPORTS":
        return _reparse_cached_periodic(filing_record, artifacts)
    return _reparse_cached_thirteenf(filing_record, artifacts)


def _reparse_cached_thirteenf(filing_record: object, artifacts: list[StoredArtifact]) -> object:
    artifact_map = {artifact.role: artifact for artifact in artifacts}
    submission_text = artifact_map["submission_text"].local_path.read_text(
        encoding="utf-8",
        errors="replace",
    )
    submission_header = parse_submission_header(submission_text)
    primary_bytes = artifact_map["primary_xml"].local_path.read_bytes()
    information_bytes = (
        artifact_map["information_table_xml"].local_path.read_bytes()
        if "information_table_xml" in artifact_map
        else None
    )
    entry = filing_record.to_index_entry()
    return parse_thirteenf(
        entry,
        submission_type=filing_record.form_type,
        acceptance_datetime=submission_header.acceptance_datetime,
        primary_document_filename=filing_record.primary_document_filename,
        information_table_filename=filing_record.information_table_filename,
        primary_xml=primary_bytes,
        information_table_xml=information_bytes,
        index_url=filing_record.index_url,
    )


def _reparse_cached_periodic(filing_record: object, artifacts: list[StoredArtifact]) -> object:
    artifact_map = {artifact.role: artifact for artifact in artifacts}
    submission_text = artifact_map["submission_text"].local_path.read_text(
        encoding="utf-8",
        errors="replace",
    )
    submission_header = parse_submission_header(submission_text)
    primary_bytes = artifact_map["primary_document"].local_path.read_bytes()
    return parse_periodic_report(
        filing_record.to_index_entry(),
        acceptance_datetime=submission_header.acceptance_datetime,
        primary_document_filename=filing_record.primary_document_filename,
        primary_document=primary_bytes,
        index_url=filing_record.index_url,
    )


def _handler_for_family(
    filing_family: str,
    *,
    form_type: str = "all",
    include_amendments: bool = True,
) -> dict[str, object]:
    normalized = filing_family.upper()
    if normalized == "13F":
        return {
            "filing_family": "13F",
            "form_types": THIRTEENF_FORM_TYPES,
            "artifact_fingerprint": artifact_fingerprint,
            "mark_processing_state": mark_processing_state,
            "upsert_parsed_filing": upsert_parsed_filing,
            "refresh_analytics": True,
        }
    if normalized in {"PERIODIC", "PERIODIC_REPORTS"}:
        form_types = _periodic_form_types(form_type, include_amendments=include_amendments)
        return {
            "filing_family": "PERIODIC_REPORTS",
            "form_types": form_types,
            "artifact_fingerprint": periodic_artifact_fingerprint,
            "mark_processing_state": periodic_mark_processing_state,
            "upsert_parsed_filing": periodic_upsert_parsed_filing,
            "refresh_analytics": False,
        }
    raise ValueError(f"Unsupported filing family: {filing_family}")


def _periodic_form_types(form_type: str, *, include_amendments: bool) -> frozenset[str]:
    normalized = form_type.upper()
    if normalized == "ALL":
        base = {"10-K", "10-Q"}
    elif normalized in {"10-K", "10-Q"}:
        base = {normalized}
    else:
        raise ValueError("form_type must be one of: all, 10-K, 10-Q")
    if include_amendments:
        base |= {f"{form}/A" for form in list(base)}
    return frozenset(base & set(PERIODIC_REPORT_FORM_TYPES))
