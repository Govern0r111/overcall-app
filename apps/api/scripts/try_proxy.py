"""Send sample traffic through the local OverCall proxy so it shows up in the dashboard.

Local only. Run the dev server first (scripts/dev_server.py), then from apps/api:
    set DEV_DATABASE_URL=postgresql://postgres@127.0.0.1:53697/overcall_test
    python scripts/try_proxy.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overcall.auth.ingest_keys import generate_key, hash_key  # noqa: E402
from scripts.dev_server import DEV_PEPPER, DEV_USER  # noqa: E402

BASE = os.getenv("OVERCALL_URL", "http://127.0.0.1:8000")
CHAT = f"{BASE}/proxy/openai/v1/chat/completions"


async def make_key(db_url: str) -> str:
    key, prefix = generate_key()
    engine = create_async_engine(db_url, connect_args={"statement_cache_size": 0})
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into public.ingest_keys (id, user_id, name, prefix, key_hash, "
                "pepper_version) values (:i, :u, 'try_proxy', :p, :h, 1)"
            ),
            {"i": uuid4(), "u": DEV_USER, "p": prefix, "h": hash_key(key, DEV_PEPPER)},
        )
    await engine.dispose()
    return key


def body(content: str, **extra: object) -> dict:
    return {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": content}], **extra}


def main() -> None:
    url = os.getenv("DEV_DATABASE_URL", "")
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("DEV_DATABASE_URL must point at a local database.")
    key = asyncio.run(make_key(url.replace("postgresql://", "postgresql+asyncpg://", 1)))
    headers = {"X-Overcall-Key": key, "Authorization": "Bearer sk-local-mock"}
    sent: dict[str, int] = {}

    with httpx.Client(timeout=30) as c:

        def post(label: str, payload: dict, extra: dict | None = None) -> None:
            r = c.post(CHAT, json=payload, headers={**headers, **(extra or {})})
            sent[label] = sent.get(label, 0) + 1
            if r.status_code >= 500 and label != "failing upstream":
                print(f"  {label}: HTTP {r.status_code} {r.text[:200]}")

        for i in range(5):
            post("normal", body(f"Say hello #{i}"))
        for _ in range(6):
            post("duplicate", body("What is the capital of France?"))
        for _ in range(4):
            post("retry storm", body("Summarize this report"), {"X-Mock-Status": "429"})
        post(
            "streaming (billed)",
            body("Stream me", stream=True, stream_options={"include_usage": True}),
        )
        post("streaming (estimated)", body("Stream me too", stream=True))
        post("big response", body("Give me everything"), {"X-Mock-Resp-Bytes": "400000"})
        post("failing upstream", body("This one fails"), {"X-Mock-Status": "500"})

        time.sleep(3)  # let the background log writer flush
        run = c.post(f"{BASE}/v1/detection/run", json={})
        print(f"detection run: HTTP {run.status_code}")

    print("Sent:", ", ".join(f"{k} x{v}" for k, v in sent.items()))
    print("Open http://localhost:5173/logs (Live rows) and /issues to see the results.")


if __name__ == "__main__":
    main()
