from __future__ import annotations

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_REQUEST_DROP = {
    "host",
    "content-length",
    "x-overcall-key",
    "x-overcall-caller",
    "forwarded",
    "accept-encoding",
}
_RESPONSE_DROP = {"content-length", "content-encoding"}

Headers = list[tuple[str, str]]


def _connection_tokens(headers: Headers) -> set[str]:
    tokens: set[str] = set()
    for name, value in headers:
        if name.lower() == "connection":
            tokens.update(t.strip().lower() for t in value.split(",") if t.strip())
    return tokens


def upstream_request_headers(headers: Headers, *, drop_authorization: bool) -> Headers:
    extra = _connection_tokens(headers)
    out: Headers = []
    for name, value in headers:
        lower = name.lower()
        if (
            lower in HOP_BY_HOP
            or lower in _REQUEST_DROP
            or lower in extra
            or lower.startswith("x-forwarded-")
            or (drop_authorization and lower == "authorization")
        ):
            continue
        out.append((name, value))
    out.append(("accept-encoding", "identity"))
    return out


def client_response_headers(headers: Headers, request_id: str) -> Headers:
    extra = _connection_tokens(headers)
    out: Headers = [
        (n, v)
        for n, v in headers
        if n.lower() not in HOP_BY_HOP
        and n.lower() not in _RESPONSE_DROP
        and n.lower() not in extra
        and n.lower() != "x-overcall-request-id"
    ]
    out.append(("x-overcall-request-id", request_id))
    return out
