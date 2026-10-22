import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode

ID_SEGMENT = re.compile(
    r"^(?:\d+|[0-9a-f-]{20,}|[a-z]{2,8}_(?=[A-Za-z0-9_]*[0-9A-Z])[A-Za-z0-9_]{6,}|[a-z]+-(?=[A-Za-z0-9]*[0-9])[A-Za-z0-9]{8,})$"
)


def sha(text: str, n: int = 16) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def normalize_endpoint(path: str) -> str:
    parts = [p for p in path.split("?")[0].split("/") if p]
    return "/" + "/".join("{id}" if ID_SEGMENT.match(p) else p for p in parts)


def canonical_body(body: bytes, content_type: str) -> str:
    if not body:
        return ""
    ct = (content_type or "").lower()
    try:
        if "json" in ct:
            return json.dumps(json.loads(body), sort_keys=True, separators=(",", ":"))
        if "x-www-form-urlencoded" in ct:
            return urlencode(sorted(parse_qsl(body.decode(), keep_blank_values=True)))
    except (ValueError, UnicodeDecodeError):
        pass
    return hashlib.sha256(body).hexdigest()


def payload_hash(method: str, path: str, query: str, body: bytes, content_type: str) -> str:
    q = urlencode(sorted(parse_qsl(query or "", keep_blank_values=True)))
    return sha(f"{method.upper()}|{path}|{q}|{canonical_body(body, content_type)}")


def context_hash(messages) -> str | None:
    if not isinstance(messages, list):
        return None
    system = "".join(
        str(m.get("content", "")) for m in messages if isinstance(m, dict) and m.get("role") in ("system", "developer")
    )
    return sha(system) if len(system) >= 200 else None
