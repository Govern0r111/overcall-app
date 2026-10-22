# Try OverCall locally

Everything runs on your machine. Nothing talks to Supabase or a real provider.

## 1. Start the services (three terminals)

```powershell
# Postgres (embedded, port 53697) - only if it is not already running
python $env:TEMP\ocpg_run.py

# API (from apps\api)
$env:DEV_DATABASE_URL='postgresql://postgres@127.0.0.1:53697/overcall_test'
python scripts\dev_server.py

# Web (from apps\web)
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173

If port 8000 is already occupied, make sure the API process is running from this checkout;
the B10 key routes are not available from older API processes.

## 2. Click path

1. Landing page -> **Log in** -> **Continue as demo**.
2. **Load demo data** (top bar) -> Overview fills with spend, savings and a trend chart.
3. **Issues**: filter by severity or provider, expand a row to see the explanation and fix.
4. **Logs**: search and filter, click a row for details.
5. **Providers**: create an ingest key, copy it from the one-time dialog, and review its prefix and last-used time. The plaintext cannot be retrieved from the key list; revoke the key when finished.
6. **Settings**: currency, rule toggles, **Delete demo data**.

## 3. Send real proxy traffic

```powershell
# from apps\api, with DEV_DATABASE_URL set as above
python scripts\try_proxy.py
```

It creates an ingest key, sends normal, duplicate, retry-storm, streaming and oversized
requests through the proxy to the built-in mock OpenAI, then runs detection.
Refresh **Logs** (rows marked live) and **Issues** (retry storm, duplicate calls, oversized payload).

## Authentication modes

The local `dev_server.py` intentionally uses one fixed local user and bypasses Supabase JWT
verification. It refuses non-local database hosts and binds to loopback; never deploy it.
For real Supabase sign-in, configure `SUPABASE_URL` and (only for legacy HS256 projects)
`SUPABASE_JWT_SECRET` in the API, and set the matching Supabase URL/anon key in the web app.
The API verifies JWT issuer, audience, expiry, and signature before serving `/v1/*`.
