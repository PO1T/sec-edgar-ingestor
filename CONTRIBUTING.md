# Contributing

## Development Principles

- Keep the repository reproducible and environment-neutral.
- Prefer small commits with clear intent.
- Update documentation when behavior, architecture, or assumptions change.
- Add tests for parsing, normalization, loading, and checkpoint logic.

## Local Development

The intended workflow is:

1. Create a Python 3.10 virtual environment.
2. Install the package in editable mode with test dependencies.
3. Configure PostgreSQL and set environment variables from `.env.example`.
4. Run migrations.
5. Run ingestion in `dev` mode before attempting wider backfills.

## Pull Request Expectations

- Keep changes coherent and reviewable.
- Call out tradeoffs and unresolved questions.
- Avoid introducing private paths, hidden dependencies, or machine-local assumptions.
