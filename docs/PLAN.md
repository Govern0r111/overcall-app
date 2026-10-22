# Overcall v1 — implementation plan

| | |
|---|---|
| Status | **B1–B10 and frontend F1–F8 implemented. B11 and integration modules remain.** |
| Date | 2026-10-22 |
| Strategy | **Migrate in place** (confirmed): keep what works, move it module by module to the target stack and layout |
| Product name | **Overcall** everywhere (confirmed). Headers are `X-Overcall-Key` and `X-Overcall-Caller`. Ingest keys start with `oc_`. The old "API Cost Guard" and `X-CostGuard-*` names are retired |
| Tenancy | **One workspace per user, many revocable ingest keys** (confirmed). `X-Overcall-Caller` labels the code path |
| Effort scale | S ≈ 1 focused session (~3 h), M ≈ 2–3 sessions, L ≈ 4–6 sessions |

## How to use this document

- Sections 1–3 are shared context. Section 4 holds the modules (4A frontend F1–F8, 4B backend B1–B11, 4C integration I1–I3). Section 5 holds the deep designs. Section 6 is the risk register, 7 is the build order, 8 is the first-session task list.
- **Every module is self-contained.** Each one lists its own *contract slice* (the exact shapes it consumes or produces), files, ordered tasks, tests, edge cases and a done-when checklist. To build one module later, hand me that module's section plus §3.4 (error format) and any `§5.x` design it cites (Appendix B). Nothing else is needed.
- Frontend and backend never import each other's code. They share only **data files** in `contract/` (OpenAPI, JSON fixtures, thresholds, error codes). See §3.5.
- Money is stored and computed in **USD**. INR is a display conversion in the UI only.

### Decisions I made that you can veto

| # | Decision | Why |
|---|---|---|
| D1 | Schema lives in plain SQL files in `supabase/migrations/`, applied with the Supabase CLI. SQLModel models mirror it and a test checks they match. **No Alembic.** | RLS, partial indexes, `pg_cron` and advisory locks need raw SQL anyway. One source of truth is easier for a solo developer |
| D2 | The backend connects to Postgres directly through the **Supabase pooler** (`DATABASE_URL`), not through `supabase-py` and not with the service-role key | Needed for real transactions ("reruns replace issues in one transaction"). Render's network is IPv4 only and Supabase's direct connection is IPv6, so the pooler is required. Removes the service-role key from the backend (least privilege) |
| D3 | Tenant isolation is enforced in application code (every repository method takes `user_id`). RLS is also enabled with **zero policies** and table privileges are revoked from `anon` and `authenticated`, so the Supabase Data API cannot read these tables | The backend role bypasses RLS, so RLS is defense in depth, not the primary control. A two-user isolation test proves the real control |
| D4 | The browser **never** queries Supabase tables. It only uses Supabase Auth, and calls our API with the Supabase JWT | One enforcement point for authorization, and one contract |
| D5 | Contract source of truth is **`contract/openapi.yaml`** plus fixtures. Frontend generates TS types from it. Backend has a drift test against FastAPI's generated OpenAPI. Both sides validate fixtures with a JSON-Schema validator | One schema, two validators, no duplicated zod response schemas |
| D6 | Ingest key = `oc_` + 43 URL-safe random chars. Stored as **HMAC-SHA256(pepper, key)** hex. Plaintext is returned once | Keys are 256-bit random, so a fast keyed hash is correct. A pepper protects against a DB-only leak |
| D7 | The mock OpenAI upstream runs **in-process** through httpx's ASGI transport, never as a public route | No extra Render service. Nothing public to attack. The user's `Authorization` header is stripped before the mock sees it |
| D8 | The proxy sends `Accept-Encoding: identity` upstream and drops hop-by-hop headers. Request bytes are forwarded exactly as received (never re-serialised) | Keeps SSE unbuffered and usage parsing simple. Body integrity is preserved |
| D9 | Logging is **fail-open** (a logging problem never fails the customer's request). Authentication is **fail-closed** | Proxy priority is correctness of the customer's traffic |
| D10 | The public demo is **client-only**: "Continue as demo" runs the real UI against in-browser MSW fixtures. Zero backend calls, and it works even when Render is asleep | Honors "require auth before anything is publicly reachable" without gating the demo. Also hides cold starts |
| D11 | Detection reads the last 30 days (max 200 000 rows) and runs in a worker thread. Headline savings use **per-request max across Tier 1+2 rules**, so one request is never counted twice | Avoids double counting and bounds CPU on a free Render instance |
| D12 | A log row has an `origin` column (`upstream` or `overcall`). Errors that Overcall itself produced (bad key, live Stripe key, rate limit) are logged but ignored by every detection rule | Prevents our own rejections being flagged as the customer's retry storms |
| D13 | Response hashes are **not** stored. Only request hash, sizes, tokens, status, latency and cost | OpenAI responses differ on every call (id, created), so a response hash would not help detection and would add storage |
| D14 | Add a `C0` step (contract bootstrap, size S) before F3. It is not a module. It creates the `contract/` files described in §3 | F3 and B1 both need the fixtures and the OpenAPI file to exist first |

---

## 1. Restatement, assumptions, open questions

### 1.1 The project in my words

Overcall is a **metadata-only forwarding proxy plus an analysis dashboard** for people who call paid APIs.

A developer changes their app's base URL to our proxy and adds an `X-Overcall-Key` header. Their real OpenAI or Stripe key stays in their own app and is passed straight through to the provider. The proxy forwards each request unchanged, returns the provider's response unchanged, and in the background records only **metadata**: provider, normalised endpoint, status, latency, byte sizes, token counts, a hash of the canonicalised request, and an estimated cost. It never stores request or response bodies.

A detection engine reads those logs and applies seven rules in three tiers. Tier 1 is deterministic (duplicate calls, missing cache, retry storms). Tier 2 is threshold based (oversized payloads, unbatched calls). Tier 3 is experimental, off by default and always shown with a confidence score and an Experimental badge (token bloat, model overuse). Each finding explains what was seen, why it costs money, how to fix it, and shows sample requests as hashes and sizes only.

The dashboard shows **two separate figures that are never added together**: estimated spend savings (real money, mostly OpenAI) and reliability findings (a count, mostly Stripe where savings are only a modelled overhead). Demo data is always labelled.

Stack: React + Vite on Vercel; FastAPI on Render; Supabase for Postgres and Auth (email and Google). Local development uses a mock OpenAI upstream and Stripe test keys only.

### 1.2 Non-goals for v1

AWS proxying (returns 501), request or response body storage, team workspaces or projects, billing, live Stripe keys, automatic exchange-rate fetching, multi-instance proxy (single instance assumed), alert emails, a public API for third parties.

### 1.3 Assumptions

| # | Assumption |
|---|---|
| A1 | One Render instance for the API in v1, so in-memory rate limiting and the in-memory log queue are acceptable |
| A2 | You will run Docker Desktop locally for a Postgres 15 test database. If not, a dedicated Supabase "dev" project with a throwaway schema is the fallback |
| A3 | USD to INR is a manual setting (default 83.5). It is never fetched automatically |
| A4 | Supabase email confirmation is **on** in production and **off** in dev. The UI handles both |
| A5 | Retention default is 14 days for proxy logs and a cap of 100 000 rows per user, to fit 500 MB |
| A6 | The hosted proxy is called server-to-server. Browsers do not call `/proxy/*` directly, so CORS is disabled there |
| A7 | You have Stripe test-mode keys (free) for I2. No real money ever moves |
| A8 | Pricing numbers in the existing JSON files are re-verified against provider pricing pages in B2 and stamped with `retrieved_at` |
| A9 | The Google OAuth provider you configured in Supabase stays as is. The backend only ever sees a Supabase JWT |
| A10 | Tests may use fake secrets shaped like real ones (`sk_test_FAKE…`). Real secrets are never pasted into tests, chat or fixtures |

### 1.4 Open questions (none block F1)

| # | Question | My default if you don't answer |
|---|---|---|
| OQ1 | **Stripe SDKs and custom headers.** Stripe's Node SDK has no default-headers option. Python, Ruby and the others differ. The ingest key must travel in `X-Overcall-Key` (your design, unchanged). For Stripe I plan setup snippets that add the header through each SDK's custom HTTP client or fetch wrapper, and verify them in I2. If one SDK cannot do it, v1 documents the limitation rather than changing the design | Keep the header design. Verify in I2 |
| OQ2 | Do you want a custom domain for the proxy (for example `proxy.overcall.dev`)? | Use the Render URL until I3 |
| OQ3 | Stripe SDKs that only accept a host (no path prefix) need host-based routing such as `stripe.<proxy-domain>`. Do you want that in v1 or only the path form `/proxy/stripe/v1/…`? | Path form in v1. Host routing in v1.1 if I2 shows it is needed |
| OQ4 | Is the exchange rate a manual number forever, or should a later version fetch it? | Manual |
| OQ5 | Should the plan assume a public demo URL is linked from the README and resume? | Yes. Client-only demo (D10) |

---

## 2. Final repo structure

### 2.1 Target monorepo layout

```
Overcall/
├─ apps/
│  ├─ web/                         # Vite + React + TS + Tailwind  (was frontend/)
│  │  ├─ index.html
│  │  ├─ package.json  vite.config.ts  vitest.config.ts  playwright.config.ts
│  │  ├─ tailwind.config.ts  postcss.config.js  eslint.config.js  tsconfig*.json
│  │  ├─ .env.example
│  │  ├─ public/                   # favicon.svg, og.png, robots.txt, mockServiceWorker.js
│  │  ├─ e2e/                      # Playwright specs
│  │  ├─ scripts/                  # check-design-rules.mjs, gen-api-types.mjs
│  │  └─ src/
│  │     ├─ main.tsx  router.tsx  App.tsx
│  │     ├─ styles/                # tokens.css, globals.css
│  │     ├─ lib/                   # cn.ts, env.ts, theme.ts, format.ts, clipboard.ts
│  │     ├─ api/                   # client.ts, errors.ts, keys.ts, hooks.ts, schema.d.ts (generated)
│  │     ├─ auth/                  # AuthClient.ts, MockAuthClient.ts, SupabaseAuthClient.ts, AuthProvider.tsx, ProtectedRoute.tsx
│  │     ├─ mocks/                 # handlers.ts, state.ts, scenarios.ts, browser.ts, server.ts
│  │     ├─ components/ui/         # Button, Card, Badge, Input, Select, Switch, Tabs, Dialog, Skeleton, Toast
│  │     ├─ components/layout/     # Shell, Sidebar, Topbar, EmptyState, ErrorBoundary
│  │     ├─ features/              # landing/ auth/ overview/ issues/ logs/ providers/ settings/
│  │     └─ test/                  # setup.ts, utils.tsx
│  └─ api/                         # FastAPI  (was backend/, package costguard → overcall)
│     ├─ pyproject.toml  requirements.txt  requirements-dev.txt  pytest.ini  .env.example
│     ├─ overcall/
│     │  ├─ main.py  config.py  errors.py  logging.py  deps.py
│     │  ├─ db/                    # engine.py, models.py, repos/
│     │  ├─ pricing/               # loader.py, cost.py, files/{openai,stripe,aws}/<version>.json
│     │  ├─ synthetic/             # generator.py, scenarios.py, truth.py, cli.py
│     │  ├─ detection/             # base.py, registry.py, thresholds.py, runner.py, rules/*.py
│     │  ├─ api/                   # schemas.py, pagination.py, routers/*.py
│     │  ├─ auth/                  # jwt.py, ingest_keys.py
│     │  ├─ mock_openai/           # app.py, tokens.py
│     │  ├─ proxy/                 # router.py, forward.py, headers.py, hashing.py, extract.py, sse.py, tokens.py, writer.py, ratelimit.py
│     │  ├─ retention/             # purge.py
│     │  └─ accuracy/              # latest.json (copied from validation/reports at build)
│     ├─ scripts/                  # export_openapi.py, check_contract.py, evaluate.py, seed_dev.py, bench_proxy.py, warm_tiktoken.py
│     └─ tests/                    # unit/ integration/ contract/ security/ perf/
├─ contract/                       # DATA ONLY. Shared by web and api. No code imported across apps
│  ├─ README.md
│  ├─ openapi.yaml                 # source of truth for paths and schemas
│  ├─ errors.json                  # error codes, HTTP status, default message
│  ├─ thresholds.json              # default, min, max for every detection threshold
│  ├─ rules.json                   # rule catalogue: id, name, tier, description, default_enabled
│  ├─ pricing.schema.json          # JSON Schema for pricing files
│  ├─ fixtures/
│  │  ├─ me.*.json  overview.{demo,empty,live}.json  issues.{list,empty}.json
│  │  ├─ logs.{page1,page2,empty}.json  logs.detail.json  logs.facets.json
│  │  ├─ providers.json  settings.json  accuracy.json  ingest-keys.json
│  │  ├─ errors/*.json
│  │  ├─ proxy/routes.json         # real proxy routes; snippets and backend routes are both tested against it
│  │  └─ synthetic/small/{logs.json,ground_truth.json}
│  └─ scenarios/                   # MSW scenario manifests: empty, demo, live, error, slow
├─ supabase/
│  ├─ config.toml
│  └─ migrations/                  # 0001_init.sql, 0002_rls_retention.sql, ...
├─ validation/                     # I2: real-traffic validation
│  ├─ README.md  samples.lock      # pinned commit SHAs of the sample apps (clones are gitignored)
│  ├─ scenarios/                   # scripted traffic drivers (Playwright / scripts)
│  ├─ labels/real.v1.csv           # hand labels, frozen before detection is run
│  └─ reports/{synthetic,real}.json
├─ docs/  PLAN.md  PRD.md  adr/
├─ scripts/                        # check-contract.sh, dev.ps1 (start db + api + web)
├─ .github/workflows/              # ci.yml, keepalive.yml
├─ docker-compose.dev.yml          # postgres for tests + dev
├─ vercel.json   render.yaml
└─ README.md  .gitignore  .gitleaks.toml
```

### 2.2 Migration inventory (what happens to each existing file)

| Existing | Target | Action | Module |
|---|---|---|---|
| `frontend/` (CRA, CRACO, React 19, react-router 7, Recharts 3, zod 3, RHF 7) | `apps/web/` | `git mv`, then replace CRACO and react-scripts with Vite. Prune the Emergent plugin and overlay packages | F1 |
| `frontend/src/pages/Landing.tsx` | `features/landing/*` | Split into section components. Rebuild on new tokens. Keep copy that already fits | F1 |
| `frontend/src/pages/AuthPage.tsx`, `auth/authClient.ts`, `lib/supabase.ts` | `features/auth/*`, `auth/*` | Split the single merged client into `MockAuthClient` and `SupabaseAuthClient` behind one interface. Keep the Google button. Fix the "navigate to /app before email confirmation" bug | F2 |
| `components/Sidebar.tsx`, `Topbar.tsx`, `EmptyState.tsx`, `context/AppContext.tsx` | `components/layout/*` | Keep layout ideas. Split the context into Theme, Currency and Auth providers | F3 |
| `pages/Overview.tsx`, `HeroSavings`, `TrendChart`, `DemoBanner` | `features/overview/*` | Rework to the two-figure rule (never summed) | F4 |
| `pages/Issues.tsx`, `IssueRow`, `IssueDetail`, `Badges` | `features/issues/*` | Add URL-synced filters, keyboard expansion, Tier 3 gate | F5 |
| `pages/Logs.tsx` | `features/logs/*` | Currently one long line of JSX with demo rows as fallback. Rebuild with cursor pagination, facets and a dialog panel | F6 |
| `pages/Providers.tsx`, `CopyField`, `PricingTable` | `features/providers/*` | Add ingest-key card and verified snippets | F7 |
| `pages/Settings.tsx`, `components/settings/*` | `features/settings/*` | Add validation, confirmations, accuracy rows | F8 |
| `lib/api.ts` (axios + Supabase token) | `api/client.ts` | Replace axios with a typed fetch client generated from the contract | F3 |
| `backend/server.py` | `overcall/main.py` | App factory, lifespan, middleware | B1 |
| `backend/costguard/` | `apps/api/overcall/` | `git mv` and rename the package | B1 |
| `costguard/db.py` (Mongo-style adapter over Supabase REST) | deleted | Replaced by SQLModel repositories | B1 |
| `costguard/models.py` (Mongo-style documents) | `db/models.py`, `api/schemas.py` | Remove `ground_truth` from the log model. Add the new columns | B1 |
| `costguard/pricing_config.py`, `pricing/*.json` | `pricing/` | Version the files, add the loader, add `cost_basis` | B2 |
| `costguard/synthetic.py` | `synthetic/` | Rewrite so ground truth is a separate file and hard negatives exist | B3 |
| `costguard/rules/*.py`, `engine.py` | `detection/` | Keep the algorithms. Replace the global "dirty flag" with explicit runs. Replace-in-one-transaction. Add `impact_kind` | B4, B5 |
| `costguard/api.py`, `settings_store.py` | `api/routers/*`, settings repo | Rebuild on the contract with auth | B6 |
| `costguard/mock_llm.py` | `mock_openai/` | Add streaming and failure injection | B7 |
| `costguard/proxy.py`, `hashing.py` | `proxy/` | Remove the `x-costguard-*` and `sk_test_emergent` special cases and the synchronous log insert | B8, B9 |
| `render.yaml`, `vercel.json` | same names | Rewrite for the new layout | I3 |
| `memory/PRD.md`, `design_guidelines.json` | `docs/PRD.md` | Move the PRD. Fold the guidelines into tokens | F1 |
| `.emergent/`, `emergent.yml`, `test_reports/`, `test_result.md`, root `tests/` | deleted | Legacy generator artifacts | F1 |
| `hs_err_pid*.log`, `replay_pid*.log`, `frontend-start.log` | ignored | Add to `.gitignore` | F1 |
| `accept-a-payment/` (untracked clone) | `validation/samples/accept-a-payment/` (gitignored, SHA pinned in `samples.lock`) | Move out of the repo root | I2 |
| `supabase/migrations/.env` (gitignored by `*.env`) | `apps/api/.env` | Move. Do not read or commit it | B1 |

### 2.3 Environment files

All real `.env` files are gitignored. Only `.env.example` files are committed. A secret scan (gitleaks) runs in a pre-commit hook and in CI.

| File | Holds | Committed |
|---|---|---|
| `apps/web/.env.example` | Public Vite values only. Everything prefixed `VITE_` is shipped to the browser, so never put secrets here | yes |
| `apps/api/.env.example` | Placeholders for server secrets | yes |
| `apps/web/.env.local`, `apps/api/.env` | Real values | **no** |
| Vercel project settings | The `VITE_*` values | n/a |
| Render service settings | The API values | n/a |
| GitHub Actions secrets | `API_URL`, `INTERNAL_TOKEN` (keep-alive) | n/a |

Full variable tables are in §5.6.

### 2.4 Repository conventions

- Branches: `feat/<module>-<slug>` (for example `feat/f1-landing`). One module per PR, squash merged. Tag `module/<id>-done` on completion.
- Commits: Conventional Commits (`feat(web):`, `fix(api):`, `docs:`, `chore:`).
- CI (`ci.yml`): web (typecheck, eslint, vitest, build, design-rules check), api (ruff, pytest with a Postgres service container), contract check (§3.5), gitleaks.
- Python: 3.11+, `ruff` for lint and format, `pytest`, `pytest-asyncio`. Web: Node 20+, `npm`.
- Every module PR must include its tests and tick its own done-when list in the PR description.

### 2.5 Findings from the repo check (things you should know now)

1. **`supabase/migrations/20261021140000_initial.sql` is 140 bytes and contains environment-variable placeholder text, not SQL.** It is untracked, so git cannot restore it. Your dev database may still hold tables from when the original SQL was run, but I cannot confirm that. B1 replaces it with real migrations and its first task is to reset the dev schema (there is no real data to lose).
2. `supabase/migrations/.env` is a misplaced env file. It is gitignored, but it belongs in `apps/api/.env`.
3. The current frontend (React 19, react-router 7, Recharts 3) is modern enough that the Vite move is mostly build tooling, not a rewrite.
4. The backend requirements still pull `emergentintegrations`, which cannot be installed and is unused. It is removed in B1.
5. The existing `Logs.tsx` has real logic but is written as a single line of JSX with hard-coded demo rows as an error fallback. The fallback is removed in F6 so errors are never disguised as data.
6. **The current proxy has no authentication at all** (`/api/proxy/*` is open), and it lets any caller pick the real OpenAI upstream per request through an `x-costguard-upstream` header, which bypasses the "real upstream off by default" rule. It also special-cases an `sk_test_emergent` Stripe key. All three are removed in B8: ingest-key auth is mandatory, the upstream mode comes only from the user's saved setting plus the operator flag `ALLOW_REAL_UPSTREAM`, and the special case is deleted.
7. The current backend writes each log row synchronously inside the request. B8 moves this to the bounded async writer (§5.1).

---

## 3. The data contract

### 3.1 Conventions

- JSON, `snake_case`, UTC timestamps as ISO 8601 with `Z`, ids are UUIDs.
- Money is a JSON number in **USD**, rounded to 6 decimals on output. Stored as `numeric(14,8)`. Computed with `Decimal`.
- All `/v1/*` routes require `Authorization: Bearer <Supabase JWT>`, except `/healthz` and `/readyz`.
- All `/proxy/*` routes require `X-Overcall-Key` and nothing else from us. The `Authorization` header there belongs to the provider.
- Pagination is **keyset** (cursor), never offset. A cursor is opaque base64url of `{t, id}`.
- Enumerations: `provider` ∈ openai, stripe, aws. `severity` ∈ critical, warning, info. `tier` ∈ 1, 2, 3. `impact_kind` ∈ spend, reliability. `cost_basis` ∈ billed, estimated, modelled. `source` ∈ proxy, demo. `origin` ∈ upstream, overcall.
- `cost_basis` meaning: **billed** = tokens from the provider's own `usage` multiplied by the price table. **estimated** = tokens counted by tiktoken (streaming fallback) or an unknown model priced as the default model. **modelled** = a fixed per-request overhead (Stripe, failed requests). Only billed and estimated can count as real spend.

### 3.2 Database tables (Supabase Postgres)

Text columns with `CHECK` constraints are used instead of Postgres enums (enums are painful to alter). No table has a column for headers, bodies, prompts or response text. A test enforces a column allowlist.

```sql
-- 0001_init.sql (abridged but exact in shape)
create table public.user_settings (
  user_id        uuid primary key references auth.users(id) on delete cascade,
  currency       text not null default 'INR' check (currency in ('INR','USD')),
  usd_inr_rate   numeric(10,4) not null default 83.5 check (usd_inr_rate > 0),
  rules_enabled  jsonb not null default '{}'::jsonb,   -- {rule_id: bool}; missing = catalogue default
  tier3_enabled  boolean not null default false,
  thresholds     jsonb not null default '{}'::jsonb,   -- overrides only; missing = default
  upstream_mode  text not null default 'mock' check (upstream_mode in ('mock','real')),
  retention_days int  not null default 14 check (retention_days between 1 and 90),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create table public.ingest_keys (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  name           text not null check (char_length(name) between 1 and 60),
  prefix         text not null,                 -- 'oc_' + first 6 chars. Safe to display
  key_hash       text not null unique,          -- hex HMAC-SHA256(pepper, full key)
  pepper_version smallint not null default 1,
  created_at     timestamptz not null default now(),
  last_used_at   timestamptz,
  revoked_at     timestamptz
);
create index ingest_keys_user_active on public.ingest_keys (user_id) where revoked_at is null;

create table public.request_logs (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users(id) on delete cascade,
  ingest_key_id       uuid references public.ingest_keys(id) on delete set null,
  source              text not null check (source in ('proxy','demo')),
  origin              text not null default 'upstream' check (origin in ('upstream','overcall')),
  occurred_at         timestamptz not null,
  provider            text not null check (provider in ('openai','stripe','aws')),
  method              text not null,
  endpoint            text not null,            -- normalised template, e.g. /v1/customers/{id}
  status              int  not null,
  latency_ms          real not null,
  ttfb_ms             real,
  req_size            int  not null,            -- bytes
  resp_size           int  not null,
  req_hash            text not null,            -- 16 hex chars of sha256 over the canonical request
  model               text,
  prompt_tokens       int  not null default 0,
  completion_tokens   int  not null default 0,
  cached_prompt_tokens int not null default 0,
  tokens_estimated    boolean not null default false,
  stream              boolean not null default false,
  context_hash        text,                     -- hash of system/developer messages (>= 200 chars), never the text
  context_tokens      int,
  uses_tools          boolean not null default false,
  list_limit          int,                      -- Stripe ?limit=
  items_returned      int,
  has_idempotency_key boolean not null default false,
  caller              text check (char_length(caller) <= 64),
  cost_usd            numeric(14,8) not null default 0,
  cost_basis          text not null check (cost_basis in ('billed','estimated','modelled')),
  pricing_version     text,
  error_code          text
);
create index request_logs_user_time   on public.request_logs (user_id, occurred_at desc, id desc);
create index request_logs_dedupe      on public.request_logs (user_id, provider, method, req_hash, occurred_at);
create index request_logs_occurred_at on public.request_logs (occurred_at);   -- retention
create index request_logs_demo        on public.request_logs (user_id) where source = 'demo';

create table public.detection_runs (
  id                         uuid primary key default gen_random_uuid(),
  user_id                    uuid not null references auth.users(id) on delete cascade,
  status                     text not null check (status in ('running','succeeded','failed')),
  started_at                 timestamptz not null default now(),
  finished_at                timestamptz,
  is_demo_data               boolean not null,
  window_start               timestamptz, window_end timestamptz,
  window_days                numeric(8,3),
  projection_low_confidence  boolean not null default false,
  request_count              int not null default 0,
  flagged_request_count      int not null default 0,
  total_spend_usd            numeric(14,6) not null default 0,
  spend_savings_window_usd   numeric(14,6) not null default 0,
  spend_savings_monthly_usd  numeric(14,6) not null default 0,   -- headline (Tier 1+2, impact=spend)
  experimental_monthly_usd   numeric(14,6) not null default 0,   -- Tier 3, NEVER in the headline
  reliability_count          int not null default 0,             -- count of impact=reliability issues
  reliability_overhead_monthly_usd numeric(14,6) not null default 0, -- modelled, NEVER added to spend
  issue_counts               jsonb not null default '{}'::jsonb, -- {critical,warning,info}
  trend                      jsonb not null default '[]'::jsonb, -- [{date, spend_usd, waste_usd}]
  settings_snapshot          jsonb not null default '{}'::jsonb,
  pricing_versions           jsonb not null default '{}'::jsonb,
  rule_errors                jsonb not null default '[]'::jsonb,
  duration_ms                int
);
create index detection_runs_user on public.detection_runs (user_id, started_at desc);

create table public.issues (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null references auth.users(id) on delete cascade,
  run_id               uuid not null references public.detection_runs(id) on delete cascade,
  rule_id              text not null,
  tier                 int  not null check (tier in (1,2,3)),
  experimental         boolean not null,
  provider             text not null,
  endpoint             text not null,
  severity             text not null check (severity in ('critical','warning','info')),
  impact_kind          text not null check (impact_kind in ('spend','reliability')),
  title                text not null, summary text not null,
  explanation          text not null, suggested_fix text not null,
  affected_count       int  not null,
  window_savings_usd   numeric(14,6) not null default 0,
  projected_monthly_usd numeric(14,6) not null default 0,   -- meaning depends on impact_kind
  confidence           real,                                 -- null for Tier 1 and 2
  is_demo_data         boolean not null,
  detected_at          timestamptz not null default now()
);
create index issues_user on public.issues (user_id, severity, projected_monthly_usd desc);

create table public.issue_requests (            -- capped at 200 rows per issue
  issue_id    uuid not null references public.issues(id) on delete cascade,
  request_id  uuid not null references public.request_logs(id) on delete cascade,
  user_id     uuid not null,
  waste_usd   numeric(14,8) not null default 0,
  primary key (issue_id, request_id)
);
create index issue_requests_request on public.issue_requests (request_id);

-- 0002_rls_retention.sql
alter table public.user_settings   enable row level security;
alter table public.ingest_keys     enable row level security;
alter table public.request_logs    enable row level security;
alter table public.detection_runs  enable row level security;
alter table public.issues          enable row level security;
alter table public.issue_requests  enable row level security;
-- zero policies on purpose, plus:
revoke all on public.user_settings, public.ingest_keys, public.request_logs,
              public.detection_runs, public.issues, public.issue_requests from anon, authenticated;
-- public.purge_old_logs() and the pg_cron schedule are specified in §5.5
```

**Reruns replace issues in one transaction:** `begin; select pg_advisory_xact_lock(hashtext(user_id::text)); delete from issues where user_id = $1; insert detection_runs …; insert issues …; insert issue_requests …; commit;`. `issue_requests` cascades from `issues`. Transaction-level advisory locks are used because the Supabase pooler runs in transaction mode and session locks do not survive it.

### 3.3 REST API

Base path `/v1`. Auth is the Supabase JWT unless stated. Every error uses §3.4. All list responses have the shape `{ "items": [...], "next_cursor": "…" | null }`.

#### Public

| Method and path | Auth | Response |
|---|---|---|
| `GET /healthz` | none | `200 {"status":"ok","release":"…"}`. No DB access (used to wake Render) |
| `GET /readyz` | none | `200 {"status":"ok"}` after `select 1`. `503` with `error.code="not_ready"` otherwise (used by keep-alive) |
| `GET /internal/db-size`, `POST /internal/purge` | `Authorization: Bearer <INTERNAL_TOKEN>` | Operator-only (B11). Without the token they return `404`, so they are not discoverable. `db-size` returns `{"bytes":N,"limit_bytes":524288000,"percent":N}` |

#### Account and shell

`GET /v1/me` → the shell summary used by every page:
```json
{
  "id": "uuid", "email": "a@b.com", "created_at": "…",
  "proxy_status": "no_key | waiting_for_traffic | receiving_traffic | demo_only",
  "last_request_at": "… | null",
  "issue_count": 7,
  "is_demo_data": false,
  "has_data": true,
  "real_upstream_available": false
}
```

#### Overview

`GET /v1/overview`
```json
{
  "has_data": true, "is_demo_data": true, "generated_at": "…", "run_id": "uuid",
  "window": {"start": "…", "end": "…", "days": 7.0, "low_confidence_projection": false},
  "request_count": 12840, "flagged_request_count": 912, "total_spend_usd": 41.22,
  "spend_savings": {"window_usd": 6.1, "projected_monthly_usd": 26.14, "percent_of_spend": 14.8},
  "experimental_spend_savings": {"projected_monthly_usd": 4.2},
  "reliability_findings": {"count": 5, "modelled_overhead_monthly_usd": 0.9},
  "severity_breakdown": {"critical": 1, "warning": 3, "info": 3},
  "by_provider": [{"provider":"openai","spend_usd":40.1,"issue_count":4}, {"provider":"stripe","spend_usd":1.12,"issue_count":3}],
  "trend": [{"date":"2026-10-15","spend_usd":5.9,"waste_usd":0.8}],
  "top_issues": [ /* up to 5 IssueSummary, ordered by §3.3 impact order */ ]
}
```
`spend_savings` is the headline. `reliability_findings.modelled_overhead_monthly_usd` is shown only as a muted note and must never be added to the headline. When there is no data: `{"has_data": false, "is_demo_data": false}` plus zeros and empty arrays.

#### Issues

`GET /v1/issues?provider=&severity=&tier=&impact_kind=&include_experimental=false&limit=50&cursor=` → list of `Issue`. Tier 3 issues are returned only when the user's `tier3_enabled` is true **and** `include_experimental=true` (the server enforces both, so a client cannot bypass the setting). Default order: severity (critical first), then `projected_monthly_usd` descending, then id.

`GET /v1/issues/{id}` → `Issue`.

```json
{
  "id": "uuid", "rule_id": "duplicate_calls", "rule_name": "Duplicate calls",
  "tier": 1, "experimental": false, "provider": "openai", "endpoint": "/v1/chat/completions",
  "severity": "warning", "impact_kind": "spend",
  "title": "…", "summary": "…", "explanation": "…", "suggested_fix": "…",
  "affected_count": 42, "window_savings_usd": 1.2, "projected_monthly_usd": 5.1,
  "confidence": null, "is_demo_data": true, "detected_at": "…",
  "sample_requests": [
    {"request_id":"uuid","occurred_at":"…","req_hash":"a1b2c3d4e5f60718","req_size":1840,"resp_size":922,"status":200,"cost_usd":0.0031}
  ]
}
```
`sample_requests` contains up to 5 items and **only** these keys. There is no body field in the type.

#### Logs

`GET /v1/logs?q=&provider=&status_class=2xx|3xx|4xx|5xx&endpoint=&caller=&model=&issue_id=&from=&to=&limit=50&cursor=` → list of `LogEntry`, newest first. `q` matches endpoint, model, caller and a hash prefix (min 4 chars). `limit` max is 200.

```json
{
  "id":"uuid","occurred_at":"…","provider":"openai","method":"POST","endpoint":"/v1/chat/completions",
  "status":200,"latency_ms":812.4,"ttfb_ms":120.1,"req_size":1840,"resp_size":922,"req_hash":"a1b2c3d4e5f60718",
  "model":"gpt-4o-mini","prompt_tokens":410,"completion_tokens":96,"tokens_estimated":false,
  "stream":false,"cost_usd":0.0031,"cost_basis":"billed","pricing_version":"2026-01-15",
  "caller":"checkout-service","has_idempotency_key":false,"error_code":null,"origin":"upstream","is_demo":true,
  "flagged_by":[{"issue_id":"uuid","rule_id":"duplicate_calls","title":"…","severity":"warning"}]
}
```
`GET /v1/logs/{id}` → `LogEntry` (same shape, `flagged_by` populated). `GET /v1/logs/facets` → `{"providers":[…],"endpoints":[{"value":"/v1/…","count":12}],"callers":[…],"models":[…]}` (top 100 each).

#### Providers

`GET /v1/providers` → array of 3:
```json
{
  "id":"openai","name":"OpenAI","status":"waiting | receiving_traffic | demo_only | coming_soon",
  "proxy_base_url":"https://<host>/proxy/openai/v1",
  "snippets":[{"id":"curl","label":"curl","code":"…"},{"id":"python","label":"Python","code":"…"},{"id":"node","label":"Node","code":"…"}],
  "traffic":{"proxy":120,"demo":0,"last_request_at":"… | null"},
  "upstream_mode":"mock | real | test | null",
  "pricing":{"version":"2026-01-15","effective_from":"…","source_url":"…","rows":[{"label":"gpt-4o-mini input","usd_per_1m":0.15}]},
  "notes":"Stripe does not bill per call. Savings are a modelled overhead."
}
```
Snippets are generated on the server from `PUBLIC_PROXY_BASE_URL`, so they always match the real routes. They use the placeholder `YOUR_OVERCALL_KEY`, never a real key. AWS returns `status:"coming_soon"` and an empty snippet list.

#### Settings and detection

`GET /v1/settings` and `PUT /v1/settings` (full object, protected):
```json
{
  "currency":"INR","usd_inr_rate":83.5,
  "rules_enabled":{"duplicate_calls":true,"missing_cache":true,"retry_storm":true,"oversized_payload":true,"unbatched_calls":true,"token_bloat":true,"model_overuse":true},
  "tier3_enabled":false,
  "thresholds":{ /* every key in §3.6 */ },
  "upstream_mode":"mock",
  "confirm_real_upstream":false,
  "retention_days":14,
  "updated_at":"…"
}
```
Setting `upstream_mode:"real"` is rejected with `real_upstream_disabled` (403) unless the server env allows it, and with `confirmation_required` (400) unless `confirm_real_upstream` is true. A saved change triggers a detection rerun.

`GET /v1/rules` → catalogue (`contract/rules.json`).
`POST /v1/detection/run` → `202 {"run_id":"…","status":"running"}`. Small datasets finish inline and return `200` with the final status. `GET /v1/detection/runs/latest` → run summary.

#### Data management (all protected)

| Method and path | Body | Result |
|---|---|---|
| `POST /v1/demo/load` | `{"seed":42,"days":7}` | Replaces the user's demo logs (never real ones), reruns detection. `{"inserted":N}` |
| `DELETE /v1/demo` | none | Removes demo logs and demo issues. `204` |
| `DELETE /v1/data` | `{"confirm":"delete my data"}` | Removes **all** logs, issues and runs. `204`. Wrong confirmation gives `confirmation_required` |
| `POST /v1/settings/reset` | `{"confirm":true}` | Restores defaults. `200` settings |
| `GET /v1/accuracy` | none | Accuracy report (below) |

Accuracy report:
```json
{
  "datasets":[
    {"id":"synthetic","label":"Synthetic data (circular)","note":"Generated from the same rules, so high scores are expected and are not evidence of real accuracy.",
     "generated_at":"…","requests":5400,"rules":[{"rule_id":"duplicate_calls","tier":1,"positives":120,"flagged":118,"true_positives":116,"precision":0.983,"recall":0.967,"false_positives_on_hard_negatives":1}]},
    {"id":"real","label":"Real-traffic fixtures (hand-labelled)","note":"…","generated_at":"… | null","requests":640,"rules":[ /* same shape + wilson_low / wilson_high */ ]}
  ]
}
```
The two datasets are always reported separately. `real` may have `generated_at: null` and an empty `rules` list until I2 is done ("not measured yet").

#### Ingest keys (protected)

| Method and path | Result |
|---|---|
| `POST /v1/ingest-keys` `{"name":"checkout-service"}` | `201 {"id","name","prefix","key","created_at"}`. **`key` appears only in this response.** Max 5 active keys per user (`conflict` after that) |
| `GET /v1/ingest-keys` | `{"items":[{"id","name","prefix","created_at","last_used_at","revoked_at"}],"next_cursor":null}` |
| `DELETE /v1/ingest-keys/{id}` | `204`. Revokes. Idempotent |

#### Proxy (ingest-key auth, not JWT)

| Route | Behaviour |
|---|---|
| `ANY /proxy/openai/v1/{path}` | Forwards to the mock upstream (default) or `https://api.openai.com/v1/{path}` when real mode is on and allowed |
| `ANY /proxy/stripe/v1/{path}` | Forwards to `https://api.stripe.com/v1/{path}`. Test keys only |
| `ANY /proxy/aws/{path}` | `501 provider_not_supported` (after key auth) |
| any other `/proxy/*` | `404 route_not_supported` |

Required header: `X-Overcall-Key`. Optional: `X-Overcall-Caller` (max 64 chars, `[A-Za-z0-9._:/-]` only, anything else is dropped). The response carries `X-Overcall-Request-Id`. Errors generated by Overcall add `X-Overcall-Error: <code>` so a client can tell they did not come from the provider. Provider errors pass through untouched.

**Impact order** (used by Overview "top issues" and the default Issues order): severity, then `impact_kind = spend` before `reliability`, then `projected_monthly_usd` descending.

### 3.4 Error format

Every error from `/v1/*` and every Overcall-generated proxy error:
```json
{
  "error": {
    "code": "validation_error",
    "message": "Some settings are invalid.",
    "details": {"fields": [{"path": "thresholds.oversized_bytes", "message": "Must be between 10000 and 5000000."}]},
    "request_id": "req_01HXYZ…"
  }
}
```
This is deliberately close to OpenAI's `{error:{message,code}}` shape so provider SDKs parse proxy-originated errors gracefully. `details` is optional. `message` is plain language and never contains a secret, a body fragment or a stack trace.

| code | HTTP | When |
|---|---|---|
| `unauthenticated` | 401 | No Bearer token |
| `invalid_token` | 401 | JWT invalid, expired, wrong audience or wrong issuer |
| `forbidden` | 403 | Authenticated but not allowed |
| `not_found` | 404 | Unknown id, or an id that belongs to another user (never reveal which) |
| `validation_error` | 422 | Body, query or path invalid. `details.fields` lists each problem |
| `confirmation_required` | 400 | A destructive or risky action without its confirmation field |
| `real_upstream_disabled` | 403 | Real OpenAI mode requested but disabled by the operator |
| `conflict` | 409 | For example the 6th active ingest key |
| `invalid_cursor` | 400 | Malformed pagination cursor |
| `rate_limited` | 429 | Too many requests. Includes `Retry-After` |
| `ingest_key_missing` | 401 | Proxy call without `X-Overcall-Key` |
| `ingest_key_invalid` | 401 | Unknown key |
| `ingest_key_revoked` | 401 | Revoked key |
| `stripe_live_key_rejected` | 403 | Stripe credential is not an `sk_test_` or `rk_test_` key |
| `provider_not_supported` | 501 | AWS |
| `route_not_supported` | 404 | Proxy path outside the allow-list |
| `payload_too_large` | 413 | Proxy body over `MAX_REQUEST_BODY_BYTES` |
| `overloaded` | 503 | In-flight cap reached. Includes `Retry-After` |
| `upstream_unreachable` | 502 | Connection failure to the provider |
| `upstream_timeout` | 504 | Provider did not answer in time |
| `not_ready` | 503 | `/readyz` DB check failed |
| `internal_error` | 500 | Anything unexpected. Generic message only |

### 3.5 The `contract/` folder and drift checks

Both apps read these files. Neither imports the other's code.

| File | Written by | Used by |
|---|---|---|
| `openapi.yaml` | hand, from §3.3 (C0) | web: `openapi-typescript` generates `src/api/schema.d.ts`. api: drift test |
| `fixtures/*.json` | hand in C0. `synthetic/small` comes from B3 | web: MSW handlers and tests. api: response-shape tests |
| `errors.json`, `thresholds.json`, `rules.json` | hand | web: form validation and labels. api: validation and the catalogue |
| `fixtures/proxy/routes.json` | hand | web: snippet test. api: route test |

Checks that run in CI (`scripts/check-contract.sh`):

1. **Fixture validity (both sides):** every fixture validates against its schema in `openapi.yaml` (`ajv` in Vitest, `jsonschema` in pytest).
2. **Backend drift:** `scripts/check_contract.py` compares FastAPI's generated OpenAPI to `contract/openapi.yaml` for the set of (method, path, status code) and for every response component's property names, types and `required` list. Extra backend fields fail the check too.
3. **Types freshness:** regenerating `schema.d.ts` must produce no diff.
4. **Error codes:** every code raised anywhere in the backend exists in `errors.json`, and every code in the file is documented.

A contract change always goes in a PR that updates `contract/` first. Then the web and api sides adapt.

**C0 — contract bootstrap (size S).** Create `contract/` from §3. Author `openapi.yaml`, the fixtures listed above (demo and empty variants, plus one realistic `live` overview), `errors.json`, `thresholds.json`, `rules.json` and the check scripts. Done when both validators pass on every fixture.

### 3.6 Detection thresholds (defaults, min, max)

These are the same numbers the current code uses, plus `token_bloat_min_context_tokens` and `model_overuse_min_calls`, which were hard-coded. The server validates them and the Settings form uses the same ranges. Cross-field rule: `long_window_s > short_window_s`.

| Key | Default | Min | Max | Used by |
|---|---|---|---|---|
| `short_window_s` | 10 | 1 | 300 | duplicate_calls, missing_cache |
| `long_window_s` | 600 | 60 | 3600 | missing_cache |
| `retry_min_backoff_ms` | 1000 | 100 | 10000 | retry_storm |
| `retry_min_attempts` | 3 | 2 | 10 | retry_storm |
| `oversized_bytes` | 200000 | 10000 | 5000000 | oversized_payload |
| `unbatched_min_calls` | 5 | 2 | 100 | unbatched_calls |
| `unbatched_window_s` | 5 | 1 | 60 | unbatched_calls |
| `token_bloat_min_repeats` | 3 | 2 | 50 | token_bloat |
| `token_bloat_min_context_tokens` | 1024 | 256 | 32000 | token_bloat |
| `model_overuse_max_prompt_tokens` | 800 | 50 | 8000 | model_overuse |
| `model_overuse_max_completion_tokens` | 300 | 10 | 4000 | model_overuse |
| `model_overuse_min_calls` | 10 | 3 | 1000 | model_overuse |

---

## 4A. Frontend modules (F1–F8)

Common rules for every frontend module:

- Builds against MSW and `contract/fixtures` only. No real backend until I1.
- Fonts: Inter for UI text. JetBrains Mono (`.mono` utility: `font-mono tabular-nums`) for numbers, costs, hashes and endpoint paths. Both self-hosted via `@fontsource-variable/*` (no third-party font requests).
- Flat surfaces, hairline borders, no gradients, no stacked shadows. Severity colours (`critical`, `warning`) appear only on flagged issues.
- Sentence case, plain words, no unexplained jargon. Every empty state says what to do next.
- Visible focus ring on every interactive element. `prefers-reduced-motion` respected. Both themes designed with equal care.
- Tests: Vitest + React Testing Library + MSW (node). Playwright for the critical flow of the module. `axe` accessibility check on every new page.

### F1 — Landing page · size M

**Goal:** A public page that explains the product in ten seconds and sends people to sign up or try the demo. Creates the design tokens every later module reuses.
**Depends on:** nothing. The page makes no backend calls.
**Contract slice:** none.

**Design tokens** (CSS variables in `src/styles/tokens.css`, Tailwind maps to them):

| Token | Light | Dark |
|---|---|---|
| `--bg` | #FAFAF9 | #14161B |
| `--surface` | #FFFFFF | #1B1E24 |
| `--border` | #E5E5E3 | #2A2D34 |
| `--text` | #1B1D22 | #EDEDEC |
| `--muted` | #6B6F76 | #9A9DA6 |
| `--accent` | #35507A | #7C9CC4 |
| `--positive` | #2F7D5A | #5FB98A |
| `--warning` | #B8791A | #D9A64E |
| `--critical` | #B3392C | #E0685C |

Selected by `<html data-theme="light|dark">`. A tiny inline script in `index.html` sets it before first paint (no flash). Preference stored in `localStorage` key `overcall-theme` as `system | light | dark`, default `system`. Existing shadcn-style variable names (`--background`, `--card`, `--primary`) become aliases of these tokens so unmigrated components keep working until their own module.

**Files**
- Create: `apps/web/{package.json,vite.config.ts,tsconfig.json,tsconfig.node.json,index.html,tailwind.config.ts,postcss.config.js,eslint.config.js,vitest.config.ts,playwright.config.ts,lighthouserc.json,.env.example}`, `public/{favicon.svg,og.png,robots.txt}`, `src/{main.tsx,router.tsx}`, `src/styles/{tokens.css,globals.css}`, `src/lib/{theme.ts,cn.ts,env.ts}`, `src/components/ui/{Button,Card,Badge,Container,Accordion}.tsx`, `src/components/ThemeToggle.tsx`, `src/features/landing/{LandingPage,Nav,Hero,HowItWorks,DashboardPreview,WhatWeCatch,BetaNote,Faq,Footer}.tsx`, `src/features/landing/previewData.ts`, `src/features/landing/LandingPage.test.tsx`, `src/test/setup.ts`, `e2e/landing.spec.ts`, `scripts/check-design-rules.mjs`
- Move: `frontend/` → `apps/web/`
- Delete: `craco.config.js`, `plugins/`, `public/index.html` (replaced by root `index.html`), `build/`, Emergent overlay packages

**Tasks**
1. Create branch `feat/f1-landing`. Commit this plan.
2. `git mv frontend apps/web`; confirm it still installs and runs unchanged. Commit.
3. Convert CRA to Vite: add `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom`. Move `public/index.html` to `index.html` with `<script type="module" src="/src/main.tsx">`. Rename `src/index.tsx` to `main.tsx`. Replace `process.env.REACT_APP_*` with `import.meta.env.VITE_*` through `lib/env.ts`. Set `tsconfig` to `moduleResolution: "bundler"`, `types: ["vite/client"]`, alias `@/` to `src`. Remove `react-scripts`, `@craco/craco` and Emergent packages.
4. Add `.gitignore` entries for logs and crash dumps. Delete legacy artifacts (§2.2).
5. Write `tokens.css`, map Tailwind colours to the variables, override `boxShadow` to `none` (focus ring only), add `@fontsource-variable/inter` and `jetbrains-mono`.
6. Theme module: `theme.ts` (`getPreference`, `setPreference`, `applyTheme`, system listener) and the inline pre-paint script. `ThemeToggle` is an accessible three-state button group with `aria-pressed`.
7. UI primitives: Button (primary, secondary, ghost), Card (border only), Badge, Container, Accordion (native `<details>` or ARIA disclosure).
8. Router: `/` Landing only for now. Buttons link to `/signup` and `/app` (those routes can be stubs until F2 and F3).
9. Build sections in order: nav, hero, three-step explainer, static dashboard preview, "what it catches", free-during-beta note, FAQ, footer.
10. Copy (sentence case, plain words). Hero: "See where your API money goes". Support line: "Point your API base URL at Overcall. We log request metadata, spot wasteful patterns and show what fixing them would save." Buttons: "Try the demo" (`/app`) and "See how it works" (anchor `#how-it-works`). Steps: "Point your base URL at the proxy" → "We log and analyse" → "See where money is wasted". "What it catches": one plain sentence per rule, Tier 3 marked **Experimental**.
11. Static preview: a fixed fake dashboard (headline number, two figures, a small chart drawn with static SVG, three issue rows). Labelled "Example data".
12. FAQ (accordion): Do you store my prompts? (No: only hashes, sizes, token counts, status, latency and cost.) Do I give you my OpenAI or Stripe key? (No, it stays in your app.) Does it slow my app? (Do not state a number until B11 measures it. Say that we measure the overhead and publish it.) What about Stripe? (Test keys only.) How accurate are the savings? (Estimates, and why.)
13. Page title, meta description, canonical, Open Graph and Twitter tags (`og.png` 1200×630, absolute URL from `VITE_SITE_URL`). Skip link, landmarks, `lang`, focus-visible, reduced motion (no animated counters).
14. `scripts/check-design-rules.mjs`: fails if any source uses gradients, `shadow-*` classes other than `shadow-none`, or `critical`/`warning` colour classes outside issue components.
15. Tests, Lighthouse run, screenshots in both themes, PR.

**Tests**
- Unit: theme resolution (`system` follows `matchMedia`, stored choice wins, corrupted value falls back to `system`). Toggle persists.
- Component: every section renders. Both buttons have the correct `href`. FAQ expands with keyboard. Headings are in order (`h1` once).
- Playwright: load `/` with network capture and assert **no requests other than same-origin static assets**. Click "Try the demo" and the nav "Sign up" and assert the routes `/app` and `/signup`. Run `axe` in light and dark.
- Lighthouse CI: accessibility ≥ 90 (aim for 100), performance ≥ 90 on desktop.

**Edge cases:** `localStorage` blocked (private mode) so the toggle works for the session only. System theme changes while on `system`. 320 px wide and 200 % zoom. JavaScript disabled shows the readable content. Font loading uses `font-display: swap` with preloaded woff2. Dark-mode contrast of muted text (check ≥ 4.5:1). Very long words in the preview do not overflow. The OG image URL is absolute.

**Done when**
- [ ] Both themes look right at 320, 768 and 1280 px.
- [ ] The page makes **no backend calls** (Playwright assertion).
- [ ] Buttons route to `/signup` and `/app`.
- [ ] Lighthouse accessibility ≥ 90.
- [ ] `check-design-rules` passes. No gradients or shadows.
- [ ] Tokens file is the only place hex colours appear.
- [ ] `npm run build` passes and the old CRA files are gone.

### F2 — Auth pages (UI) · size M

**Goal:** Signup, login, forgot-password and reset screens that work against a fake client, with the real Supabase client behind the same interface.
**Depends on:** F1 tokens only. The real backend counterpart is B10.
**Contract slice:** none. (Supabase Auth is called by the Supabase JS SDK, not by our API. The API only sees the resulting JWT.)

**Interface**
```ts
interface AuthClient {
  signup(email: string, password: string): Promise<{ user: AuthUser; needsEmailConfirmation: boolean }>;
  login(email: string, password: string): Promise<AuthUser>;
  loginWithGoogle(): Promise<void>;
  logout(): Promise<void>;
  me(): Promise<AuthUser | null>;
  getAccessToken(): Promise<string | null>;
  requestPasswordReset(email: string): Promise<void>;
  updatePassword(newPassword: string): Promise<void>;
  continueAsDemo(): Promise<AuthUser>;            // client only, no account
  onAuthStateChange(cb: (u: AuthUser | null) => void): () => void;
}
```
Selection: `VITE_AUTH_MODE=mock | supabase` (default `mock` in dev and tests).

**Files**
- Create: `src/auth/{AuthClient.ts,MockAuthClient.ts,SupabaseAuthClient.ts,AuthProvider.tsx,ProtectedRoute.tsx,messages.ts,safeRedirect.ts}`, `src/features/auth/{AuthLayout,LoginPage,SignupPage,ForgotPage,ResetPage,CallbackPage,GoogleButton,PasswordField,schemas}.tsx|ts`, tests alongside.
- Modify: `router.tsx` (add `/login`, `/signup`, `/forgot`, `/reset`, `/auth/callback`, protect `/app/*`). Delete the merged `auth/authClient.ts` and `pages/AuthPage.tsx`.

**Tasks**
1. `AuthClient` interface and `AuthUser` type (id, email, isDemo).
2. `MockAuthClient`: fake session in `localStorage` (`overcall-mock-session`), small artificial delay, deterministic errors (`taken@example.com` is already registered, `wrong@example.com` fails login) for tests.
3. `SupabaseAuthClient`: wraps `@supabase/supabase-js` (`signUp`, `signInWithPassword`, `signInWithOAuth({provider:'google', redirectTo: origin + '/auth/callback'})`, `resetPasswordForEmail`, `updateUser`, `onAuthStateChange`). Maps `needsEmailConfirmation` from `data.session === null`.
4. `AuthProvider` exposes `user`, `status` (`loading | signedOut | signedIn`) and the client.
5. Zod schemas: email format, password ≥ 8 characters (matches Supabase's configured minimum), confirm equals password. `react-hook-form` with `zodResolver`.
6. Forms with show and hide password (button has `aria-label` and `aria-pressed`), inline errors tied with `aria-describedby`, submit disabled while pending.
7. `messages.ts`: map error codes (`invalid_credentials`, `user_already_exists`, `email_not_confirmed`, `weak_password`, `over_email_send_rate_limit`, network failure) to plain language that says what happened and what to do next. Example: "That email and password do not match. Check them and try again, or reset your password."
8. Signup when `needsEmailConfirmation` shows a "Check your email" screen instead of navigating (fixes the current behaviour).
9. `ProtectedRoute`: signed-out users go to `/login?next=<path>`. `safeRedirect` allows only same-origin relative paths starting with a single `/`.
10. "Continue as demo" on login and signup creates a client-side demo session (`isDemo: true`). In F3 the API layer uses MSW for demo sessions and makes no real backend calls.
11. Google button only renders in `supabase` mode.
12. `/auth/callback` finishes OAuth and email-confirmation redirects, then goes to `next` or `/app`. `/reset` lets the user set a new password after following the email link.

**Tests**
- Unit: schemas (valid, invalid email, short password, mismatch), `safeRedirect` (rejects `//evil.com`, `https://evil.com`, `/\evil`, `javascript:`), message mapping, `MockAuthClient` flows.
- Component: sign up then log in then log out. Wrong password message. Visiting `/app` signed out redirects to `/login?next=/app` and returns after login. Double submit sends one request.
- Playwright: full mock flow including the demo path.

**Edge cases:** email confirmation on and off. Two tabs: logging out in one signs out the other (`storage` event or Supabase listener). Session expires mid-use: a 401 from the API sends the user to `/login` with a "Your session ended" message. OAuth hash fragments. Password managers (`autocomplete` values). Trailing spaces and uppercase in email (trim and lowercase before sending). A user clicking Google while Supabase is unconfigured sees no button.

**Done when**
- [ ] You can sign up, log in, log out and `/app` redirects when signed out, all with the mock client.
- [ ] Open-redirect tests pass.
- [ ] Switching `VITE_AUTH_MODE=supabase` against your Supabase project works for email and Google (manual check).
- [ ] No auth code outside `src/auth` and `src/features/auth` talks to Supabase.

### F3 — App shell · size M

**Goal:** The frame every dashboard page lives in, plus the mock API layer all later modules use.
**Depends on:** C0 (contract fixtures) and F2 (auth provider).
**Contract slice:** `GET /v1/me` (shell summary), `GET /v1/providers`, `GET /v1/settings`, `POST /v1/demo/load`, error format §3.4.

**Files**
- Create: `src/api/{client.ts,errors.ts,keys.ts,hooks.ts,schema.d.ts}` (types generated), `src/mocks/{handlers.ts,state.ts,scenarios.ts,browser.ts,server.ts}`, `public/mockServiceWorker.js`, `src/lib/{format.ts,clipboard.ts}`, `src/components/layout/{Shell,Sidebar,Topbar,EmptyState,ErrorBoundary,PageSkeleton}.tsx`, `src/components/ui/{Skeleton,Dialog,Toast,Tabs}.tsx`, `src/context/{CurrencyProvider,SidebarProvider}.tsx`, route placeholders in `src/features/*/Page.tsx`.

**Tasks**
1. Add `openapi-typescript` script (`npm run gen:api`) that writes `schema.d.ts` from `contract/openapi.yaml`.
2. Typed fetch client: base URL from env, adds `Authorization` from `AuthClient.getAccessToken()`, parses the §3.4 error into an `ApiError` (`code`, `message`, `fields`, `requestId`, `status`). A 401 triggers sign-out.
3. TanStack Query setup: key factory, sensible `staleTime`, retry only on network errors and 5xx (never on 4xx).
4. MSW: handlers serve `contract/fixtures`. `state.ts` keeps in-memory settings, demo-loaded flag and ingest keys so changes persist across requests. `scenarios.ts` supports `empty`, `demo`, `live`, `error`, `slow` selected by `?scenario=` (dev only) or test setup. In the browser the worker starts before the first render. In prod it starts **only** for demo sessions, loaded lazily.
5. `Shell`: collapsible sidebar (icon and label) with Overview, Issues, Logs, Providers, Settings, an issue-count badge from `/v1/me`, collapse state saved. On narrow screens the sidebar becomes a drawer.
6. `Topbar`: proxy status pill (`no_key`, `waiting_for_traffic`, `receiving_traffic`, `demo_only`), INR/USD switch, theme toggle, "Load demo data" button, account menu with log out.
7. Currency: `useMoney()` returns a formatter. USD to INR happens here and nowhere else, using the rate from settings. INR uses `en-IN` grouping. Always shows a currency symbol.
8. `EmptyState`: copyable proxy URL, short setup snippets (tabs), one-click "Load demo data". Used whenever `has_data` is false.
9. Skeletons for each placeholder page. `ErrorBoundary` with a Retry button that resets the query error boundary.
10. Routes `/app`, `/app/issues`, `/app/logs`, `/app/providers`, `/app/settings`, each a placeholder inside the shell.

**Tests**
- Unit: `ApiError` mapping from every fixture in `fixtures/errors/`. Money formatter (INR grouping, tiny values, zero, rounding).
- Component: sidebar collapse and keyboard navigation, badge hides at 0 and shows `99+`, currency switch updates a rendered amount, empty state buttons, error boundary retry, skeleton to content.
- MSW: settings PUT then GET returns the new value. Demo load flips `is_demo_data`.
- Playwright: shell renders every route with mock data.

**Edge cases:** the MSW worker failing to register (show a clear dev error). Query retry storms (none on 4xx). Window resize while the drawer is open. Rate returned as 0 (guard divide-by-zero, show USD). Scenario switching while on a page. Demo session never calls a real URL (assert in a test by failing on any unhandled request).

**Done when**
- [ ] Every route renders a placeholder inside the shell and the mock data loads.
- [ ] Currency switch works everywhere through `useMoney()`.
- [ ] Unhandled requests fail the test run.
- [ ] `npm run gen:api` produces no diff on a clean checkout.

### F4 — Overview dashboard · size M

**Goal:** One screen that answers "how much could I save, and what should I fix first?"
**Depends on:** F3 shell conventions only (or a bare page with the same fixtures).
**Contract slice:** `GET /v1/overview` (§3.3). Fixtures `overview.demo.json`, `overview.empty.json`, `overview.live.json`.

**Files:** `src/features/overview/{OverviewPage,HeroSavings,FigureCards,TrendChart,TopIssues,SeverityBreakdown,DemoLabel,ProjectionNote}.tsx` and tests.

**Tasks**
1. Hero: projected monthly **spend savings** in large mono type, one plain line under it ("Based on the last 7 days of traffic. This is an estimate, not a bill.").
2. Two separate figure cards: **Estimated spend savings** (real money) and **Reliability findings** (a count, with its muted modelled-overhead note). They are visually distinct and nothing sums them. Tooltip explains why.
3. A persistent **Demo data** label whenever `is_demo_data` is true.
4. Trend line chart (Recharts): spend and estimated waste per day. Waste uses a dashed line so colour is not the only cue. Accessible name plus a visually hidden data table.
5. Top 3–5 issues (links into Issues with the issue open). Small severity breakdown (three bars with counts; colour only here because these are flagged issues).
6. If `window.low_confidence_projection`, show "Based on less than a day of traffic, so this projection may swing a lot."
7. If experimental results are enabled in settings, show a muted line "Up to ₹X more from experimental checks (not included)".
8. Empty state when `has_data` is false.

**Tests**
- Component: render from each fixture and assert the visible numbers match the fixture. A test asserts **no element shows the sum** of the two figures. Empty fixture shows the empty state. Demo fixture shows the label.
- Currency: INR values equal `usd × rate`.
- Playwright: screenshots in both themes (reviewed by eye). `axe`.

**Edge cases:** zero savings ("No waste found. Nice."). One trend point. Very large and very small values. NaN or null defences. Chart with all-zero waste. Locale grouping (lakh). Long endpoint names in top issues. Window shorter than a day.

**Done when**
- [ ] Page matches `overview.demo.json` in both themes.
- [ ] Empty state shows when there is no data.
- [ ] The two figures are separate and never added.
- [ ] Demo label always appears for demo data.

### F5 — Issues page · size M

**Goal:** Browse everything flagged and understand how to fix it.
**Depends on:** nothing beyond fixtures.
**Contract slice:** `GET /v1/issues` and `GET /v1/issues/{id}` (§3.3), `GET /v1/settings.tier3_enabled`.

**Files:** `src/features/issues/{IssuesPage,IssueFilters,IssueList,IssueRow,IssueDetail,SampleRequests,ExperimentalBadge,SeverityBadge}.tsx`, `useIssueFilters.ts` and tests.

**Tasks**
1. Flat list, not a dense grid: severity badge, title, provider, endpoint (mono), impact (savings or modelled overhead), affected count.
2. Filters for provider, severity and tier, combined with AND, synced to the URL (`?provider=openai&severity=warning`) so they can be shared.
3. Rows expand in place: **What we detected**, **Why it costs money**, **Suggested fix** (copy button), **Sample requests**.
4. Sample requests table shows hash, size, timestamp, status and cost only. The type has no body field.
5. Tier 3 issues show an **Experimental** badge and a confidence score ("Confidence 70%"). They are hidden unless the Tier 3 setting is on.
6. Impact label depends on `impact_kind`: "Estimated savings" for spend, "Modelled overhead (not billed by Stripe)" for reliability.
7. "View in logs" link to `/app/logs?issue=<id>`. Load more with the cursor.
8. Empty states: no issues at all, and "filters hide everything" with a Clear filters button.

**Tests:** filter combinations (provider × severity × tier, including Tier 3 gate on and off). Row toggles with Enter and Space and exposes `aria-expanded`. Sample-request allowlist test (renders only the five permitted keys, fails if extra keys appear in a fixture). URL sync. Reliability issues never show a "savings" label.

**Edge cases:** hundreds of issues (paginate). Very long endpoint path (wrap). Deep link `?open=<id>` expands that row. Filter value in the URL that no longer exists. Tier 3 turned off while a Tier 3 row is open. Confidence missing on Tier 3 (show "Confidence unknown").

**Done when**
- [ ] Filters combine correctly.
- [ ] A row expands and collapses with the keyboard.
- [ ] No request body is ever rendered.
- [ ] Tier 3 is hidden unless enabled and always badged when shown.

### F6 — Log Explorer · size M

**Goal:** See the raw traffic flowing through the proxy and find a specific request quickly.
**Depends on:** nothing beyond the logs fixtures.
**Contract slice:** `GET /v1/logs` (filters `q, provider, status_class, endpoint, caller, model, issue_id, from, to, cursor, limit`), `GET /v1/logs/{id}`, `GET /v1/logs/facets`.

**Files:** `src/features/logs/{LogsPage,LogFilters,LogTable,LogRow,LogDetailPanel,TimeRangePicker,useLogFilters}.tsx` and tests.

**Tasks**
1. Table columns: time, provider, endpoint, status, latency, size, tokens, cost, flagged-by. Numbers and paths in the mono font. Sticky header. Local time with UTC in the tooltip.
2. Search box (debounced 250 ms) plus filters: provider, status class, endpoint (from facets), time range presets (15 m, 1 h, 24 h, 7 d, 30 d) and custom.
3. Cursor pagination with a **Load more** button (`useInfiniteQuery`). A load error keeps the rows already shown.
4. Click or press Enter on a row to open a side panel (a dialog with a focus trap, Escape to close, focus returns to the row). It shows every metadata field and links to the issues that flagged it.
5. Modelled and estimated values: "~" prefix plus a tooltip ("Estimated tokens" or "Modelled cost").
6. URL-synced filters, including `?issue=<id>` coming from the Issues page.
7. Remove the hard-coded demo-row fallback from the old page: errors show an error state, never fake data.

**Tests:** filter and search build the right query string. Load more appends. The panel opens, traps focus, closes with Escape and restores focus. `flagged_by` links go to the right issue. Error keeps existing rows. Large list renders without freezing (virtualised above ~500 rows).

**Edge cases:** empty result. Search of fewer than 4 hash characters. Status 0 or odd codes. Missing `ttfb_ms`. Very long endpoint. Many callers or models in facets. Clock skew between `from` and `to`. Mobile horizontal scroll.

**Done when**
- [ ] You can find a specific request in a few seconds using search and filters (timed manually on the 5 000-row demo set).
- [ ] The panel shows all metadata and links to flagging issues.
- [ ] Keyboard and screen-reader pass (`axe`).

### F7 — Providers page · size S

**Goal:** Tell users how to connect each provider and manage their ingest keys.
**Depends on:** nothing beyond fixtures.
**Contract slice:** `GET /v1/providers`, `GET/POST /v1/ingest-keys`, `DELETE /v1/ingest-keys/{id}`, `fixtures/proxy/routes.json`.

**Files:** `src/features/providers/{ProvidersPage,ProviderCard,SnippetTabs,PricingTable,IngestKeyCard,CreateKeyDialog,KeyList}.tsx` and tests.

**Tasks**
1. One card per provider: OpenAI, Stripe, AWS. Each shows status, a copyable proxy URL, tabbed setup snippets, traffic count, and the pricing table version (expandable table).
2. AWS shows a calm **Coming soon** state in a neutral style, not an error.
3. Stripe card states "Test keys only" and explains that Stripe does not bill per call (modelled overhead).
4. Ingest key card: create (name) opens a dialog that shows the key **once** with a copy button and "I have saved it" confirmation. List shows name, prefix, created and last used. Revoke asks for confirmation.
5. Copy buttons give an accessible confirmation ("Copied").

**Tests:** every snippet's URL path matches `fixtures/proxy/routes.json`. Snippets contain the placeholder `YOUR_OVERCALL_KEY`, never a real key. The plaintext key is not in the DOM after the dialog closes and is not stored (state, storage or query cache). Copy works. Revoke needs confirmation. AWS has no error styling.

**Edge cases:** clipboard API unavailable (select-all fallback). Sixth key (conflict message). Revoked key still listed with a muted state. Long key names.

**Done when**
- [ ] Copy buttons work.
- [ ] Each snippet matches the real proxy routes (shared route fixture).
- [ ] The key is shown only once.

### F8 — Settings page · size M

**Goal:** Every control a user needs, nothing they do not.
**Depends on:** nothing beyond fixtures.
**Contract slice:** `GET/PUT /v1/settings`, `contract/thresholds.json`, `contract/rules.json`, `POST /v1/demo/load`, `DELETE /v1/demo`, `DELETE /v1/data`, `POST /v1/settings/reset`, `GET /v1/accuracy`, `/v1/me.real_upstream_available`.

**Files:** `src/features/settings/{SettingsPage,AppearanceSection,CurrencySection,DetectionSection,UpstreamSection,DataSection,AccuracySection,ConfirmDialog,settingsSchema}.tsx` and tests.

**Tasks**
1. Sections: **Appearance** (system, light, dark), **Currency** (INR/USD and the exchange rate with a "set by you" note), **Detection** (rule toggles by tier, thresholds, the Tier 3 gate with a clear experimental warning), **Upstream** (mock or real OpenAI), **Data** (load demo, clear demo, clear all, reset settings), **Accuracy**.
2. Form with `react-hook-form` and a zod schema generated from `thresholds.json` (min, max, integer rules and the `long_window_s > short_window_s` cross-field rule). Inline errors per field. Server `details.fields` errors map onto the same fields.
3. Selecting **real** upstream opens a warning dialog (requests go to OpenAI with your own key and cost real money) and requires an explicit checkbox before the setting can be saved. The option is disabled with an explanation when `real_upstream_available` is false.
4. Destructive actions use a confirm step. "Clear all data" requires typing `delete my data`.
5. Saving shows a toast, invalidates overview, issues and logs queries, and says "Re-analysing your data".
6. **Accuracy table** with two separate rows: Synthetic data (labelled circular) and Real-traffic fixtures (with sample size and 95 % interval). Per-rule detail expands. If the real dataset is not measured yet it says so.
7. Unsaved-changes warning when navigating away.

**Tests:** schema accepts defaults and rejects every out-of-range value. Cross-field rule. Server field error lands on the right input. Real-upstream dialog blocks saving without confirmation. Typed confirmation works. Changes persist through the MSW state. Accuracy shows two rows and never one blended number.

**Edge cases:** rate 0, negative, empty or huge. Threshold typed as text. Two rapid saves. A save failing mid-way (form keeps user input). Tier 3 toggled while its rules are off. Settings reset while the form is dirty.

**Done when**
- [ ] Changes persist through the mock handlers.
- [ ] Invalid values show inline errors.
- [ ] Real upstream needs confirmation. Destructive actions need a confirm step.
- [ ] The Accuracy table shows synthetic and real accuracy as two separate rows.

---

**Frontend status (F2–F8):** Dashboard, issue, log, provider and settings screens are rebuilt against the real local `/v1` API and were manually browser-checked. Login/signup/demo auth, password reset/callback routes, safe redirects, issue/log URL filters, sample metadata tables, settings validation/confirmation, responsive navigation, and ingest-key UI are implemented. Web typecheck, 20 unit tests, design-rule check and production build pass. Axe returned zero violations on the landing, login and app pages in both themes and at mobile width; confirmation dialogs were also checked. Known boundaries: key operations cannot work until the B10 backend routes exist; real Supabase auth needs credentials and has not been manually verified; no MSW fixtures or committed Playwright flow yet. See `docs/TRY_IT.md`.

## 4B. Backend modules (B1–B11)

Common rules for every backend module:

- Builds against pytest fixtures and the shared contract only. No frontend code.
- When handing a backend module back to me, include the design sections it cites (`§5.x`) as well as §3.4.
- Python 3.11+, async everywhere that touches I/O, Pydantic v2 for API schemas, SQLModel for tables. Tests run against a **real Postgres** (Docker), never SQLite, because JSONB, advisory locks and partial indexes matter.
- **Security rules apply to every module:** no bodies stored or logged; Authorization, `x-api-key`, Stripe keys, OpenAI keys, ingest keys and JWTs are never logged (including error logs and stack traces); Stripe live keys rejected; auth required before anything is public; real upstream off by default.
- Each module ends with `ruff` clean, tests green, `check-contract` green.

### B1 — Skeleton and DB · size M

**Goal:** A running FastAPI app with config, error format, logging with redaction wired in, the real schema, and a test harness. The old Mongo-style adapter is gone.
**Depends on:** the contract (§3.2 tables, §3.4 errors).
**Contract slice:** tables in §3.2. Error format §3.4. `GET /healthz`, `GET /readyz`.

**Files**
- Move: `backend/` → `apps/api/`; package `costguard` → `overcall`; `server.py` → `overcall/main.py`.
- Create: `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `.env.example`, `overcall/{config,errors,logging,deps}.py`, `overcall/db/{engine,models}.py`, `overcall/db/repos/base.py`, `supabase/config.toml`, `supabase/migrations/{0001_init,0002_rls_retention}.sql`, `docker-compose.dev.yml`, `tests/sql/00_auth_stub.sql`, `tests/{conftest.py,unit/test_health.py,unit/test_errors.py,integration/test_schema_parity.py,security/test_no_body_columns.py,unit/test_logging_redaction_basic.py}`, `scripts/export_openapi.py`, `.github/workflows/ci.yml`.
- Delete: `costguard/db.py`, `supabase` Python package, `motor`, `pymongo`, `emergentintegrations`, `backend/tests` legacy API tests (rewritten in B6).

**Tasks**
1. `git mv backend apps/api`; rename the package and fix imports; delete the adapter and legacy dependencies.
2. Dev database reset (dev Supabase project only, no data worth keeping): `drop table if exists request_logs, issues, settings, detection_runs cascade;` in the SQL editor, then apply the new migrations with `supabase db push`.
3. Write `0001_init.sql` and `0002_rls_retention.sql` exactly per §3.2. Local test DB: Docker Postgres 15 plus `00_auth_stub.sql` (creates `auth.users(id uuid primary key)` so foreign keys work).
4. `config.py` with `pydantic-settings`: every variable in §5.6, typed, validated, **fails fast in production if a required secret is missing**, and masks secrets in `repr`.
5. `db/engine.py`: `postgresql+asyncpg`, `statement_cache_size=0` (Supabase pooler in transaction mode does not support prepared statements), `pool_size=5`, `max_overflow=5`, `pool_pre_ping=True`, SSL required, disposed in the lifespan.
6. `db/models.py`: SQLModel tables with the same columns, types and nullability as the SQL. No `ground_truth` column.
7. `errors.py`: `OvercallError(code, status, message, details)`; handlers for `HTTPException`, `RequestValidationError` (to `validation_error` with `details.fields`) and unhandled exceptions (generic `internal_error`, request id, no stack trace in the body). Loads `contract/errors.json` and refuses unknown codes.
8. `logging.py`: JSON logs with a request-id context var and a **redaction filter installed from day one** (patterns in §5.7). The deeper redaction suite lands in B11.
9. `main.py`: app factory, lifespan, request-id middleware (`X-Overcall-Request-Id`), CORS only on `/v1/*`, `/healthz` (no DB) and `/readyz` (`select 1`).
10. `scripts/export_openapi.py` and the CI workflow (Postgres service, migrations, ruff, pytest).

**Tests**
- Health returns 200 without a DB. Readiness returns 503 with `not_ready` when the DB is down.
- Error format for 404, 422 (with `fields`), and an injected 500 (generic message, no traceback text).
- **Schema parity:** every SQL column exists in a SQLModel field with the same type and nullability, and vice versa.
- **Security:** `request_logs` columns are checked against an allowlist. Any column whose name matches `body|prompt|content|header|authorization|secret|key_plain` fails.
- Migrations apply on an empty DB and are re-runnable. RLS is enabled on all six tables and `anon` and `authenticated` have no privileges.
- Redaction basics: a log line containing `Bearer sk-FAKE…`, `sk_test_FAKE…` and `oc_FAKE…` comes out redacted.

**Edge cases:** the pooler transaction mode needs `statement_cache_size=0` (otherwise random "prepared statement does not exist" errors). Use the pooler host, not the direct IPv6 host. Windows event-loop policy for local dev. Startup without a DB still serves `/healthz`. Timestamps are always `timestamptz`.

**Done when**
- [x] `uvicorn overcall.main:app` starts. `/healthz` and `/readyz` work; without a database, readiness correctly returns 503.
- [x] Migrations apply to a local PostgreSQL 16 (verified 2026-10-22) and to the dev Supabase project (pushed by the owner; all six public tables present with RLS enabled, confirmed via `pg_tables`).
- [x] Schema parity passes against PostgreSQL migrations. Verified 2026-10-22 against an embedded PostgreSQL 16 (pgserver) with the auth stub; this also fixed a vacuous parity/RLS test that discovered zero tables.
- [x] The no-body-column test passes.
- [x] No Mongo, Motor, supabase-py or Emergent references remain; the legacy-reference check passes.

**Implementation status (2026-10-22): PARTIAL.** FastAPI startup and health/readiness behavior were smoke-tested. The unused Mongo-backed API, engine, proxy, settings store and mock-upstream prototype files were removed; B6-B8 will implement their planned SQL-backed replacements. Unit tests pass. The two PostgreSQL schema/RLS checks remain unverified locally, and the migration has not been applied to the development Supabase project.

### B2 — Pricing and cost engine · size S

**Goal:** Deterministic, versioned cost estimation with an honest `cost_basis`.
**Depends on:** nothing (pure functions plus JSON files).
**Contract slice:** `cost_basis` ∈ billed, estimated, modelled. `pricing_version` string. Pricing rows exposed by `GET /v1/providers`. `contract/pricing.schema.json`.

**Files:** `overcall/pricing/{__init__,loader,cost,models}.py`, `overcall/pricing/files/{openai,stripe,aws}/2026-01-15.json`, `contract/pricing.schema.json`, `scripts/check_pricing_age.py`, `tests/unit/pricing/*`.

**Pricing file shape** (OpenAI example; Stripe and AWS use the same envelope):
```json
{
  "provider": "openai", "version": "2026-01-15", "effective_from": "2026-01-15T00:00:00Z",
  "retrieved_at": "2026-01-15", "source_url": "https://openai.com/api/pricing/", "currency": "USD",
  "models": { "<model-id>": {"tier": "low|high", "input_per_1m": 0, "cached_input_per_1m": 0, "output_per_1m": 0} },
  "default_model": "<model-id>",
  "per_request_overhead_usd": 0, "failed_request_overhead_usd": 0,
  "chat_endpoints": ["/v1/chat/completions"],
  "deterministic_post_endpoints": ["/v1/embeddings"],
  "downgrade_map": {"<premium>": "<cheaper>"},
  "batch_equivalents": {"POST /v1/embeddings": {"method": "…", "discount": 0.0, "basis": "documented source for the saving", "fix": "…"}}
}
```
Numeric values are carried over from the current files and **re-verified against the provider pricing pages during this module**, then stamped with `retrieved_at`.

**Tasks**
1. `contract/pricing.schema.json` and a loader that validates every file at startup and fails fast.
2. `PricingBook.for_time(provider, at)` picks the latest version whose `effective_from <= at`. Older logs keep older prices.
3. `estimate_cost(provider, model, usage, status, at) -> CostResult(cost_usd, basis, pricing_version, fallback_used)` with `Decimal`.
4. Rules: successful OpenAI call with provider-reported usage is `billed`. Tokens from tiktoken, or an unknown model priced as the default, is `estimated`. Failed requests, endpoints without usage, and all Stripe calls are `modelled`. AWS returns 0 `modelled` with `supported: false`.
5. Cached prompt tokens: `(prompt − cached) × input + cached × cached_input + completion × output`.
6. Model resolution by **longest prefix** (so a dated `-mini` model never resolves to the non-mini model).
7. `scripts/check_pricing_age.py` warns when `retrieved_at` is older than 90 days (CI warning, not failure).

**Tests:** table-driven, reading numbers from the price files (so tests do not hard-code prices that could go stale). Version selection on both sides of `effective_from`. Prefix resolution (`gpt-4o-mini-<date>` must not match `gpt-4o`). Cached tokens. Decimal exactness. Every file validates against the schema. Unknown model sets `fallback_used` and `estimated`.

**Edge cases:** negative or huge token counts (clamp and log). `cached > prompt` (clamp). `model` null. Provider unknown (raise). Missing file (fail at startup). Currency other than USD (reject).

**Done when**
- [x] Cost is deterministic and every result carries a basis and a pricing version.
- [x] Old logs price with old versions.
- [x] Price files carry `retrieved_at` and pass the schema.

**Implementation status (2026-10-22): COMPLETE.** Pricing unit tests, schema validation, version selection, age check, and the full API test suite pass.

### B3 — Synthetic data generator · size M

**Goal:** A seedable generator that produces realistic traffic with injected waste, **hard negatives**, and a **separate** ground-truth file. It must be written before the rules, from the definitions in §5.3, so it does not secretly mirror the code.
**Depends on:** B2 (costs) and the log shape in §3.2.
**Contract slice:** `LogEntry` fields (§3.3) as the output rows. Ground truth file shape below. `fixtures/synthetic/small/*`.

**Files:** `overcall/synthetic/{generator,scenarios,truth,cli}.py`, `contract/fixtures/synthetic/small/{logs.json,ground_truth.json}`, `tests/unit/synthetic/*`.

**Ground truth shape** (separate from logs, never loaded into the database):
```json
{ "seed": 42, "generator_version": "1.0.0",
  "labels": [ {"request_id": "uuid", "rule_id": "duplicate_calls", "role": "positive", "pattern": "double_submit"},
              {"request_id": "uuid", "rule_id": "retry_storm", "role": "hard_negative", "pattern": "exponential_backoff"} ] }
```
A request can carry labels for several rules. Logs contain no `ground_truth`, `rule` or `label` keys.

**Tasks**
1. `generate(seed, days, size, start) -> (list[LogRow], GroundTruth)` using `random.Random(seed)` and an injected start time. Ids are `uuid5(namespace, f"{seed}:{index}")`, so output is byte-identical for the same inputs.
2. Baseline traffic: diurnal volume, endpoint mix per provider, model mix, log-normal latency, realistic token and size distributions. At least 95 % of rows are clean.
3. Positive injectors, one per rule, each with named patterns (for example `double_submit`, `page_refresh_storm`, `polling_without_cache`, `no_backoff_retries`, `giant_document_prompt`, `loop_of_single_embeddings`, `repeated_system_prompt`, `premium_model_for_tiny_task`). Boundary positives just inside the threshold (for example a duplicate at 9.9 s).
4. Hard negatives per rule: identical payload at 10.5 s; different payloads in rapid succession; identical call after a *failed* call; retries with exponential backoff (1 s, 2 s, 4 s); only two attempts; identical GET after more than the long window; non-deterministic POST repeated (chat completion); a payload exactly at the threshold; four calls in a burst; five calls with 6 s gaps; repeated context below the token minimum; a premium model with a long prompt; a premium model using tools; Stripe retries that carry an Idempotency-Key.
5. CLI: `python -m overcall.synthetic --seed 42 --days 7 --size small|standard --out <dir>`. `small` (~300 requests) is committed under `contract/fixtures/synthetic/small/`. `standard` (about 5 000 to 10 000 requests over 7 days) is generated in CI and for evaluation.
6. `[Deferred to B6]` `POST /v1/demo/load` will use the generator without ground truth and mark rows `source='demo'`; that API endpoint is not part of B1-B4.
7. **Freeze rule:** tag `b3-frozen` before B4 starts. Later generator changes need a changelog line with a reason. Never edit the generator to make a rule pass.
8. Adversarial review (5 minutes with me): list five waste patterns the rules would plausibly miss, add them as positives so recall is not circular.

**Tests:** same seed gives identical bytes and different seeds differ. Every pattern appears at least N times. Every rule has hard negatives. Every label id exists in logs. No label leakage in `logs.json`. Sorted timestamps and unique ids. Costs agree with B2. Generation time under 3 s for `standard`.

**Edge cases:** seed 0, `days=1`, `days=30` (cap volume). Overlapping patterns on one request. Time zone is UTC only.

**Done when**
- [x] Deterministic output and a separate ground-truth file.
- [x] Hard negatives exist for all seven rules.
- [x] `small` fixture is committed and validates against the contract schema.
- [ ] The `b3-frozen` tag exists before any rule code is written. The tag exists and predates the new B4 `detection/` package, but the published root commit already contains legacy prototype rule files, so the strict historical ordering cannot be established from this repository history.

**Implementation status (2026-10-22): PARTIAL.** Generator determinism, synthetic schema/fixture, CLI output, and the standard-size performance test pass. The B3 freeze rule was followed for B4 rule implementation; subsequent, user-approved truth-set additions are recorded in the changelog. The strict historical ordering cannot be proven from the published root commit.

**Adversarial review (user approved, added in generator v1.1.0):**
1. `semantic_duplicate_nonsemantic_metadata` (`duplicate_calls`): same intent, different request hashes.
2. `duplicate_after_configured_window` (`missing_cache`): identical embedding after the configured long cache window.
3. `overlapping_poll_different_cursor` (`missing_cache`): overlapping Stripe pages with different request hashes.
4. `retry_chain_beyond_fast_threshold` (`retry_storm`): repeated failures with gaps beyond the fast-retry threshold.
5. `premium_model_above_tiny_task_threshold` (`model_overuse`): premium-model usage just outside the “tiny task” limits.

These accepted positives are deliberately not forced into the current rule thresholds. B4 evaluation now reports the resulting misses instead of presenting circular 100% recall. The regression baseline is versioned to the revised labels.

### B4 — Detection core and Tier 1 rules · size M

**Goal:** The `Rule` interface, the runner (replace issues in one transaction), savings maths, and the three deterministic rules.
**Depends on:** B1 (DB), B2 (costs), B3 (fixtures).
**Contract slice:** `Issue` shape (§3.3), `detection_runs` and `issues` tables, thresholds (§3.6). Design: §5.3.

**Files:** `overcall/detection/{base,registry,thresholds,runner,savings}.py`, `overcall/detection/rules/{duplicate_calls,missing_cache,retry_storm}.py`, `overcall/db/repos/{logs,runs,issues}.py`, `scripts/evaluate.py`, `tests/unit/detection/*`, `tests/integration/test_runner.py`.

**Core types**
```python
@dataclass(slots=True) class LogRow: ...                     # the columns the rules need, no bodies exist
@dataclass class Finding: rule_id, severity, provider, endpoint, title, summary, explanation,
                          suggested_fix, affected: list[LogRow], waste_by_request: dict[UUID, Decimal],
                          confidence: float | None = None
class Rule(Protocol):
    id: str; name: str; tier: Literal[1,2,3]; description: str; default_enabled: bool
    threshold_keys: tuple[str, ...]
    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]: ...
```
`RuleContext(thresholds, window_days, now)`.

**Tasks**
1. `base.py`, `registry.py` (rules register by id, catalogue matches `contract/rules.json`), `thresholds.py` (defaults, bounds from `contract/thresholds.json`, cross-field validation).
2. `savings.py`: `monthly = window × 30 / max(window_days, 1)`; `split_by_impact(finding)` (a finding whose flagged rows mix cost bases is split into a spend finding and a reliability finding); severity by monthly impact (≥ $20 critical, ≥ $2 warning, else info, with per-rule overrides in §5.3); money-risk override to critical for Stripe payment writes without an Idempotency-Key.
3. Port the three rules from the existing code onto `LogRow`, ignoring `origin='overcall'` rows and `provider='aws'`. Deterministic ordering by `(occurred_at, id)`. Boundaries documented and tested (`<=` for windows).
4. `runner.run(user_id)`: advisory lock → load settings and last-30-day logs (cap 200 000) → run enabled rules (Tier 3 only if enabled), each in its own try block (a failing rule goes into `rule_errors`, others continue) → merge waste by **max per request** across Tier 1 and 2 → build the run summary and trend → in one transaction delete old issues, insert run, issues, issue_requests (cap 200 per issue) → commit.
5. Headline rule: `spend_savings_monthly_usd` sums only impact `spend` from Tier 1 and 2. Tier 3 goes to `experimental_monthly_usd`. Reliability goes to `reliability_count` and overhead and is never added to spend.
6. `scripts/evaluate.py`: runs the engine on a generated dataset and compares flagged request ids to ground truth, per rule: positives, flagged, true positives, precision, recall, and false positives on hard negatives. Writes `validation/reports/synthetic.json`.

**Tests**
- Unit per rule with hand-built rows: below, at and above each boundary (9.99, 10.00, 10.01 s), each hard-negative pattern, Stripe money-risk severity.
- Runner integration: rollback test (raise after the delete and prove old issues survive), two concurrent runs serialise, a throwing rule is isolated, idempotence (two runs give equal issues apart from ids), double-counting (one request flagged by two rules counts once), empty logs, one log, all-failed logs.
- Evaluate on the `small` fixture. Gate on *regression* against `validation/baseline.json`, not on 100 %.

**Edge cases:** identical timestamps. Very large groups (performance budget: 100 000 rows under 2 s). `window_days < 1` sets `projection_low_confidence`. Rows with `status` 0. A rule raising mid-way. Settings that disable every rule.

**Done when**
- [x] A rerun replaces issues atomically and never leaves a half state. Verified 2026-10-22 against embedded PostgreSQL 16; this exposed and fixed a bug where Decimal values in the run's JSONB `trend` could not be serialised.
- [x] Tier 1 rules pass their unit and hard-negative tests.
- [x] Evaluate reports precision and recall per rule on synthetic data.
- [ ] Spend and reliability totals are kept apart in persisted storage. Unit-level separation passes; database persistence is not yet exercised locally.

**Implementation status (2026-10-22): PARTIAL.** Tier 1 code, savings separation, rule contracts, baseline-gated fixture evaluation, and runner integration tests are present. Against the user-reviewed v1.1.0 labels, the small fixture reports precision/recall of 1.00/0.80 for `duplicate_calls`, 1.00/0.75 for `missing_cache`, and 1.00/0.50 for `retry_storm`, with no hard-negative false positives. These synthetic scores are not evidence of real-traffic accuracy. Rollback, serialization, rule isolation, idempotence, empty/single-log, and all-rules-failed scenarios are covered by PostgreSQL integration tests, but those tests remain unverified locally because Docker/PostgreSQL is unavailable. CI now includes the B4 implementation in linting and provisions PostgreSQL for integration tests.

### B5 — Tier 2 and Tier 3 rules · size M

**Goal:** The two threshold rules and the two experimental rules, each behind the `Rule` interface.
**Depends on:** B4.
**Contract slice:** thresholds §3.6, `confidence`, `experimental`. Design: §5.3.

**Files:** `overcall/detection/rules/{oversized_payload,unbatched_calls,token_bloat,model_overuse}.py`, tests, and the evaluate script now reports by tier.

**Tasks**
1. `oversized_payload` (Tier 2): `max(req_size, resp_size) > oversized_bytes`. Waste is `cost × (size − limit) / size`.
2. `unbatched_calls` (Tier 2): endpoints with a documented batch equivalent (from the pricing file). Bursts of at least `unbatched_min_calls` calls with gaps ≤ `unbatched_window_s` per (provider, method, endpoint, caller). Waste is `cost × discount` for every call after the first.
3. `token_bloat` (Tier 3): OpenAI chat calls, 2xx, with a `context_hash` and `context_tokens ≥ token_bloat_min_context_tokens`. Contexts repeated at least `token_bloat_min_repeats` times. Waste per repeat is `context_tokens × (input − cached_input) / 1e6` (improves on the old version, which used the whole prompt). Confidence `min(0.85, 0.45 + 0.05 × average_repeats)`.
4. `model_overuse` (Tier 3): premium-tier model in the downgrade map, prompt ≤ `model_overuse_max_prompt_tokens`, completion ≤ `model_overuse_max_completion_tokens`, **`uses_tools` false**, at least `model_overuse_min_calls` calls per model. Waste is the cost difference at identical token counts. Confidence 0.7 if the average completion is under 60 tokens, else 0.55.
5. Tier 3 only runs when `tier3_enabled`. All Tier 3 issues carry `experimental: true` and a confidence.
6. **Savings honesty check for `unbatched_calls`:** for every entry in `batch_equivalents`, record the documented basis for a saving in the pricing file (a published batch discount, or fewer billed requests). Embedding batching, for example, does not change per-token cost. Where no real price saving exists, the finding is classified as **reliability** with a modelled overhead, never as spend. A unit test fails if an entry has no `basis` field.

**Tests:** boundary and hard-negative tests per rule (payload exactly at the threshold is not flagged, four-call bursts, repeated context below the minimum, premium model with a long prompt, premium model with tools). Confidence formulas. Tier 3 off means no Tier 3 issues and no `experimental_monthly_usd`. Evaluate by tier.

**Edge cases:** missing pricing entry for a model (skip with a note, never crash). `caller` null grouped as "unknown". Context hash collisions (documented, extremely unlikely). Savings above the call's own cost (clamped).

**Done when**
- [x] All seven rules run behind one interface and respect thresholds from settings.
- [x] Tier 3 is gated (off by default, runner skips it unless `tier3_enabled`) and always carries a confidence.
- [x] Evaluate reports synthetic precision and recall per rule.

**Implementation status (2026-10-22): COMPLETE for code and unit/evaluation checks.** `oversized_payload`, `unbatched_calls`, `token_bloat` and `model_overuse` are registered and in `contract/rules.json`. Synthetic v1.1.0 results: `oversized_payload` 1.00/1.00, `unbatched_calls` 1.00/1.00, `token_bloat` 1.00/1.00, `model_overuse` precision 1.00 / recall 0.50 (the accepted adversarial 900-token-prompt positives are deliberately missed). No hard-negative false positives. These scores are synthetic and are not evidence of real-traffic accuracy. Evaluation now regenerates full rows from the committed seed because the public fixture omits internal fields (context hash, tool use) that Tier 3 needs, and fails if the committed ground truth no longer matches the generator. Stripe batching savings are classified as reliability, never spend, via `split_by_impact`. Tier 3 runner behaviour against PostgreSQL is covered only by the existing, locally skipped integration tests.

### B6 — REST API · size M

**Goal:** Every `/v1` endpoint from §3.3 (except ingest keys, which are B10), built on the repositories.
**Depends on:** B1, B4 (and B5 for the full catalogue). Auth is an injected dependency here.
**Contract slice:** all of §3.3 except `/v1/ingest-keys`, plus §3.4.

**Files:** `overcall/api/{schemas,pagination,snippets}.py`, `overcall/api/routers/{health,me,overview,issues,logs,providers,settings,detection,demo,data,accuracy,rules}.py`, `overcall/db/repos/{settings}.py`, `scripts/check_contract.py`, `tests/contract/*`, `tests/integration/api/*`.

**Tasks**
1. `deps.current_user` is an interface that returns a `UserContext(user_id, email)`. **B6 does not decode JWTs.** Tests override it. Local dev between B6 and B10 uses a dev-only script that overrides it. There is no test header or backdoor inside the app.
2. Pydantic v2 response models that match the OpenAPI schemas exactly (`extra="forbid"` on responses).
3. Keyset pagination helper (`(occurred_at, id)` cursor, tamper-safe, `invalid_cursor`).
4. Implement every endpoint. Overview reads the latest run row. Issues enforces the Tier 3 gate server-side. Logs builds a parameterised query (no string concatenation). Providers builds snippets from `PUBLIC_PROXY_BASE_URL` and `contract/fixtures/proxy/routes.json`. Settings validates thresholds with fields and enforces the real-upstream rules. Demo and data endpoints operate by `source` and `user_id`.
5. Detection run endpoint: inline for up to 20 000 rows, otherwise a background task returning 202.
6. A route-table walk test that asserts every non-public `/v1` route requires auth (fails closed when B10 plugs in the real dependency).
7. `scripts/check_contract.py` (drift check from §3.5) wired into CI.

**Tests:** every endpoint validates against `contract/openapi.yaml` and fixtures. **Two-user isolation** on every id-taking endpoint (user B asking for user A's id gets `not_found`). Pagination stability while rows are inserted. Filter combinations. Tier 3 gate. Settings errors with `details.fields`. Real-upstream gating and `confirmation_required`. Demo load never touches live rows and is idempotent. `DELETE /v1/data` requires the exact confirmation. SQL-injection strings in `q`, `endpoint` and `caller` are inert. Snippets match `routes.json`.

**Edge cases:** cursor tampering. `limit` bounds. `from > to`. Very long `q`. Concurrent demo loads. Deleting data while a detection run is in progress (advisory lock). A user with no settings row (created on first read).

**Done when**
- [x] The backend drift check passes (`scripts/check_contract.py`, wired into CI). **Deviation:** `contract/openapi.yaml` was generated from the FastAPI schema with `--write` rather than hand-authored first, so it detects future drift but is not an independent spec. It does not yet check error codes.
- [x] Isolation and gating tests pass (`tests/integration/test_api_endpoints.py`, 128 passed locally against PostgreSQL 16, 0 skipped).
- [ ] Every response shape equals the corresponding fixture shape. **Not done:** no per-endpoint response fixtures exist; shapes are enforced by `extra="forbid"` response models and the drift check only.

**Implementation status (2026-10-22): implemented and tested, with gaps.** All §3.3 endpoints except `/v1/ingest-keys` (B10) exist. `current_user` fails closed with 401 until B10; tests override it. Route-table walk confirms every `/v1` route returns 401 by default. Tested: two-user isolation on logs and issues, cursor pagination (logs and issues), filters, SQL-injection strings in `q` and `endpoint`, `limit`/`from>to`/long `q`/bad cursor, settings validation with `details.fields`, real-upstream gating, `reset` and `DELETE /v1/data` confirmations, demo load idempotency without touching proxy rows, providers status and snippets. **Not tested:** pagination while rows are inserted, concurrent demo loads, delete during a running detection, the Tier 3 visibility gate on issues, the 202 background detection path, `/v1/accuracy`, and the Stripe Node snippet (unverified until I2). `PUT /v1/settings` accepts but ignores `updated_at`. `/v1/accuracy` reads `validation/reports/synthetic.json`; real-traffic accuracy is reported as not measured.

### B7 — Mock OpenAI upstream · size S

**Goal:** A deterministic fake OpenAI that is safe, fast, supports streaming and can simulate failures.
**Depends on:** nothing.
**Contract slice:** the OpenAI response shapes it imitates (chat completion, embeddings, models, error, SSE chunks). No Overcall contract.

**Files:** `overcall/mock_openai/{app,tokens}.py`, `tests/unit/mock_openai/*`.

**Tasks**
1. Endpoints: `POST /v1/chat/completions` (non-stream and stream), `POST /v1/embeddings`, `GET /v1/models`.
2. Deterministic content seeded from the request hash. `id` and `created` vary per call, like the real service.
3. Usage computed with tiktoken (fallback `len/4`). Streaming sends a role chunk, content deltas, a finish chunk, then **a usage chunk only when `stream_options.include_usage` is true**, then `data: [DONE]`.
4. Failure injection by request headers: `X-Mock-Status` (429, 500, 503), `X-Mock-Latency-Ms`, `X-Mock-Retry-After`, `X-Mock-Drop-After-Chunks` (cut the stream), `X-Mock-Resp-Bytes` (pad the response to test oversize).
5. OpenAI-shaped errors for bad input (missing `model` or `messages`).
6. Mounted **only** through `httpx.ASGITransport` by the proxy. It is not a public route.

**Tests:** response shapes against hand-written reference examples. Streaming format and usage-chunk behaviour. Each failure injection. Determinism. The mock never echoes request headers.

**Edge cases:** `n > 1`, unicode, empty `messages`, very long input, `stream: true` with `n > 1`.

**Done when**
- [x] The proxy can talk to it in-process with no network (`create_mock_client()` wires `httpx.ASGITransport`; no socket is opened).
- [x] Streaming, errors and latency injection work.
- [x] It is unreachable from outside the process (not included in the main app; docs and OpenAPI disabled; tested).

**Implementation status (2026-10-22): COMPLETE, 48 tests, full suite 176 passed.** Files: `overcall/mock_openai/{app,tokens}.py`, `tests/unit/mock_openai/test_mock_openai.py`. Covered: response shapes, determinism with varying `id`/`created`, usage maths, streaming format, usage chunk only with `include_usage`, `n > 1` (stream and non-stream), unicode, 1 MB input, all failure headers (including invalid values rejected with 400), embeddings (float, base64, token arrays, dimensions), bad-input errors, and that headers, secrets and prompt text are never echoed.

**Deviations and known limits**
- **No tiktoken.** It downloads encoding files over the network on first use, which breaks the offline in-process requirement. Tokens are estimated as `ceil(chars / 4)`, so usage numbers are an estimate, not what OpenAI would bill.
- **`httpx.ASGITransport` buffers the whole response** (verified: headers and all chunks arrive together once the app finishes). Through it the proxy cannot observe real time-to-first-byte or incremental streaming. **B8 must decide** between a small custom streaming ASGI transport or accepting that mock-mode `ttfb_ms` is not meaningful. `X-Mock-Latency-Ms` delays the whole response, not individual chunks.
- `X-Mock-Resp-Bytes` pads the first choice's content with `x` (at least N bytes for non-stream, approximate for streams); padded text counts toward `completion_tokens`.
- `X-Mock-Drop-After-Chunks` ends the stream cleanly without `[DONE]` rather than resetting the connection.
- Invalid `X-Mock-*` header values return 400 instead of being ignored.

### B8 — Proxy core · size L

**Goal:** Forward requests unchanged, log metadata only, never block on logging, and fail closed on authentication. Design: §5.1 (read it first).
**Depends on:** B1, B2, B7. Key verification is built here as pure functions (B10 adds management and JWT).
**Contract slice:** the proxy table in §3.3 (routes, `X-Overcall-Key`, `X-Overcall-Caller`, `X-Overcall-Request-Id`, `X-Overcall-Error`), the error codes for the proxy, `request_logs` columns.

**Files:** `overcall/proxy/{router,forward,headers,hashing,extract,writer,ratelimit,ingest_auth,errors}.py`, `overcall/auth/ingest_keys.py` (generate, hash, verify), `overcall/db/repos/settings.py` (a small read helper `get_upstream_mode(user_id)`, which B6 later extends), `tests/unit/proxy/*`, `tests/integration/proxy/*`, `tests/security/test_proxy_*.py`. Tests create ingest-key rows directly with a test pepper (the management endpoints arrive in B10).

**Tasks** (order matters)
1. `hashing.py`: port the existing canonical hashing and endpoint normaliser with golden test vectors (§5.1).
2. `headers.py`: the forward and drop policy using the **raw header list** (multi-value headers preserved), hop-by-hop removal, `Accept-Encoding: identity`.
3. `auth/ingest_keys.py`: `generate_key`, `hash_key` (HMAC-SHA256 with a pepper), `verify`. `ingest_auth.py`: lookup by hash with a TTL cache (60 s positive, 10 s negative, bounded size).
4. `router.py`: provider allow-list, path rules (§5.1), Stripe credential check, AWS 501 after auth, settings lookup for the upstream mode (cached 30 s per user).
5. `forward.py`: shared `httpx.AsyncClient` (limits and timeouts in §5.1), no redirects, error mapping to 502 and 504.
6. `extract.py`: OpenAI usage, model, context hash and tokens, `uses_tools`; Stripe `limit`, items returned, idempotency flag. Runs after the response is sent.
7. Cost via B2. Build the log row. Send it to `writer.py` (bounded queue, batched inserts, retries, drop counter, flush on shutdown).
8. `ratelimit.py`: per-key token bucket, in-flight cap, failed-auth throttle per IP.
9. Lifespan wiring (client, writer start and stop).
10. Request-size cap (`payload_too_large`) and response-buffer cap (larger non-SSE responses stream through unparsed).

**Tests**
- Unit: hashing vectors (key order, whitespace, form-encoded ordering, big body fallback), endpoint normaliser (`cus_…`, UUIDs, numeric ids, `pi_…`), header policy table, Stripe credential check (Bearer, Basic, `sk_live_`, `rk_live_`, `pk_live_`, `sk_test_`), path rules, ingest-key hashing and verification.
- Integration (upstream faked with `respx` or `MockTransport`): **forwarded body is byte-identical** to the client body. Status, headers and body pass through (200, 400, 429 with `Retry-After`, 500). Upstream down gives 502. Timeout gives 504. Missing, invalid and revoked keys. AWS gives 501 only after auth. Unknown provider gives 404. Rate limiting. Oversize body. Redirects are not followed. Multi-value response headers survive.
- Log rows: correct fields and cost basis. **Sentinel test:** a unique string placed in request and response bodies appears in **no** table and no captured log. **Redaction test:** fake `sk_test_…`, `sk-proj-…`, `oc_…` and JWT strings sent in headers and bodies, through success, upstream failure, malformed body and handler exception paths, never appear in logs, rows or error bodies.
- Writer: batching, queue-full drop with counter, DB failure retry then drop, shutdown flush.
- Concurrency: 200 parallel requests, no cross-talk. Overhead benchmark against the in-process mock is recorded (not asserted until B11 sets the budget).

**Edge cases:** HEAD and OPTIONS. GET with a body. Chunked request bodies. `Expect: 100-continue`. Compressed request bodies (hash the raw bytes). Multipart uploads (hash raw bytes, never canonicalised). Repeated query keys. Percent-encoded path characters. Trailing and double slashes. Client disconnects mid-upload. `Content-Length` mismatch. An `X-Overcall-Caller` with odd characters (sanitised or dropped). Upstream 3xx.

**Done when**
- [x] A request through the proxy returns exactly what the upstream returned (byte-identical forward, status, multi-value headers; tested with a streaming fake upstream).
- [x] A metadata-only row appears within about two seconds, written off the request path (Postgres test: row visible within one flush interval; shutdown flush tested).
- [x] Redaction and no-body sentinel tests pass (success path, malformed body, handler exception).
- [x] Auth fails closed. Logging fails open.

**Status: done (built in this order, 248 tests green, ruff clean).**

Deviations and untested items (be honest):
- `forward.py` was not made a separate file; forwarding lives in `proxy/router.py` and the wiring in `proxy/wiring.py`. Tests are in `tests/unit/proxy/` (units plus flow) and `tests/integration/test_proxy_pg.py`; there is no `tests/security/test_proxy_*.py`, the sentinel and redaction tests are in the flow file.
- Hash golden vectors are inline in the unit test (no `hash_vectors.json`). The hash is not ported from the legacy implementation; it is new and not yet cross-checked against the frontend or demo generator.
- Fake upstreams use a small streaming `httpx` transport (not respx; `MockTransport` pre-reads bodies).
- The mock OpenAI is reached through `ASGITransport`, which buffers responses, so mock-mode `ttfb_ms` is not meaningful (B9 decides on a streaming transport).
- SSE and over-cap responses are passed through as bytes and logged with modelled/unparsed data; token counting from streams is B9.
- Detection now ignores `origin='overcall'` rows (`LogsRepository`), tested against Postgres.
- Not tested: `Expect: 100-continue`, client disconnect mid-upload, `Content-Length` mismatch, request-body hash of multipart beyond raw fallback, overhead benchmark not recorded, per-IP throttle relies on the socket peer address (no `X-Forwarded-For` trust), per-user upstream-mode cache means a mode change takes up to 30 s to apply, and a key revoked in the DB stays valid up to 60 s (cache).
- Ingest key rows must still be created by hand until B10; `INGEST_KEY_PEPPER` must be set or the proxy returns 503 `not_ready`.
- While shutting down, each batch gets a single write attempt (no retry delays).

### B9 — SSE streaming pass-through · size M

**Goal:** Stream OpenAI responses through without buffering, read usage from the final chunk, and fall back to tiktoken (marked estimated). Design: §5.2.
**Depends on:** B7, B8.
**Contract slice:** `stream`, `ttfb_ms`, `tokens_estimated`, `cost_basis` columns.

**Files:** `overcall/proxy/{sse,tokens}.py`, changes to `forward.py`, `scripts/warm_tiktoken.py`, `tests/unit/proxy/test_sse_parser.py`, `tests/integration/proxy/test_streaming.py`.

**Tasks**
1. Incremental SSE parser (`sse.py`): buffers partial lines, handles CRLF and LF, comment lines, multi-line `data:`, `[DONE]`, and chunk boundaries anywhere.
2. Streaming forward: raw bytes are yielded to the client **as they arrive**. A tee feeds the parser. Request headers `Accept: text/event-stream` are untouched.
3. Usage extraction: remember the last JSON event that has a top-level `usage` or a `response.usage`.
4. Fallback `tokens.py`: tiktoken prompt count (`o200k_base` for 4o, 4.1 and o-series, `cl100k_base` for older, default `o200k_base`; per-message overhead) and completion count from accumulated delta text (capped, then extrapolated). Marks `tokens_estimated = true`, `cost_basis = 'estimated'`.
5. Client disconnect and upstream drop: always close the upstream response, and still write a log row in `finally` with `error_code` (`client_disconnected` or `upstream_dropped`) and estimated tokens from what was seen.
6. Record `ttfb_ms` (first byte to the client) and total `latency_ms`.
7. `warm_tiktoken.py` downloads encodings at build time into `TIKTOKEN_CACHE_DIR` so a cold Render start never fetches over the network.

**Tests:** property test that splits a recorded stream at **every byte position** and at random positions and proves the parsed events and usage are identical. Usage chunk present gives `billed` basis. Absent gives `estimated`. Non-chat SSE with `response.usage`. Client disconnect leaves no leaked connection and a log row exists. Upstream drop (`X-Mock-Drop-After-Chunks`). First chunk is delivered before the stream finishes (timing test). No body text is stored.

**Edge cases:** very long streams (completion text cap). Keep-alive comments. Unicode split across chunks. Missing `[DONE]`. `n > 1`. Error event mid-stream. HTTP/1.0 upstream. Backpressure from a slow client (bounded buffer).

**Done when**
- [x] The client sees chunks as they arrive (no buffering).
- [x] Usage comes from the final chunk when available. Otherwise it is estimated and labelled so.
- [x] A disconnect never leaks a connection and still logs.

**Status: done** (267 tests passing). Deviations:
- No tiktoken: tokens are estimated at about 4 chars per token (same formula as the mock), still labelled `estimated`. `warm_tiktoken.py` was not written.
- Added `mock_openai/transport.py` (`StreamingASGITransport`), because `httpx.ASGITransport` buffers whole responses.
- Only a character count of streamed text is kept, so no completion text cap is needed.
- A dropped stream is detected by a missing `[DONE]` on chat-completions streams. Responses-API streams are not flagged.
- Tests are in `tests/unit/proxy/test_sse_parser.py` and `test_streaming.py` (no separate integration file).

### B10 — Auth and ingest keys · size M

**Goal:** Real Supabase JWT verification for `/v1/*` and complete ingest-key management. Design: §5.4.
**Depends on:** B1, B6, B8.
**Contract slice:** `/v1/ingest-keys` (§3.3), `invalid_token`, `unauthenticated`, `conflict` errors, `ingest_keys` table.

**Files:** `overcall/auth/jwt.py`, real `deps.current_user`, `overcall/api/routers/ingest_keys.py`, `tests/security/test_jwt.py`, `tests/security/test_route_auth.py`, `tests/security/test_tenant_isolation.py`, `tests/integration/test_ingest_keys.py`.

**Tasks**
1. JWT verification with `PyJWT[crypto]`: signing keys from Supabase's JWKS endpoint (cached), plus optional legacy HS256 with `SUPABASE_JWT_SECRET`. The **allowed algorithms come from configuration, never from the token header**. Check `exp`, `aud == "authenticated"` and `iss == <SUPABASE_URL>/auth/v1`. `sub` is the user id.
2. `current_user` replaces the B6 stub. Errors use `unauthenticated` or `invalid_token`.
3. Ingest keys: create (name 1–60 chars, max 5 active), list, revoke (idempotent). The plaintext is returned once. `last_used_at` is updated by the writer in batches (not per request). Revocation evicts the in-process cache.
4. First-request provisioning of `user_settings` with defaults.
5. Route-walk test: every route except `/healthz`, `/readyz` and `/proxy/*` returns 401 without a token.
6. Cross-tenant isolation test across all id-taking endpoints, auto-parametrised from the route table.

**Tests:** valid token. Expired, wrong audience, wrong issuer, bad signature, missing `sub`. **Algorithm confusion** (an HS256 token signed with the public key must be rejected when RS256 is expected). `alg: none` rejected. Key generation shape and entropy. Plaintext appears only in the create response (not in list, logs or DB). Hash lookup works, revoked key is rejected, sixth key conflicts, rename or reuse impossible. Key timing: lookup by hash, no early-exit comparison on the secret.

**Edge cases:** JWKS fetch failure (use the cached keys, then fail closed). Clock skew leeway of 30 s. Key rotation at Supabase. A user deleted in Supabase while holding a key (FK cascade). Pepper rotation (`pepper_version`, previous pepper accepted until all keys are rehashed).

**Status: done** (286 API tests passing with the local PostgreSQL integration database). JWT checks include fixed algorithm allowlists, claim validation, JWKS caching/rotation behavior and legacy HS256. Ingest-key integration covers one-time plaintext, tenant scoping, proxy use, cache eviction on revoke, and the five-active-key limit.

**Done when**
- [x] No `/v1` route works without a valid token.
- [x] Ingest keys can be created once, listed, used and revoked, and the plaintext is never retrievable again.
- [x] Isolation tests cover the id-taking log, issue and ingest-key endpoints.

### B11 — Hardening · size M

**Goal:** Make it safe and measurable enough to put on the internet.
**Depends on:** B1–B10.
**Contract slice:** `/readyz`, internal endpoints (token protected), retention behaviour (§5.5).

**Files:** `overcall/logging.py` (full redaction), `overcall/retention/purge.py`, `supabase/migrations/0003_retention_cron.sql`, `overcall/api/routers/internal.py`, `scripts/bench_proxy.py`, `.github/workflows/keepalive.yml`, `docs/adr/0003-threat-model.md`, `tests/security/*`, `tests/perf/*`.

**Tasks**
1. **Redaction suite** (§5.7): patterns, exception and traceback formatting, uvicorn access logs (disabled or reduced to method, route template and status), httpx logger at WARNING, `repr` of settings, structured `extra` fields. Randomised fuzz test.
2. Rate limits for `/v1` (per user) and throttling of failed auth per IP. Timeouts and keep-alive limits on uvicorn.
3. Security headers (`X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control: no-store` on authenticated routes). CORS tests (allowed origin, disallowed origin, no CORS on `/proxy/*`).
4. SSRF and path tests on the proxy (`//host`, `@`, `\`, `..`, encoded variants, non-`/v1` paths) can never change the upstream host.
5. Retention (§5.5): `purge_old_logs()` SQL function, `pg_cron` schedule, per-user row cap, demo expiry, tests. Internal `GET /internal/db-size` and `POST /internal/purge` protected by `INTERNAL_TOKEN`.
6. Graceful shutdown: SIGTERM flushes the log queue (test with a real subprocess).
7. Performance: `bench_proxy.py` reports p50 and p95 **added latency** against the in-process mock, and detection runtime on 100 000 rows while proxying. Record budgets (target p50 added latency ≤ 15 ms, detection under 2 s) and make regressions fail CI.
8. Supply chain: `pip-audit`, `npm audit`, pinned versions, gitleaks in CI.
9. Keep-alive workflow (§5.6) and `docs/adr/0003-threat-model.md`.
10. Optional privacy item: `DELETE /v1/account` (needs the service-role key, kept off by default).

**Tests:** all listed above, plus the logging fuzz test and the retention tests (old rows removed, recent kept, cap enforced, demo expiry).

**Edge cases:** the purge deleting millions of rows (batched, 5 000 at a time). Cron skipped while the project is paused. Internal endpoints without the token return 404, not 403, so they are not discoverable.

**Done when**
- [ ] The fuzz redaction test finds no leaked secret on any code path.
- [ ] Proxy overhead is measured and recorded. The FAQ number (F1) is updated from it.
- [ ] Retention and cap work. DB size stays within budget in a 7-day soak on synthetic traffic.
- [ ] CI blocks secrets, vulnerable dependencies and contract drift.

---

## 4C. Integration modules (I1–I3)

### I1 — Wire frontend to the real backend · size M

**Goal:** The same UI you built on mocks now runs on the real API, locally.
**Depends on:** F1–F8 and B1–B10 (B11 not required).
**Contract slice:** all of §3.

**Files:** `docker-compose.dev.yml` (Postgres plus optional local Supabase stack), `scripts/dev.ps1`, `apps/web/e2e/real-stack.spec.ts`, `.github/workflows/e2e.yml`, docs update in `README.md`.

**Tasks**
1. One command (`scripts/dev.ps1`) starts the database, API and web with `VITE_API_MODE=real` and `VITE_AUTH_MODE=supabase`. Prefer the **local Supabase stack** (`supabase start`) so end-to-end tests need no cloud secrets.
2. Configure CORS origins and the Supabase redirect URLs for localhost.
3. Switch the app to real mode. Fix every contract drift that appears (the contract is changed first, then both sides).
4. Keep MSW only for demo sessions and tests. Prove it is absent from the signed-in code path.
5. Cold-start UX: if `/readyz` is slow, show "Waking up the server. This can take up to a minute." and poll.
6. End-to-end happy path in Playwright: sign up, create an ingest key, send requests through the proxy (mock upstream) with curl or a script, see them in Logs, run detection, see issues and the Overview numbers, load and clear demo data, change settings and see them persist, log out.
7. Real and demo data scope: when live proxy logs exist, the Overview analyses only live data. Verify the "Demo data" label disappears accordingly.

**Tests:** the e2e above in CI against local Supabase. Contract check green. A test proving that a demo session makes zero calls to the real API.

**Edge cases:** JWT refresh during a long session. CORS preflight. 401 mid-session. Timezone differences. Large log lists. Error mapping of every code in §3.4 to a friendly message. Email confirmation flow against the local mail catcher.

**Done when**
- [ ] The e2e happy path passes locally and in CI.
- [ ] No page shows mock data when signed in with a real account.
- [ ] The demo session still works with the backend stopped.

### I2 — Real-traffic validation · size L

**Goal:** Evidence of detection quality on traffic you did not generate yourself, reported **separately** from synthetic accuracy.
**Depends on:** I1 (a working local stack) and B4, B5.
**Contract slice:** `GET /v1/accuracy` dataset shape, `validation/labels/real.v1.csv`, `validation/reports/real.json`.

**Files:** `validation/{README.md,samples.lock}`, `validation/scenarios/{stripe-accept-a-payment.*,vercel-ai-chat.*}`, `validation/labels/real.v1.csv`, `validation/export_logs.py`, `validation/reports/real.json`, `apps/api/scripts/evaluate_real.py`.

**Tasks**
1. Move the existing `accept-a-payment/` clone to `validation/samples/accept-a-payment/` (gitignored) and pin its commit in `samples.lock`. Clone a Vercel AI SDK chat example the same way.
2. Point **Stripe** at the local proxy using the sample's own Stripe server (pick the Python or Node server) with your **test** keys, adding `X-Overcall-Key` through the SDK's custom HTTP client. Point the **chat example** at `/proxy/openai/v1` with `defaultHeaders: {"X-Overcall-Key": …}`, upstream mock mode. This also answers OQ1 for real SDKs.
3. Script realistic scenarios with Playwright or small scripts, each with a written intent: normal browsing, double-clicked "Pay", page-refresh storms, retries on injected 429s (with and without backoff), tight polling versus polling every 15 s, chat with a long system prompt (≥ 1 100 tokens) over many turns, chat with a premium model for tiny prompts.
4. Export the logs (`export_logs.py`) from the database, redacting nothing because nothing sensitive is stored.
5. **Hand-label** `validation/labels/real.v1.csv` (`request_id, rule_id, expected (yes/no), reason, labeller, date`) using only the scenario script and the raw fields, **before** running detection. Commit the labels. They are then frozen. Any relabel is a new file version with a reason.
6. Run `evaluate_real.py`: per rule, precision and recall, the count of positives, and a Wilson 95 % interval. Report rules with fewer than about 10 positives as "low sample". Tier 3 is reported separately.
7. Write `validation/reports/real.json`, copy a snapshot into `apps/api/overcall/accuracy/latest.json`, and let `GET /v1/accuracy` serve it as the `real` dataset next to the `synthetic` one.
8. Write down every false positive and false negative with a one-line cause. Fix rule defects only through a normal PR that re-runs both reports.

**Tests:** labels file validates (ids exist, one row per labelled request, allowed values). Evaluate is deterministic on the frozen export. The report schema validates against the contract.

**Edge cases:** too few positives for a rule (say so, do not smooth it). Sample app changes upstream (pinned commit). Stripe test-mode rate limits. Mock versus real OpenAI differences (documented).

**Done when**
- [ ] Two datasets, two reports, never blended.
- [ ] Labels were committed before the first real evaluation run (git history proves it).
- [ ] The Settings accuracy table shows synthetic and real as separate rows with sample sizes.
- [ ] A short written analysis of misses and false alarms exists in `validation/README.md`.

### I3 — Deployment · size M

**Goal:** Vercel frontend, Render API, Supabase database, with environment variables, warm-up and keep-alive. Design: §5.6.
**Depends on:** I1 and B11.
**Contract slice:** environment variable tables (§5.6).

**Files:** `vercel.json`, `render.yaml`, `.github/workflows/keepalive.yml`, `docs/DEPLOY.md`, `apps/api/scripts/warm_tiktoken.py` (build step).

**Tasks**
1. Supabase production project: Auth providers (email and Google), email confirmation on, Site URL and redirect URLs, migrations through `supabase db push`, `pg_cron` enabled, Data API off for `public` tables.
2. Render web service (`rootDir: apps/api`): build installs requirements and warms tiktoken, start with `uvicorn overcall.main:app --host 0.0.0.0 --port $PORT --proxy-headers`, health check `/healthz`, env vars from §5.6 (secrets set in the dashboard, never in `render.yaml`).
3. Vercel project (`rootDir: apps/web`): Vite preset, SPA rewrite, security headers and a CSP in `vercel.json`, `VITE_*` variables.
4. CORS set to the exact Vercel origins. Supabase redirect URLs updated.
5. Warm-up: the landing page and login page fire a `GET /healthz` so Render wakes while the visitor reads. The signed-in app polls `/readyz` after a long idle.
6. Keep-alive GitHub Actions workflow (§5.6) hitting `/readyz` every 10 minutes, and a daily DB-size check that fails the workflow above 80 % of the free limit.
7. Verify SSE streaming through Render (not buffered). If it buffers, send `X-Accel-Buffering: no` and periodic comment keep-alives.
8. Smoke test script that runs against production: sign up, create key, one proxied call (mock mode), see a log row.
9. Write `docs/DEPLOY.md` including the upgrade path to an always-on instance.

**Tests:** the smoke script. Lighthouse against the deployed URL. A header check (CSP, no `Server` version leak). CORS check from a wrong origin.

**Edge cases:** Render cold start during a first signup. Supabase project paused. Missing env var (fails fast with a clear log). Vercel preview deployments (origins and Supabase redirects). GitHub Actions scheduled runs are best-effort and stop after 60 days without repo activity (add an external pinger as a backup).

**Done when**
- [ ] Production smoke test passes.
- [ ] Keep-alive runs and the DB-size alert works.
- [ ] No secret is in the repo, Vercel public variables or logs.
- [ ] The upgrade path to an always-on API is a one-line change in `render.yaml`.

---

## 5. Detailed designs for the hard parts

### 5.1 The proxy (forwarding, hashing, headers)

**Request flow**

```
client app ──► /proxy/{provider}/{path}
                │ 1  in-flight cap, size cap (413 / 503)
                │ 2  X-Overcall-Key → HMAC → cache/DB lookup        (401 on failure)   ← fail closed
                │ 3  per-key rate limit                              (429)
                │ 4  provider allow-list; AWS → 501; path rules      (404 / 501)
                │ 5  Stripe credential must be sk_test_/rk_test_     (403)
                │ 6  resolve upstream: openai → mock (default) or real; stripe → api.stripe.com
                │ 7  build forward request: same method, path, query, body BYTES, filtered headers
                ▼
        upstream (mock in-process | api.openai.com | api.stripe.com)
                │ 8  non-stream: read body. stream: pass bytes through as they arrive (§5.2)
                ▼
client ◄── same status, same body, filtered headers + X-Overcall-Request-Id
                │
                └─ after the response is sent (BackgroundTask): extract metadata, hash, cost,
                   build row → bounded queue → batch writer → Postgres                ← fail open
```

**Routing and path rules.** Only `/proxy/openai/v1/**` and `/proxy/stripe/v1/**` are forwarded. The forwarded path is `/v1/…` exactly as received after the prefix. Reject (404 `route_not_supported`) any path that contains `..`, `//`, `\`, `@`, a percent-encoded dot or slash, or does not start with `/v1/`. The upstream host comes only from the environment, never from the request. The upstream URL is assembled as `base + path` and then re-parsed to assert the host did not change.

**Header policy** (implemented over the raw header list so repeated headers survive):

| Direction | Rule |
|---|---|
| Request, forward unchanged | `authorization`, `content-type`, `accept`, `user-agent`, `idempotency-key`, `stripe-account`, `stripe-version`, `openai-organization`, `openai-project`, `openai-beta`, `x-stainless-*`, and any other header not listed below |
| Request, drop | `host`, `content-length` (the client library recomputes it), `connection`, `keep-alive`, `proxy-authenticate`, `proxy-authorization`, `te`, `trailer`, `transfer-encoding`, `upgrade`, any header named in `Connection`, `x-overcall-key`, `x-overcall-caller`, `forwarded`, `x-forwarded-*` |
| Request, replace | `accept-encoding` becomes `identity` (decision D8) |
| Response, forward unchanged | everything else, including `retry-after`, `x-request-id`, `openai-*`, `x-ratelimit-*`, `stripe-*`, multi-value headers |
| Response, drop or recompute | hop-by-hop headers, `content-length`, `content-encoding` (the body is already decoded) |
| Response, add | `x-overcall-request-id`. On errors Overcall itself generated, also `x-overcall-error` |
| Mock mode | `authorization` is dropped before the mock is called so it cannot be echoed or logged |

**Body handling.** The request body is read once as bytes, forwarded as exactly those bytes (never re-serialised), and handed to the background task only for hashing and metadata, then released. Cap: `MAX_REQUEST_BODY_BYTES` (default 10 MB). Responses over `MAX_RESPONSE_BUFFER_BYTES` (default 20 MB) are streamed through without parsing and logged with `resp_size` from a byte counter and modelled cost.

**Upstream client.** One shared `httpx.AsyncClient` per upstream: `follow_redirects=False`, no automatic retries (retrying would hide the customer's own retry behaviour, which is exactly what we measure), `http2=False`, limits `max_connections=100`, `max_keepalive_connections=20`, `keepalive_expiry=30`, timeouts `connect=5s`, `read=120s` (also the gap between stream chunks), `write=30s`, `pool=5s`. Connection failure gives 502 `upstream_unreachable`. Timeout gives 504 `upstream_timeout`. Both are logged with `origin='upstream'`, the status, and `error_code`.

**Canonical request hash.** Purpose: group identical requests. It is a grouping key, not a security primitive, so 16 hex characters (64 bits) of SHA-256 is enough because grouping is always scoped to one user, one provider, one method and a time window.

```
req_hash = sha256( METHOD + "|" + RAW_PATH + "|" + SORTED_QUERY + "|" + CANONICAL_BODY ).hexdigest()[:16]
```
- `RAW_PATH` keeps ids intact (`/v1/customers/cus_123` and `/v1/customers/cus_456` must hash differently). The stored `endpoint` is the **normalised** template (`/v1/customers/{id}`).
- `SORTED_QUERY`: query pairs sorted by (key, value), repeated keys preserved.
- `CANONICAL_BODY`: `application/json` → parse, then dump with sorted keys, compact separators, `ensure_ascii=False`. `application/x-www-form-urlencoded` → sorted `(key, value)` pairs, duplicates preserved (Stripe bracket keys such as `metadata[a]` stay as they are). Anything else, bodies over 1 MB, and bodies that fail to parse → SHA-256 of the raw bytes. Empty body → empty string.
- The `Idempotency-Key` header is excluded from the hash and recorded as the boolean `has_idempotency_key`.
- Golden vectors (kept in `apps/api/tests/data/hash_vectors.json`): reordered JSON keys hash the same; extra whitespace hashes the same; a changed value differs; reordered form fields hash the same; reordered query parameters hash the same; a different id in the path differs; a different method differs; invalid JSON falls back to the raw hash.

**Endpoint normalisation.** Segments that are all digits, long hex or UUIDs, or provider-prefixed ids (`cus_…`, `pi_…`, `ch_…`) become `{id}`. The existing normaliser is ported with test vectors for each shape, including look-alikes that must **not** be replaced (`/v1/chat/completions`, `/v1/models`).

**Metadata extracted after the response** (never stored beyond these fields):
- OpenAI request: `model`, `stream`, `uses_tools` (presence of `tools`, `functions` or `tool_choice`), `context_hash` (hash of concatenated system and developer message text when ≥ 200 characters), `context_tokens`.
- OpenAI response: actual `model`, `usage.prompt_tokens`, `usage.completion_tokens`, `usage.prompt_tokens_details.cached_tokens`.
- Stripe: `limit` query value, number of items in a list response, `Idempotency-Key` presence.
- JSON is parsed only when the content type is JSON and the body is at most 5 MB. A parse failure never propagates. The row is stored with modelled cost.
- `occurred_at` is the time the request was received. `latency_ms` is measured with a monotonic clock around the upstream call and body read.

**Caller label.** `X-Overcall-Caller` is kept only if it matches `^[A-Za-z0-9._:/-]{1,64}$`, otherwise stored as null.

**Cost.** B2 `estimate_cost` with the extracted usage. `origin='overcall'` rows (our own 401, 403, 413, 429 and 501 responses) are stored with cost 0 and `error_code`, and every detection rule ignores them.

**Async log writing.**
- `asyncio.Queue(maxsize=LOG_QUEUE_MAX)` (default 5 000). `put_nowait`; if full, the row is dropped, a counter increments and one error line per minute is logged. The customer request is never delayed.
- A flusher task collects up to `LOG_BATCH_SIZE` (200) rows or waits `LOG_FLUSH_INTERVAL_MS` (1 000), then inserts them in one statement. On a DB error it retries 3 times (0.5 s, 1 s, 2 s) and then drops with a counter. `last_used_at` for the keys involved is updated in the same flush.
- On SIGTERM (Render restarts) the lifespan shutdown drains the queue for up to 10 s.
- Accepted loss window: up to about one second of logs on a hard crash. Documented, not hidden.

**Limits.** Per-key token bucket (default 50 requests per second, burst 100). A global in-flight cap (default 100, then 503 `overloaded` with `Retry-After`). Failed-auth throttling per IP (10 per minute). All in memory because of assumption A1.

### 5.2 SSE streaming pass-through

**Goal:** the client sees each chunk when the provider sends it. Usage is read from the final chunk. If it is missing, estimate with tiktoken and say so.

**Handling**
1. Detect streaming from the **response** `content-type: text/event-stream` (not only the request flag).
2. Use `client.stream(...)` and a `StreamingResponse` whose generator yields `aiter_raw()` chunks unchanged. Add `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Status and headers are sent as soon as the upstream headers arrive.
3. A tee feeds each chunk to an incremental parser. It never delays the yield.
4. **Parser:** keep a byte buffer. Split on the first blank line (`\n\n` or `\r\n\r\n`). For each event, join its `data:` lines. Ignore comment lines (`:`). Stop on `data: [DONE]`. JSON-decode each event; remember the **last** event that has a top-level `usage` object, or a `response.usage` (Responses-style streams). Accumulate delta text (`choices[].delta.content`) up to a cap (for example 200 KB) for the fallback.
5. **Usage rule:** when the last usage event exists, tokens come from it, `cost_basis='billed'`, `tokens_estimated=false`. OpenAI only sends usage in a stream when the client asked for `stream_options.include_usage`. We do **not** alter the request, so many streams will not include it.
6. **Fallback:** prompt tokens by tiktoken over the request messages (`o200k_base` for 4o, 4.1 and o-series model names, `cl100k_base` for older names, unknown defaults to `o200k_base`, plus the documented per-message overhead). Completion tokens by tiktoken over the accumulated delta text (extrapolated by length if capped). Set `tokens_estimated=true`, `cost_basis='estimated'`. The UI shows an "est." marker.
7. **Disconnects.** If the client disconnects (cancellation or `ClientDisconnect`), close the upstream response in a `finally`. If the upstream drops, end the client stream. In both cases write the log row in the `finally`, with `error_code` (`client_disconnected` or `upstream_dropped`), the status actually received, and estimated tokens from what was seen. Use a shielded task so cancellation does not skip the log.
8. **Timing.** `ttfb_ms` is the time to the first byte forwarded to the client. `latency_ms` is the total duration. `resp_size` is the byte count of forwarded chunks.

**tiktoken operational note.** tiktoken downloads encodings on first use. On a cold Render instance that adds seconds and can fail. `scripts/warm_tiktoken.py` runs in the Render build step with `TIKTOKEN_CACHE_DIR` pointing to a directory inside the build, so the runtime never fetches from the network.

**Render check.** Render proxies HTTP and should not buffer chunked responses, but this is verified in I3 rather than assumed. If chunks are delayed, add periodic `: keepalive` comment lines and keep `X-Accel-Buffering: no`.

**Tests:** split a recorded stream at every byte offset and at random offsets and assert identical parsed events and usage. Usage present vs absent. Responses-style `response.usage`. CRLF vs LF. Unicode split mid-character. Missing `[DONE]`. Mid-stream error event. Client disconnect and upstream drop (no leaked connections, log row exists). First-chunk-before-end timing test.

### 5.3 Detection rules, defaults and savings

**Shared rules.** Rules see `LogRow` objects for one user from one data scope (live proxy rows if any exist in the retention window, otherwise demo rows). They skip `origin='overcall'` and `provider='aws'`. Rows are ordered by `(occurred_at, id)`. Windows are inclusive (`≤`). Thresholds come from the user's settings with the defaults in §3.6.

**Savings model (all rules)**
- Every flagged request has a **waste amount** that is at most that request's own cost.
- `window_savings = Σ waste`. `projected_monthly = window_savings × 30 / max(window_days, 1)`. `window_days` is the span from the first to the last analysed log. If the span is under one day, `projection_low_confidence` is set and the UI says so.
- **Impact kind.** If all flagged rows have `cost_basis` billed or estimated, the finding is **spend**. If any are `modelled` (Stripe, failed requests, endpoints without usage), the finding is split: modelled rows become a **reliability** finding with `modelled_overhead` and the rest stay spend. Stripe findings are always reliability.
- **Headline** = Σ over Tier 1 and Tier 2 spend findings, taking the **maximum waste per request** when several rules flag the same request. Tier 3 spend goes to `experimental_monthly_usd` and is never in the headline. Reliability is a **count** plus a muted modelled overhead and is never added to spend.
- **Severity** by monthly impact: critical at or above $20, warning at or above $2, otherwise info, with these per-rule overrides: `missing_cache` 40 and 1, and `oversized_payload`, `unbatched_calls`, `token_bloat`, `model_overuse` 30 and 1. A Stripe payment write without an Idempotency-Key that was duplicated is always critical. Retry storms with at least 30 retries are critical.
- Savings are labelled **estimates**. Rounding happens only at output.

**Tier 1 (deterministic)**

| Rule | Algorithm | Defaults | Savings | Known false positives (and what we do) |
|---|---|---|---|---|
| `duplicate_calls` | Group by (provider, method, `req_hash`). For each consecutive pair, flag the later call if the gap is at most `short_window_s` **and** the earlier call returned 2xx | `short_window_s = 10` | Cost of each flagged call. Stripe is reliability. Money-risk wording and critical severity for Stripe payment writes without an Idempotency-Key | Tight status polling (same GET every few seconds) looks identical. The explanation says "if this is intentional polling, back off or use webhooks". Hard-negative tests cover 10.5 s gaps, different payloads and calls after failures |
| `missing_cache` | Candidates are GET calls and POSTs listed as `deterministic_post_endpoints` (OpenAI embeddings). Flag the later call of an identical-hash pair when `short_window_s < gap ≤ long_window_s` and the earlier call returned 2xx | `short = 10`, `long = 600` | Cost of each flagged call (embeddings: spend. Stripe GET: reliability) | Data that really changed in between (a customer was updated). The fix text recommends a short TTL and invalidation by webhooks. We cannot see response bodies, so we cannot prove the data was identical |
| `retry_storm` | Within a group of identical-hash calls, build chains where each call except the last returned non-2xx and the next arrived less than `retry_min_backoff_ms` later. Flag all calls after the first in chains of at least `retry_min_attempts` | `backoff = 1000 ms`, `attempts = 3` | Cost of the flagged retries (failed-call overhead is modelled, so reliability) | Official SDK retries (about 0.5 s then 1 s) deliberately do **not** form a 3-chain under these defaults. Hard negatives include exponential backoff and two-attempt chains |

**Tier 2 (threshold based)**

| Rule | Algorithm | Defaults | Savings |
|---|---|---|---|
| `oversized_payload` | Flag a call when `max(req_size, resp_size) > oversized_bytes` (strictly greater) | `200 000` bytes | `cost × (size − limit) / size`: the share above the threshold |
| `unbatched_calls` | For endpoints that have a documented batch equivalent in the pricing file, find bursts of at least `unbatched_min_calls` calls with gaps ≤ `unbatched_window_s`, grouped by (provider, method, endpoint, caller). Flag every call after the first in each burst | `5` calls, `5 s` | `cost × discount` from the pricing file. **Each batch equivalent must cite a real, documented basis for a price or request saving (B5 check). Where none exists, the finding is reported as reliability with a modelled overhead, never as spend** |

**Tier 3 (experimental, off by default, always shows confidence and the Experimental badge)**

| Rule | Algorithm | Defaults | Savings and confidence |
|---|---|---|---|
| `token_bloat` | OpenAI chat calls, 2xx, with a `context_hash` and `context_tokens ≥ min`. Contexts that repeat at least `min_repeats` times. Flag every repeat after the first | `repeats = 3`, `context tokens = 1024` (OpenAI's automatic prompt cache starts at 1 024 tokens) | `context_tokens × (input − cached_input) / 1e6` per repeat. Confidence `min(0.85, 0.45 + 0.05 × average_repeats)` |
| `model_overuse` | Chat calls on a premium-tier model that has an entry in the downgrade map, with `prompt ≤ max_prompt`, `completion ≤ max_completion`, **`uses_tools` false**, and at least `min_calls` such calls per model | `prompt ≤ 800`, `completion ≤ 300`, `min_calls = 10` | `cost − cost at the cheaper model` at identical token counts. Confidence 0.7 if the average completion is under 60 tokens, otherwise 0.55. The explanation states that output quality is not measured |

**Evaluation (used by B4, B5 and I2).** Request-level comparison of flagged ids against labels, per rule: positives, flagged, true positives, precision, recall, and false positives on hard negatives. Reports are **per dataset** and never blended: `validation/reports/synthetic.json` and `validation/reports/real.json`.

### 5.4 Ingest keys and authentication

**Ingest key lifecycle**
1. **Create** (`POST /v1/ingest-keys`): `secrets.token_urlsafe(32)` gives 43 URL-safe characters (256 bits). The key is `oc_` + that string. `prefix = key[:9]`. `key_hash = HMAC-SHA256(INGEST_KEY_PEPPER, key)` as hex. The row stores `prefix`, `key_hash` and `pepper_version`. The full key is returned **once** in the response and never stored or logged.
2. **Use:** the proxy reads `X-Overcall-Key`, computes the HMAC and looks it up by `key_hash`. A positive result is cached for 60 s and a negative for 10 s (bounded cache). Revocation evicts the entry immediately, and any other instance would see it within 60 s.
3. **Revoke:** sets `revoked_at`. Revoked keys return 401 `ingest_key_revoked`.
4. **Limits:** 5 active keys per user. Names 1 to 60 characters.
5. **Pepper rotation:** `INGEST_KEY_PEPPER` is the current pepper, `INGEST_KEY_PEPPER_PREV` is optional. Verification tries the current pepper first, then the previous one (by `pepper_version`) and rehashes on success. Remove the previous pepper once all active keys are rehashed.
6. **Why this is safe:** a database leak exposes only HMAC hashes and prefixes. Keys are random and long, so brute force is infeasible. Failed-auth attempts are throttled per IP anyway.

**JWT verification (`/v1/*`)**
- Supabase access tokens are verified with `PyJWT[crypto]`. Signing keys come from `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` (cached, refreshed on an unknown `kid`). A legacy HS256 secret (`SUPABASE_JWT_SECRET`) is supported only when configured.
- **The accepted algorithms are fixed by configuration** (for example `RS256` and `ES256`, plus `HS256` only if a secret exists), never read from the token header. This blocks algorithm-confusion and `alg: none` attacks.
- Required: valid signature, `exp`, `aud == "authenticated"`, `iss == "<SUPABASE_URL>/auth/v1"`, `sub` present. 30 s clock leeway.
- If the JWKS endpoint is unreachable, cached keys are used. With no cached keys the request fails closed.
- The user id (`sub`) is the only identity the rest of the code sees. Repositories take it as a required argument.

**Account provisioning.** `user_settings` is created on the first authenticated request with defaults (idempotent upsert).

### 5.5 Log retention and capacity

**Budget (Supabase free: 500 MB database)**

| Item | Planned allowance |
|---|---|
| Postgres system, auth schema, extensions | about 60 MB |
| `request_logs` plus its four indexes | at most 350 MB |
| `issues`, `issue_requests`, `detection_runs`, settings, keys | at most 20 MB |
| Headroom | about 70 MB |

A `request_logs` row is estimated at 350 to 450 bytes of data plus index entries, so roughly 800 bytes all-in. That makes **100 000 rows ≈ 80 MB**. This is an estimate to be measured in B11 (`/internal/db-size` and a 7-day synthetic soak), and the cap below is adjusted from the measurement.

**Policies**
- Default retention 14 days (user-settable 1 to 90). Hard cap 100 000 rows per user (the oldest rows are removed first). Demo rows are capped at 20 000 per user.
- A completed purge does not shrink the file on disk, because Postgres reuses the freed space. So the steady state matters. Retention keeps the size flat, and the database size alert (below) is based on `pg_database_size`.

```sql
-- 0003_retention_cron.sql (shape)
create or replace function public.purge_old_logs(batch int default 5000) returns bigint
language plpgsql security definer set search_path = public as $$
declare total bigint := 0; n bigint;
begin
  loop   -- 1) age-based, in batches
    with doomed as (
      select l.id from request_logs l left join user_settings s on s.user_id = l.user_id
      where l.occurred_at < now() - make_interval(days => coalesce(s.retention_days, 14))
      limit batch)
    delete from request_logs where id in (select id from doomed);
    get diagnostics n = row_count; total := total + n; exit when n = 0;
  end loop;
  -- 2) per-user cap: keep the newest 100000 rows
  delete from request_logs where id in (
    select id from (select id, row_number() over (partition by user_id order by occurred_at desc, id desc) rn
                    from request_logs) t where rn > 100000);
  return total;
end $$;
revoke execute on function public.purge_old_logs(int) from public, anon, authenticated;
select cron.schedule('overcall-purge', '17 3 * * *', $$select public.purge_old_logs()$$);
```
`pg_cron` lives in the database, so it still runs while Render is asleep. `issue_requests` rows disappear through the cascade. `POST /internal/purge` (token protected) runs the same function on demand.

**Writes stay small:** no bodies, short hash strings, integers for sizes, `numeric(14,8)` cost, a handful of nullable columns.

### 5.6 Deployment and environment variables

**Free-tier constraints and how the plan handles them**

| Constraint | Effect | Mitigation |
|---|---|---|
| Render free web services sleep after about 15 minutes idle, with a cold start of about a minute | A proxy that sleeps will time out the first customer call | Warm-up: the landing and login pages call `/healthz` so the API wakes while the visitor reads. Keep-alive pings every 10 minutes (below). SDK timeout guidance in the Providers snippets. The public **demo does not need the backend** (D10). **Upgrade path:** change `plan: free` to `plan: starter` in `render.yaml` for an always-on instance. No code change |
| Supabase free projects pause after 7 days of inactivity | The product disappears for a returning user | The keep-alive hits `/readyz`, which runs a real query. A paused project is restored from the Supabase dashboard (documented in `docs/DEPLOY.md`) |
| 500 MB database | Logs can fill it | Retention, cap, compact schema, DB-size alert (§5.5) |
| Free instance CPU is small | Detection could slow the proxy | Detection runs in a worker thread, bounded to 200 000 rows, and B11 measures proxy latency while it runs |
| In-memory queue and rate limits | Lost on restart, not shared across instances | Single instance (A1), flush on SIGTERM, documented loss window |
| GitHub scheduled workflows are best-effort and pause after 60 days without repo activity | Keep-alive could silently stop | Add a free external pinger as a backup |

**Keep-alive workflow (`.github/workflows/keepalive.yml`):** cron every 10 minutes: `curl -fsS $API_URL/readyz`. Once a day: `curl -fsS -H "Authorization: Bearer $INTERNAL_TOKEN" $API_URL/internal/db-size` and fail the job (so GitHub emails you) when usage exceeds 80 % of 500 MB.

**Supabase setup (production)**
1. Create the project. Enable the Email provider (confirmation on) and Google (client id and secret, with Supabase's callback URL added in Google Cloud).
2. URL configuration: Site URL is the Vercel production URL. Redirect URLs include `<site>/auth/callback` and `<site>/reset`, plus `http://localhost:5173/*` for development.
3. `supabase db push` for the migrations. Enable `pg_cron`. Turn the Data API off for the `public` schema tables if the dashboard allows.
4. Use the **pooler** connection string (transaction mode) as `DATABASE_URL`.

**Web variables (public, set in Vercel and `apps/web/.env.local`)**

| Variable | Meaning |
|---|---|
| `VITE_APP_ENV` | `development` or `production` |
| `VITE_API_MODE` | `mock` (MSW) or `real` |
| `VITE_AUTH_MODE` | `mock` or `supabase` |
| `VITE_API_BASE_URL` | Render API origin, for example `https://overcall-api.onrender.com` |
| `VITE_PROXY_BASE_URL` | Origin shown in setup snippets (usually the same as the API) |
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase **anon** key (public by design) |
| `VITE_SITE_URL` | Canonical site URL for Open Graph tags |

**API variables (secret, set in Render and `apps/api/.env`)**

| Variable | Secret | Meaning and default |
|---|---|---|
| `APP_ENV` | no | `development`, `test` or `production` |
| `PORT` | no | Set by Render |
| `DATABASE_URL` | **yes** | Supabase pooler URL (`postgresql+asyncpg://…`) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | no | 5 / 5 |
| `SUPABASE_URL` | no | For issuer and JWKS |
| `SUPABASE_JWT_ALGORITHMS` | no | Fixed JWKS allowlist; `RS256,ES256` by default. Legacy HS256 is added only when its secret is configured |
| `SUPABASE_JWT_SECRET` | **yes** | Only if the project still uses legacy HS256. Unset otherwise |
| `SUPABASE_JWT_LEEWAY_SECONDS` | no | JWT clock-skew allowance; 30 seconds by default |
| `SUPABASE_SERVICE_ROLE_KEY` | **yes** | **Unset by default.** Only for the optional account deletion endpoint |
| `INGEST_KEY_PEPPER` | **yes** | At least 32 random bytes |
| `INGEST_KEY_PEPPER_PREV` | **yes** | Optional, for rotation |
| `INGEST_KEY_PEPPER_VERSION` | no | Positive version stored with new keys; increment when rotating the pepper |
| `INTERNAL_TOKEN` | **yes** | Guards `/internal/*` |
| `CORS_ORIGINS` | no | Comma separated exact origins |
| `PUBLIC_PROXY_BASE_URL` | no | Used to build snippets |
| `ALLOW_REAL_UPSTREAM` | no | `false` by default. Real OpenAI mode cannot be enabled by any user unless this is `true` |
| `OPENAI_UPSTREAM_BASE_URL` / `STRIPE_UPSTREAM_BASE_URL` | no | `https://api.openai.com` and `https://api.stripe.com`. Never user supplied |
| `MAX_REQUEST_BODY_BYTES` / `MAX_RESPONSE_BUFFER_BYTES` | no | 10 MB / 20 MB |
| `LOG_QUEUE_MAX` / `LOG_BATCH_SIZE` / `LOG_FLUSH_INTERVAL_MS` | no | 5000 / 200 / 1000 |
| `RATE_LIMIT_PROXY_RPS` / `RATE_LIMIT_API_RPM` / `MAX_INFLIGHT` | no | 50 / 120 / 100 |
| `LOG_RETENTION_DEFAULT_DAYS` / `MAX_LOGS_PER_USER` | no | 14 / 100000 |
| `TIKTOKEN_CACHE_DIR` | no | Directory populated at build time |
| `LOG_LEVEL` / `RELEASE` | no | `INFO` / git SHA |

GitHub Actions secrets: `API_URL`, `INTERNAL_TOKEN`.

**Vercel:** root `apps/web`, Vite preset, rewrite all paths to `/index.html`, headers (CSP limiting `connect-src` to the API and Supabase, `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy`). **The proxy is never hosted on Vercel** (serverless and streaming limits).

**Render:** `render.yaml` with `rootDir: apps/api`, `runtime: python`, `pythonVersion` 3.11, `healthCheckPath: /healthz`, build `pip install -r requirements.txt && python scripts/warm_tiktoken.py`, start `uvicorn overcall.main:app --host 0.0.0.0 --port $PORT --proxy-headers --no-access-log`. Secrets use `sync: false`.

### 5.7 Redaction and secret handling

**What is a secret:** `Authorization` and `Proxy-Authorization` values, `x-api-key`, OpenAI keys (`sk-…`, `sk-proj-…`), Stripe keys (`sk_`, `rk_`, `pk_` with `test` or `live`), ingest keys (`oc_…`), JWTs (`eyJ…`), Basic credentials, and anything named like `password`, `secret`, `token` or `api_key` in a key-value shape.

**Patterns** (one shared module, used everywhere):
- `(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}` and `(?i)basic\s+[A-Za-z0-9+/=]{16,}`
- `\bsk-[A-Za-z0-9_-]{16,}`
- `\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{8,}`
- `\boc_[A-Za-z0-9_-]{20,}`
- `\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}`
- `(?i)(authorization|x-api-key|api[-_]?key|secret|password|token)["']?\s*[:=]\s*["']?[^\s"',}]{6,}`

**Where it is applied**
1. A `logging.Filter` on every handler redacts the message, the arguments and the formatted exception text. A custom `Formatter.formatException` redacts tracebacks.
2. uvicorn's access log is off. Our own middleware logs method, **route template**, status, duration and request id. Query strings and headers are never logged.
3. `httpx` and `httpcore` loggers stay at WARNING (their debug output includes headers).
4. Validation errors: FastAPI's 422 detail includes the offending `input`, which can be a secret. The handler strips `input` and `ctx` and returns only `loc` and a safe message.
5. Settings `repr` masks secrets. Tracebacks never include local variables.
6. The database never receives headers or bodies by construction (no such columns, enforced by test).
7. Frontend: no `console.log` of API responses in production builds. The Supabase anon key is public by design and is not a secret, but the service-role key must never appear in `apps/web` or any `VITE_*` variable (CI greps for it).

**The redaction test (required, B1 basic, B8 proxy paths, B11 full fuzz):** generate a corpus of fake secrets in every format above (plus base64, URL-encoded and JSON-escaped variants). Send them in headers, bodies, query strings and paths through success, upstream-failure, malformed-body, oversized-body and handler-exception paths. Capture all log output at DEBUG (every logger, stdout and stderr) and dump every table. Assert that **no corpus string appears anywhere**, and that a unique sentinel placed in request and response bodies appears in no table and no log.

---

## 6. Risk register

L = likelihood, I = impact (H, M, L).

| # | Risk | L | I | Mitigation | Module |
|---|---|---|---|---|---|
| R1 | **Render cold start** makes the first proxied call hang or time out | H | H | Keep-alive every 10 min plus an external backup pinger. Warm-up pings from the landing and login pages. SDK timeout guidance in snippets. Public demo works without the backend. One-line upgrade to an always-on plan | B11, I3 |
| R2 | **The proxy is in the customer's critical path.** If Overcall is down, their app's API calls fail | M | H | State plainly that the beta is not for production traffic. Docs show a fallback pattern (try the proxy, fall back to direct on connection error). Fail-open logging. Measured overhead published. Status note in the dashboard | B8, B11, F1 |
| R3 | **Supabase pauses** after 7 days idle | M | M | Keep-alive runs a real query. Restore steps documented | I3 |
| R4 | **Database fills the 500 MB limit** | M | H | Retention (14 days), per-user cap, compact schema, size alert at 80 %, measured row size | B11 |
| R5 | **Secret leakage** through logs, tracebacks, 422 error bodies, `repr`, access logs | M | H | Central redaction module, filters on every handler, stripped validation `input`, access log off, fuzz test over all paths, gitleaks in CI | B1, B8, B11 |
| R6 | **A body or prompt gets stored by accident** (new column, debug log) | L | H | No such columns (column allowlist test). Sentinel test. Metadata extraction returns a typed struct, not the body. Code review checklist item | B1, B8 |
| R7 | **We handle plaintext provider keys in transit** (TLS terminates at the proxy) | H | H | Never store or log them. Redaction tests. Stripe test keys only. For real OpenAI mode, recommend a project-scoped key with a spend limit. Say this clearly in the FAQ and docs | B8, F1 |
| R8 | **False positives** (tight polling, SDK retries, changed data) erode trust | M | M | Hard negatives in the generator. Conservative defaults (SDK retries are not flagged). Every finding explains how it was detected and its known false positives. Tier 3 is experimental and gated | B3–B5 |
| R9 | **Circular accuracy claims** from synthetic data | H | M | Generator frozen before rules. Adversarial positives. Real hand-labelled set (I2) with labels committed before the first run. Two reports shown separately with sample sizes and intervals | B3, I2, F8 |
| R10 | **Cost inaccuracy** (stale prices, unknown models, streaming estimates, Stripe has no per-call price) | H | M | Versioned price files with `retrieved_at` and a 90-day age warning. `cost_basis` on every row. "est." and "modelled" markers in the UI. Savings always labelled estimates. Each batch equivalent needs a documented basis | B2, B5, F4 |
| R11 | **Summing spend and reliability** misleads the headline | M | H | Two stored figures, two UI cards, an automated test that no element shows the sum, contract fields named differently | B4, F4 |
| R12 | **Stripe SDKs cannot add custom headers** (for example Node's default client) | M | M | Use each SDK's custom HTTP client or fetch wrapper. Verify in I2 with real sample apps. If one SDK truly cannot, document it (OQ1, OQ3) | I2, F7 |
| R13 | **Open relay and SSRF** (the proxy used to reach other hosts, or to spend real OpenAI quota) | M | H | Auth required. Fixed upstream hosts from the environment. Strict path allow-list with traversal tests. Real upstream gated by operator flag. Rate limits | B8, B11 |
| R14 | **Tenant data leak** (application-level isolation) | L | H | Every repo method requires `user_id`. Two-user isolation tests over every id-taking route. RLS and revoked grants as defense in depth. Not-found instead of forbidden | B6, B10 |
| R15 | **JWT validation mistakes** (algorithm confusion, wrong audience) | L | H | Algorithms fixed by config. Tests for `none`, HS/RS confusion, expiry, audience, issuer | B10 |
| R16 | **Log loss on crash** (in-memory queue) | M | L | Flush on SIGTERM. At most about a second of logs lost. Counter and documentation | B8 |
| R17 | **tiktoken fetches encodings at runtime** and fails or stalls on a cold start | M | M | Pre-download at build into `TIKTOKEN_CACHE_DIR`. Fallback to length-based estimate if loading fails | B9, I3 |
| R18 | **Detection starves the proxy** on a small instance | M | M | Worker thread, row cap, 30-day window, benchmark with proxy traffic running, budget enforced in CI | B4, B11 |
| R19 | **Pooler incompatibility** (prepared statements, session locks) | M | M | `statement_cache_size=0`, transaction advisory locks only, tests against the real pooler in I3 smoke | B1, I3 |
| R20 | **Contract drift** between web and api | M | M | OpenAPI as source of truth, generated TS types, fixture validation on both sides, CI drift check | C0, B6 |
| R21 | **Identifiers in stored paths** (emails or ids inside URL paths leak into `endpoint`) | L | M | Normaliser replaces id-like segments and drops the query string. Test vectors include email-shaped and long-token segments | B8 |
| R22 | **Supply-chain or dependency vulnerabilities** | M | M | Pinned versions, `pip-audit` and `npm audit` in CI, Dependabot | B11 |
| R23 | **Scope creep and burnout** on a solo project | H | M | One module per PR with a done-when checklist. Freeze rules. S/M/L sizing. The demo-able milestones in §7 | all |
| R24 | **Google OAuth misconfiguration** (redirect mismatch) | M | L | Redirect URL checklist in `docs/DEPLOY.md`. E2E check against the local stack | F2, I3 |

---

## 7. Suggested build sequence

Sizes: **S** ≈ 1 session, **M** ≈ 2–3, **L** ≈ 4–6 (a session is about 3 focused hours). Total: roughly **55 sessions, about 165 hours**, which is 16 to 17 weeks at 10 hours a week. Treat it as a planning number, not a promise.

The order starts where you asked (landing page), gets to something demo-able fast, then tackles the riskiest backend piece (the proxy) **before** polishing the remaining screens, so surprises surface early.

| # | Module | Size | Why here | Milestone |
|---|---|---|---|---|
| 1 | **F1** Landing page | M | Public face. Creates the design tokens everything reuses | |
| 2 | **F2** Auth pages (UI) | M | Needs only the tokens | |
| 3 | **C0** Contract bootstrap | S | Fixtures and OpenAPI that F3 and the backend need | |
| 4 | **F3** App shell | M | Mock API layer for every later page | |
| 5 | **F4** Overview | M | The page that answers the core question | **M1 — Looks real.** Landing, auth, shell and Overview on mocks. Demo-able |
| 6 | **B1** Skeleton and DB | M | Real schema, error format, redaction wired from day one | |
| 7 | **B2** Pricing and cost | S | Needed by the proxy and the generator | |
| 8 | **B7** Mock OpenAI | S | The proxy's default upstream | |
| 9 | **B8** Proxy core | **L** | Riskiest module. Do it early | |
| 10 | **B9** Streaming | M | Second riskiest. Do it right after the core | **M2 — Proxy works.** `curl` through the proxy writes a metadata row |
| 11 | **B3** Synthetic generator | M | Must be frozen before any rule exists | |
| 12 | **B4** Detection core and Tier 1 | M | | |
| 13 | **B5** Tier 2 and Tier 3 | M | | **M3 — Engine works.** Synthetic precision and recall reported |
| 14 | **F5** Issues | M | | |
| 15 | **F6** Log Explorer | M | | |
| 16 | **F7** Providers | S | | |
| 17 | **F8** Settings | M | | **M4 — Every screen on mocks** |
| 18 | **B6** REST API | M | Needs B4 and B5 | |
| 19 | **B10** Auth and ingest keys | M | Real JWT and key management | |
| 20 | **B11** Hardening | M | Redaction fuzz, retention, benchmarks | **M5 — Backend complete** |
| 21 | **I1** Wire frontend to backend | M | | |
| 22 | **I2** Real-traffic validation | **L** | The honest accuracy numbers | |
| 23 | **I3** Deployment | M | Vercel, Render, Supabase, keep-alive | **M6 — Live** |

**Parallel-safe pairs** if you ever have help: F5 or F6 or F7 or F8 with any backend module. B2 with B7. B4 with F4.

**Hard rules for the sequence:** B3 is tagged `b3-frozen` before B4 starts. Labels for I2 are committed before the first real evaluation run. Contract changes go in first, then both sides adapt.

---

## 8. First-session task list (so we can start F1 the moment you approve)

**Before we start (you):** approve this plan or list changes. Answer any open question in §1.4 you care about (none block F1). Confirm you are happy that F1 includes moving `frontend/` to `apps/web/`.

Note the working tree currently has many uncommitted changes (the Overcall rename, Supabase and Google auth work, new pages). Step 1 commits that state first so the restructure starts clean.

### Session 1 — Repo move, Vite conversion, tokens, theme (about 3 h)

1. `git switch -c feat/f1-landing`. Commit the current working state as `chore: checkpoint before restructure`. The stray `supabase/migrations/.env`, `accept-a-payment/`, crash dumps and logs must **not** be committed (check `git status` first).
2. Commit `docs/PLAN.md` (`docs: add v1 implementation plan`).
3. Update `.gitignore`: `*.log`, `hs_err_pid*`, `replay_pid*`, `validation/samples/`, `.env*` (keep `.env.example`), `dist/`.
4. Delete legacy artifacts listed in §2.2 (`.emergent/`, `emergent.yml`, `test_reports/`, `test_result.md`, root `tests/`). Move `memory/PRD.md` to `docs/PRD.md`.
5. `mkdir apps` then `git mv frontend apps/web`. In `apps/web`, run `npm install --legacy-peer-deps` and confirm the existing app still starts (the baseline).
6. Convert to Vite: remove `react-scripts`, `@craco/craco` and Emergent packages. Add `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@playwright/test`, `@axe-core/playwright`, `@lhci/cli`, `@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono`. Create `vite.config.ts`, root `index.html`, `src/main.tsx`, `lib/env.ts`. Replace every `process.env.REACT_APP_*` with the `VITE_*` equivalents. Run `npm run dev` and see the existing pages render. Commit.
7. Write `src/styles/tokens.css` with the nine tokens in both themes. Map Tailwind colours to them. Add the shadcn-name aliases. Set `boxShadow` to none. Import both fonts. Commit.
8. Write `lib/theme.ts`, the inline pre-paint script in `index.html`, and `ThemeToggle`. Check the existing pages in light and dark. Commit.

### Session 2 — The landing page (about 3 h)

9. Build `Button`, `Card`, `Badge`, `Container`, `Accordion`.
10. Build the landing sections in order: nav, hero, three-step explainer, static dashboard preview, what it catches (Tier 3 marked Experimental), free-during-beta note, FAQ, footer. Use the copy in F1.
11. Router: `/` Landing. "Try the demo" links to `/app` and the nav "Sign up" links to `/signup` (nav also has "Log in" to `/login`). Stubs are fine for those routes.
12. Page title, meta description, Open Graph and Twitter tags, `favicon.svg`, `og.png`, `robots.txt`, skip link, landmarks, reduced-motion handling.
13. `scripts/check-design-rules.mjs` (no gradients or shadows, severity colours only in issue components). Unit and component tests.
14. Playwright: no network except static assets, route checks, `axe` in both themes. Lighthouse CI run (accessibility ≥ 90).
15. Review in both themes at 320, 768 and 1280 px. Fix issues. Open the PR with the F1 done-when checklist. Tag `module/f1-done`.

### Session 3 (only if needed)

Spillover from the Vite conversion (peer-dependency cleanup, Tailwind config edge cases) or Lighthouse fixes.

**After F1:** F2 uses the tokens and primitives from this session. Then C0, F3, F4 (milestone M1).

---

## Appendix A — Definition of done (every module)

- [ ] The module's own done-when list is fully ticked in the PR description.
- [ ] Tests listed in the module are written and green. Lint, types and formatting are clean.
- [ ] `check-contract` is green (fixtures valid, no drift, types fresh).
- [ ] No secret, key or body-like data in code, fixtures, logs or screenshots (gitleaks green).
- [ ] The security rules at the top of §4B still hold (redaction and no-body tests pass).
- [ ] Accessibility: `axe` clean on new pages. Focus visible. Keyboard operable.
- [ ] Docs touched by the change are updated (README, `docs/DEPLOY.md`, contract README).
- [ ] The module can be built and tested without importing the other side's code.

## Appendix B — Handing a single module back to me

Paste these three things and nothing else:
1. The module's own section from §4 (it already lists its contract slice, files, tasks, tests and done-when).
2. §3.4 (the error format), plus any `§5.x` design the module cites (for example B8 cites §5.1, B9 cites §5.2, B4 and B5 cite §5.3, B10 cites §5.4, B11 cites §5.5 to §5.7).
3. Any files you want me to modify that already exist (or tell me the path).

## Appendix C — Rename map (so nothing old survives)

| Old | New |
|---|---|
| API Cost Guard, Cost Guard | Overcall |
| `costguard` Python package | `overcall` |
| `X-CostGuard-Key` / `X-CostGuard-Caller` | `X-Overcall-Key` / `X-Overcall-Caller` |
| `x-costguard-request-id` | `x-overcall-request-id` |
| `x-costguard-upstream` (per-request override) | **removed** (see §2.5) |
| `/api/…` routes | `/v1/…` (API), `/proxy/…` (proxy) |
| `REACT_APP_*` | `VITE_*` |
| MongoDB collections, Supabase REST adapter | Postgres tables via SQLModel (§3.2) |
