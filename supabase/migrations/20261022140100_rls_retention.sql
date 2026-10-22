alter table public.user_settings enable row level security;
alter table public.ingest_keys enable row level security;
alter table public.request_logs enable row level security;
alter table public.detection_runs enable row level security;
alter table public.issues enable row level security;
alter table public.issue_requests enable row level security;

revoke all on public.user_settings, public.ingest_keys, public.request_logs,
              public.detection_runs, public.issues, public.issue_requests
  from anon, authenticated;
