# Overcall API

The API is a Python 3.11+ FastAPI service. It connects directly to Supabase
Postgres through the transaction-mode pooler; the browser does not query the
database.

## Local setup

1. Start the disposable PostgreSQL 15 database from the repository root:
   `docker compose -f docker-compose.dev.yml up -d postgres`.
2. Copy `.env.example` to `.env` and set local-only values.
3. Install the API and development dependencies with `python -m pip install -e . -r requirements-dev.txt`.
4. From `apps/api`, run `uvicorn overcall.main:app --reload`.
5. `GET /healthz` is database-independent. `GET /readyz` checks the database.

Never put real provider credentials, Supabase service-role keys, or live Stripe
keys in this local sample file. The Supabase service-role key is optional and
must remain unset unless the separately planned account-deletion feature is
enabled.

## Tests

Run `pytest` from this directory. CI runs Ruff and the API unit/security tests.
PostgreSQL integration tests, including ingest-key lifecycle and tenant isolation,
require a local Postgres database and `TEST_DATABASE_URL`.
The CI job initializes a fresh database and applies the tracked migrations
before running tests.

Provider pricing is versioned in `overcall/pricing/files`. Prices are stored in
USD and include a retrieval date and source URL. Run
`python scripts/check_pricing_age.py` to report files older than 90 days.

Migrations in this branch have not been applied to any Supabase project.
