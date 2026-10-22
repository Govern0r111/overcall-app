create extension if not exists pgcrypto;

create table if not exists public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  currency text not null default 'INR' check (currency in ('INR', 'USD')),
  usd_inr_rate numeric(10,4) not null default 83.5 check (usd_inr_rate > 0),
  rules_enabled jsonb not null default '{}'::jsonb,
  tier3_enabled boolean not null default false,
  thresholds jsonb not null default '{}'::jsonb,
  upstream_mode text not null default 'mock' check (upstream_mode in ('mock', 'real')),
  retention_days int not null default 14 check (retention_days between 1 and 90),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.ingest_keys (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 60),
  prefix text not null,
  key_hash text not null unique,
  pepper_version smallint not null default 1,
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at timestamptz
);
create index if not exists ingest_keys_user_active on public.ingest_keys (user_id) where revoked_at is null;

create table if not exists public.request_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ingest_key_id uuid references public.ingest_keys(id) on delete set null,
  source text not null check (source in ('proxy', 'demo')),
  origin text not null default 'upstream' check (origin in ('upstream', 'overcall')),
  occurred_at timestamptz not null,
  provider text not null check (provider in ('openai', 'stripe', 'aws')),
  method text not null,
  endpoint text not null,
  status int not null,
  latency_ms real not null,
  ttfb_ms real,
  req_size int not null,
  resp_size int not null,
  req_hash text not null,
  model text,
  prompt_tokens int not null default 0,
  completion_tokens int not null default 0,
  cached_prompt_tokens int not null default 0,
  tokens_estimated boolean not null default false,
  stream boolean not null default false,
  context_hash text,
  context_tokens int,
  uses_tools boolean not null default false,
  list_limit int,
  items_returned int,
  has_idempotency_key boolean not null default false,
  caller text check (char_length(caller) <= 64),
  cost_usd numeric(14,8) not null default 0,
  cost_basis text not null check (cost_basis in ('billed', 'estimated', 'modelled')),
  pricing_version text,
  error_code text
);
create index if not exists request_logs_user_time on public.request_logs (user_id, occurred_at desc, id desc);
create index if not exists request_logs_dedupe on public.request_logs (user_id, provider, method, req_hash, occurred_at);
create index if not exists request_logs_occurred_at on public.request_logs (occurred_at);
create index if not exists request_logs_demo on public.request_logs (user_id) where source = 'demo';

create table if not exists public.detection_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null check (status in ('running', 'succeeded', 'failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  is_demo_data boolean not null,
  window_start timestamptz,
  window_end timestamptz,
  window_days numeric(8,3),
  projection_low_confidence boolean not null default false,
  request_count int not null default 0,
  flagged_request_count int not null default 0,
  total_spend_usd numeric(14,6) not null default 0,
  spend_savings_window_usd numeric(14,6) not null default 0,
  spend_savings_monthly_usd numeric(14,6) not null default 0,
  experimental_monthly_usd numeric(14,6) not null default 0,
  reliability_count int not null default 0,
  reliability_overhead_monthly_usd numeric(14,6) not null default 0,
  issue_counts jsonb not null default '{}'::jsonb,
  trend jsonb not null default '[]'::jsonb,
  settings_snapshot jsonb not null default '{}'::jsonb,
  pricing_versions jsonb not null default '{}'::jsonb,
  rule_errors jsonb not null default '[]'::jsonb,
  duration_ms int
);
create index if not exists detection_runs_user on public.detection_runs (user_id, started_at desc);

create table if not exists public.issues (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  run_id uuid not null references public.detection_runs(id) on delete cascade,
  rule_id text not null,
  tier int not null check (tier in (1, 2, 3)),
  experimental boolean not null,
  provider text not null,
  endpoint text not null,
  severity text not null check (severity in ('critical', 'warning', 'info')),
  impact_kind text not null check (impact_kind in ('spend', 'reliability')),
  title text not null,
  summary text not null,
  explanation text not null,
  suggested_fix text not null,
  affected_count int not null,
  window_savings_usd numeric(14,6) not null default 0,
  projected_monthly_usd numeric(14,6) not null default 0,
  confidence real,
  is_demo_data boolean not null,
  detected_at timestamptz not null default now()
);
create index if not exists issues_user on public.issues (user_id, severity, projected_monthly_usd desc);

create table if not exists public.issue_requests (
  issue_id uuid not null references public.issues(id) on delete cascade,
  request_id uuid not null references public.request_logs(id) on delete cascade,
  user_id uuid not null,
  waste_usd numeric(14,8) not null default 0,
  primary key (issue_id, request_id)
);
create index if not exists issue_requests_request on public.issue_requests (request_id);
