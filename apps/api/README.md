# Overcall API

The API is a Python 3.11+ FastAPI service. It connects directly to Supabase
Postgres through the transaction-mode pooler; the browser does not query the
database.

## Local setup

1. Start the disposable PostgreSQL 15 database from the repository root:
   `docker compose -f docker-compose.dev.yml up -d postgres`.
2. Copy `.env.example` to `.env` and set local-only values.
3. Install development dependencies with `python -m pip install -r requirements-dev.txt`.
4. From `apps/api`, run `uvicorn overcall.main:app --reload`.
5. `GET /healthz` is database-independent. `GET /readyz` checks the database.

Never put real provider credentials, Supabase service-role keys, or live Stripe
keys in this local sample file. The Supabase service-role key is optional and
must remain unset unless the separately planned account-deletion feature is
enabled.

## Tests

Run `pytest` from this directory. CI runs Ruff on the B1/B2 implementation and
tests; some carried-over prototype modules still need cleanup during their
planned migration.
Schema-parity integration tests require the local Postgres database and a
`TEST_DATABASE_URL`; the CI job initializes a fresh database and applies the
tracked migrations before running tests.

Provider pricing is versioned in `overcall/pricing/files`. Prices are stored in
USD and include a retrieval date and source URL. Run
`python scripts/check_pricing_age.py` to report files older than 90 days.

Migrations in this branch have not been applied to any Supabase project.
