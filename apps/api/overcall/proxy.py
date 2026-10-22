import json
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .db import logs_col
from .engine import mark_dirty
from .hashing import context_hash, normalize_endpoint, payload_hash
from .mock_llm import mock_app
from .models import RequestLog
from .pricing_config import PRICING, estimate_cost
from .settings_store import get_settings

router = APIRouter(prefix="/api/proxy")
http_client = httpx.AsyncClient(timeout=90)
mock_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://mock-llm", timeout=30)

DROP_REQ = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding"}
DROP_RESP = {"content-encoding", "content-length", "transfer-encoding", "connection"}
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def bearer_key(headers) -> str:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if auth.lower().startswith("basic "):
        import base64
        try:
            return base64.b64decode(auth[6:]).decode().split(":")[0]
        except ValueError:
            return ""
    return ""


def resolve_upstream(provider: str, headers, openai_mode: str):
    if provider == "openai":
        if openai_mode == "real":
            return http_client, PRICING["openai"]["upstream"]["real"], "real"
        return mock_client, "", "mock"
    key = bearer_key(headers)
    base = PRICING["stripe"]["upstream"]["emergent_test" if "sk_test_emergent" in key else "real"]
    return http_client, base, "test"


def safe_json(raw: bytes):
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, UnicodeDecodeError):
        return {}


def extract_meta(provider: str, req_body: bytes, resp_body: bytes, query) -> dict:
    req, resp = safe_json(req_body), safe_json(resp_body)
    req = req if isinstance(req, dict) else {}
    resp = resp if isinstance(resp, dict) else {}
    if provider == "openai":
        usage = resp.get("usage") or {}
        return {"model": resp.get("model") or req.get("model"), "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0), "context_hash": context_hash(req.get("messages"))}
    limit = query.get("limit")
    return {"list_limit": int(limit) if limit and limit.isdigit() else None,
            "items_returned": len(resp["data"]) if resp.get("object") == "list" and isinstance(resp.get("data"), list) else None}


@router.api_route("/{provider}/{path:path}", methods=METHODS)
async def proxy(provider: str, path: str, request: Request):
    if provider == "aws":
        return JSONResponse({"error": "AWS proxying is stubbed in v1. Pricing schema is ready; forwarding is not."}, status_code=501)
    if provider not in ("openai", "stripe"):
        return JSONResponse({"error": f"Unknown provider '{provider}'. Use openai or stripe."}, status_code=404)
    if provider == "stripe" and bearer_key(request.headers).startswith(("sk_live", "rk_live")):
        return JSONResponse({"error": "v1 proxies Stripe test mode only. Use an sk_test_ key."}, status_code=403)

    settings = await get_settings()
    client, base, _mode = resolve_upstream(provider, request.headers, settings.openai_upstream)
    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in DROP_REQ
        and k.lower() not in {"x-overcall-key", "x-overcall-caller"}
        and not k.lower().startswith("x-forwarded-")
    }
    upstream_path = "/" + path
    started = time.perf_counter()
    try:
        resp = await client.request(request.method, f"{base}{upstream_path}", params=list(request.query_params.multi_items()),
                                    content=body, headers=headers)
        status, content, resp_headers = resp.status_code, resp.content, resp.headers
    except httpx.RequestError as exc:
        status, content, resp_headers = 502, json.dumps({"error": f"Upstream unreachable: {type(exc).__name__}"}).encode(), {"content-type": "application/json"}
    latency = (time.perf_counter() - started) * 1000

    meta = extract_meta(provider, body, content, request.query_params)
    log = RequestLog(
        timestamp=datetime.now(timezone.utc), provider=provider, endpoint=normalize_endpoint(upstream_path),
        method=request.method, req_size=len(body),
        req_hash=payload_hash(request.method, upstream_path, request.url.query, body, request.headers.get("content-type", "")),
        status=status, resp_size=len(content), latency_ms=round(latency, 1),
        cost_usd=estimate_cost(provider, meta.get("model"), meta.get("prompt_tokens", 0), meta.get("completion_tokens", 0), status),
        source="proxy", caller=request.headers.get("x-overcall-caller"),
        has_idempotency_key="idempotency-key" in request.headers, **meta,
    )
    await logs_col.insert_one(log.to_record())
    mark_dirty()

    out_headers = {k: v for k, v in resp_headers.items() if k.lower() not in DROP_RESP}
    out_headers["x-overcall-request-id"] = log.id
    return Response(content=content, status_code=status, headers=out_headers)
