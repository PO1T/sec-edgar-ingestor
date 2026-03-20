from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sec_edgar_ingestor.config import Settings
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
    dry_run: bool = False


@dataclass(frozen=True)
class ReprocessOptions:
    accession: str | None
    from_date: date | None
    to_date: date | None


def run_ingest(settings: Settings, options: IngestOptions) -> int:
    with connect_db(settings.require_db()) as connection:
        checkpoint = (
            load_checkpoint(
                connection,
                filing_family="13F",
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
            filing_family="13F",
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
                        )
                        if not options.dry_run:
                            fingerprint = artifact_fingerprint(artifacts)
                            mark_processing_state(
                                connection,
                                accession_number=parsed_filing.accession_number,
                                status="RUNNING",
                                artifact_hash=fingerprint,
                            )
                            upsert_parsed_filing(
                                connection,
                                filing=parsed_filing,
                                artifacts=artifacts,
                            )
                            connection.commit()
                            mark_processing_state(
                                connection,
                                accession_number=parsed_filing.accession_number,
                                status="SUCCESS",
                                artifact_hash=fingerprint,
                            )
                            if options.mode in {"full", "daily"}:
                                save_checkpoint(
                                    connection,
                                    filing_family="13F",
                                    mode=options.mode,
                                    filed_date=parsed_filing.filed_date,
                                    accession_number=parsed_filing.accession_number,
                                )
                        stats["processed_filings"] += 1
                    except Exception as exc:
                        LOGGER.exception("Failed to process accession %s", entry.accession_number)
                        connection.rollback()
                        if not options.dry_run:
                            mark_processing_state(
                                connection,
                                accession_number=entry.accession_number,
                                status="FAILED",
                                artifact_hash=None,
                                error_message=str(exc),
                            )
                        stats["failed_filings"] += 1

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
    with connect_db(settings.require_db()) as connection:
        run_id = start_ingestion_run(
            connection,
            filing_family="13F",
            mode="reprocess",
            from_date=options.from_date,
            to_date=options.to_date,
            details_json=json.dumps({"accession": options.accession}),
        )
        stats = {"processed_filings": 0, "failed_filings": 0}
        try:
            for filing_record in list_filings_for_reprocess(
                connection,
                filing_family="13F",
                accession=options.accession,
                from_date=options.from_date,
                to_date=options.to_date,
            ):
                try:
                    artifacts = list_artifacts_for_accession(connection, filing_record.accession_number)
                    parsed_filing = _reparse_cached_filing(filing_record, artifacts)
                    fingerprint = artifact_fingerprint(artifacts)
                    mark_processing_state(
                        connection,
                        accession_number=parsed_filing.accession_number,
                        status="RUNNING",
                        artifact_hash=fingerprint,
                    )
                    upsert_parsed_filing(
                        connection,
                        filing=parsed_filing,
                        artifacts=artifacts,
                    )
                    connection.commit()
                    mark_processing_state(
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
                    mark_processing_state(
                        connection,
                        accession_number=filing_record.accession_number,
                        status="FAILED",
                        artifact_hash=None,
                        error_message=str(exc),
                    )
                    stats["failed_filings"] += 1

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
            form_types=THIRTEENF_FORM_TYPES,
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


def _reparse_cached_filing(filing_record: object, artifacts: list[StoredArtifact]) -> object:
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
