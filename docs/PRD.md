# Overcall — PRD

## Original problem statement
Web tool that sits between a developer's app and paid APIs (OpenAI, Stripe, AWS stub). It logs traffic metadata, detects wasteful usage with tiered rules, and shows quantified savings in a calm, beginner-friendly dashboard (Overview / Issues / Providers / Settings). Logs come from a seedable synthetic generator and a live proxy. No auth in v1. Full brief in the first user message (colors, fonts, tiers, build order, hardening notes).

## User choices
- Currency: INR by default, with a USD switch (and exchange rate) in Settings
- One-click "Load synthetic data" button in the empty state
- OpenAI proxy: local mock by default, optional pass-through to real OpenAI with the user's own key
- Frontend in TypeScript
- Stripe proxy verified with the env test key (sk_test_emergent → Emergent Stripe test gateway)

## Architecture
- Backend (FastAPI, `/app/backend/costguard/`): `proxy.py` (/api/proxy/{openai|stripe|aws}/…), `mock_llm.py` (in-process via ASGITransport, also at /api/mock/openai), `rules/` (7 plugin rules, one interface), `engine.py` (runs rules, per-request max-waste dedupe, version-based freshness), `pricing/*.json` (versioned), `synthetic.py` (seedable, ground-truth labels, CLI), `api.py`, `settings_store.py`
- Mongo: request_logs (TTL 30d on timestamp, provider+timestamp index), issues, settings, detection_runs
- Frontend (React + TS + Tailwind + Recharts + shadcn): pages Overview / Issues / Providers / Settings; theme in localStorage; money is converted from USD on the client

## Implemented (2026-06)
- Log schema, versioned pricing configs, synthetic generator (7.2k logs/7 days, seed 42) with ground truth
- Tier 1: duplicate_calls, missing_cache, retry_storm. Tier 2: oversized_payload, unbatched_calls. Tier 3 (gated): token_bloat, model_overuse, with confidence scores. 100% precision and recall on the synthetic ground truth
- Hero savings counts Tier 1 + 2 only; Tier 3 is shown separately
- Proxy: OpenAI mock/real; Stripe test mode (live keys rejected); AWS returns 501; keys are forwarded only; payload hash and metadata only
- Dashboard: empty state with copyable proxy URL and snippets; hero, trend chart, top issues with inline expand; filterable Issues; Providers with status and pricing; Settings (theme, currency, rate, rule toggles, experimental gate, windows, upstream, data load/clear, accuracy table)
- Tests: backend/tests/test_detection.py (pure), backend/tests/test_costguard_api.py (API) — 20/20 passing

## Known limitations
- Emergent Stripe test gateway supports only some routes (checkout session create works; retrieve returns 404)
- Streaming OpenAI responses are buffered (no SSE pass-through)
- Detection re-runs on the full log set (fine for v1 volumes)

## Backlog
- P1: Per-issue "mark resolved" and savings-realized tracking
- P1: Log explorer (recent proxied requests list with filters)
- P1: Caller-context breakdown (which service wastes most)
- P2: AWS rules (S3 GET caching, Lambda retries); multi-tenant + auth; scheduled weekly savings digest email
- P2: Node proxy for lower latency; time-series storage for high volume
