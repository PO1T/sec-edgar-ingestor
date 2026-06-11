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
    enable_vector_parser = db_subparsers.add_parser(
        "enable-vector",
        help="Install pgvector for semantic periodic retrieval when available",
    )
    enable_vector_parser.add_argument("--profile", default=None)

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
    periodic_parser = ingest_subparsers.add_parser(
        "periodic",
        help="Ingest 10-K and 10-Q periodic reports",
    )
    periodic_parser.add_argument("--mode", choices=["dev", "full", "daily"], required=True)
    periodic_parser.add_argument("--from-date", type=_parse_date)
    periodic_parser.add_argument("--to-date", type=_parse_date)
    periodic_parser.add_argument("--limit-filings", type=int)
    periodic_parser.add_argument("--dry-run", action="store_true")
    periodic_parser.add_argument(
        "--form-type",
        choices=["all", "10-K", "10-Q"],
        default="all",
        help="Restrict periodic ingestion to one base form type",
    )
    periodic_parser.add_argument(
        "--exclude-amendments",
        action="store_true",
        help="Exclude 10-K/A and 10-Q/A amendments",
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
    reprocess_periodic = reprocess_subparsers.add_parser(
        "periodic",
        help="Reprocess cached 10-K and 10-Q periodic reports",
    )
    reprocess_periodic.add_argument("--accession")
    reprocess_periodic.add_argument("--from-date", type=_parse_date)
    reprocess_periodic.add_argument("--to-date", type=_parse_date)

    embeddings_parser = subparsers.add_parser(
        "embeddings",
        help="Embedding utilities",
    )
    embeddings_subparsers = embeddings_parser.add_subparsers(
        dest="embeddings_command",
        required=True,
    )
    embeddings_backfill = embeddings_subparsers.add_parser(
        "backfill",
        help="Backfill vector embeddings",
    )
    embeddings_backfill_subparsers = embeddings_backfill.add_subparsers(
        dest="embeddings_family",
        required=True,
    )
    embeddings_periodic = embeddings_backfill_subparsers.add_parser(
        "periodic",
        help="Backfill periodic report chunk embeddings",
    )
    embeddings_periodic.add_argument("--profile")
    embeddings_periodic.add_argument("--limit", type=int)
    embeddings_periodic.add_argument("--batch-size", type=int)
    embeddings_periodic.add_argument("--cik")
    embeddings_periodic.add_argument("--ticker")
    embeddings_periodic.add_argument(
        "--form-type",
        choices=["all", "10-K", "10-Q"],
        default="all",
    )
    embeddings_periodic.add_argument("--filed-from", type=_parse_date)
    embeddings_periodic.add_argument("--filed-to", type=_parse_date)
    embeddings_periodic.add_argument("--rebuild", action="store_true")
    embeddings_periodic.add_argument("--dry-run", action="store_true")

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
    if args.command == "db" and args.db_command == "enable-vector":
        from sec_edgar_ingestor.filings.periodic.embeddings import (
            enable_vector_for_profile,
        )

        with connect_db(settings.require_db()) as connection:
            profile = enable_vector_for_profile(
                connection,
                profile_name=args.profile or settings.embedding_profile_name,
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
            )
        print(f"vector:{profile.profile_name}:{profile.embedding_dimension}")
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
            filing_family="13F",
            dry_run=args.dry_run,
            refresh_analytics=not args.skip_analytics_refresh,
        )
        return run_ingest(settings, options)

    if args.command == "ingest" and args.filing_family == "periodic":
        options = IngestOptions(
            mode=args.mode,
            from_date=args.from_date,
            to_date=args.to_date,
            limit_filings=args.limit_filings,
            filing_family="PERIODIC_REPORTS",
            dry_run=args.dry_run,
            refresh_analytics=False,
            form_type=args.form_type,
            include_amendments=not args.exclude_amendments,
        )
        return run_ingest(settings, options)

    if args.command == "reprocess" and args.reprocess_family == "13f":
        options = ReprocessOptions(
            accession=args.accession,
            from_date=args.from_date,
            to_date=args.to_date,
            filing_family="13F",
            refresh_analytics=not args.skip_analytics_refresh,
        )
        return run_reprocess(settings, options)

    if args.command == "reprocess" and args.reprocess_family == "periodic":
        options = ReprocessOptions(
            accession=args.accession,
            from_date=args.from_date,
            to_date=args.to_date,
            filing_family="PERIODIC_REPORTS",
            refresh_analytics=False,
        )
        return run_reprocess(settings, options)

    if (
        args.command == "embeddings"
        and args.embeddings_command == "backfill"
        and args.embeddings_family == "periodic"
    ):
        from sec_edgar_ingestor.filings.periodic.embeddings import (
            BackfillOptions,
            run_periodic_embedding_backfill,
        )

        return run_periodic_embedding_backfill(
            settings,
            options=BackfillOptions(
                profile_name=args.profile,
                limit=args.limit,
                batch_size=args.batch_size,
                cik=args.cik,
                ticker=args.ticker,
                form_type=args.form_type,
                filed_from=args.filed_from,
                filed_to=args.filed_to,
                rebuild=args.rebuild,
                dry_run=args.dry_run,
            ),
        )

    parser.error("Unsupported command")
    return 2
