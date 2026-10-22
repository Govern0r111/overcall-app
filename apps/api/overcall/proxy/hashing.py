from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import parse_qsl

MAX_CANONICAL_BYTES = 1_000_000

_ID_PATTERNS = [
    re.compile(r"^\d+$"),
    re.compile(r"^[0-9a-f]{16,}$", re.I),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I),
    re.compile(r"^[a-z]{2,8}_(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{6,}$"),
]
_CALLER = re.compile(r"^[A-Za-z0-9._:/-]{1,64}$")


def normalize_endpoint(path: str) -> str:
    parts = path.split("/")
    out = []
    for part in parts:
        if part and any(p.match(part) for p in _ID_PATTERNS):
            out.append("{id}")
        else:
            out.append(part)
    return "/".join(out)


def clean_caller(value: str | None) -> str | None:
    if value is None:
        return None
    return value if _CALLER.match(value) else None


def _canonical_body(body: bytes, content_type: str) -> bytes:
    if not body:
        return b""
    if len(body) > MAX_CANONICAL_BYTES:
        return body
    ctype = content_type.split(";")[0].strip().lower()
    try:
        if ctype == "application/json" or ctype.endswith("+json"):
            parsed = json.loads(body)
            return json.dumps(
                parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        if ctype == "application/x-www-form-urlencoded":
            pairs = parse_qsl(body.decode(), keep_blank_values=True)
            return "&".join(f"{k}={v}" for k, v in sorted(pairs)).encode()
    except (ValueError, UnicodeDecodeError):
        return body
    return body


def request_hash(method: str, raw_path: str, query: str, body: bytes, content_type: str) -> str:
    sorted_query = "&".join(f"{k}={v}" for k, v in sorted(parse_qsl(query, keep_blank_values=True)))
    digest = hashlib.sha256()
    digest.update(f"{method.upper()}|{raw_path}|{sorted_query}|".encode())
    digest.update(_canonical_body(body, content_type))
    return digest.hexdigest()[:16]
