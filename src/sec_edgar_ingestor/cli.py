from __future__ import annotations

import argparse
from datetime import date

from sec_edgar_ingestor.config import Settings
from sec_edgar_ingestor.db.analytics import refresh_analytics_views
from sec_edgar_ingestor.db.connection import connect_db
from sec_edgar_ingestor.db.migrations import apply_migrations
from sec_edgar_ingestor.logging import configure_logging


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sec-edgar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    db_parser = subparsers.add_parser("db", help="Database utilities")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)
    db_subparsers.add_parser("migrate", help="Apply SQL migrations")
    db_subparsers.add_parser(
        "refresh-analytics",
        help="Refresh analytics materialized views",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Ingest filings")
    ingest_subparsers = ingest_parser.add_subparsers(dest="filing_family", required=True)
    thirteenf_parser = ingest_subparsers.add_parser("13f", help="Ingest 13F filings")
    thirteenf_parser.add_argument("--mode", choices=["dev", "full", "daily"], required=True)
    thirteenf_parser.add_argument("--from-date", type=_parse_date)
    thirteenf_parser.add_argument("--to-date", type=_parse_date)
    thirteenf_parser.add_argument("--limit-filings", type=int)
    thirteenf_parser.add_argument("--dry-run", action="store_true")
    thirteenf_parser.add_argument(
        "--skip-analytics-refresh",
        action="store_true",
        help="Skip refreshing analytics materialized views after ingestion",
    )

    reprocess_parser = subparsers.add_parser("reprocess", help="Reprocess cached filings")
    reprocess_subparsers = reprocess_parser.add_subparsers(
        dest="reprocess_family",
        required=True,
    )
    reprocess_thirteenf = reprocess_subparsers.add_parser(
        "13f",
        help="Reprocess cached 13F filings",
    )
    reprocess_thirteenf.add_argument("--accession")
    reprocess_thirteenf.add_argument("--from-date", type=_parse_date)
    reprocess_thirteenf.add_argument("--to-date", type=_parse_date)
    reprocess_thirteenf.add_argument(
        "--skip-analytics-refresh",
        action="store_true",
        help="Skip refreshing analytics materialized views after reprocessing",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    if args.command == "db" and args.db_command == "migrate":
        with connect_db(settings.require_db()) as connection:
            applied = apply_migrations(connection)
        for version in applied:
            print(version)
        return 0
    if args.command == "db" and args.db_command == "refresh-analytics":
        with connect_db(settings.require_db()) as connection:
            refreshed = refresh_analytics_views(connection)
        for name in refreshed:
            print(name)
        return 0

    from sec_edgar_ingestor.pipeline.orchestrator import (
        IngestOptions,
        ReprocessOptions,
        run_ingest,
        run_reprocess,
    )

    if args.command == "ingest" and args.filing_family == "13f":
        options = IngestOptions(
            mode=args.mode,
            from_date=args.from_date,
            to_date=args.to_date,
            limit_filings=args.limit_filings,
            dry_run=args.dry_run,
            refresh_analytics=not args.skip_analytics_refresh,
        )
        return run_ingest(settings, options)

    if args.command == "reprocess" and args.reprocess_family == "13f":
        options = ReprocessOptions(
            accession=args.accession,
            from_date=args.from_date,
            to_date=args.to_date,
            refresh_analytics=not args.skip_analytics_refresh,
        )
        return run_reprocess(settings, options)

    parser.error("Unsupported command")
    return 2
