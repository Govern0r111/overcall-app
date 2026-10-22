import re

from overcall.db.models import RequestLog

EXPECTED_REQUEST_LOG_COLUMNS = {
    "id",
    "user_id",
    "ingest_key_id",
    "source",
    "origin",
    "occurred_at",
    "provider",
    "method",
    "endpoint",
    "status",
    "latency_ms",
    "ttfb_ms",
    "req_size",
    "resp_size",
    "req_hash",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "cached_prompt_tokens",
    "tokens_estimated",
    "stream",
    "context_hash",
    "context_tokens",
    "uses_tools",
    "list_limit",
    "items_returned",
    "has_idempotency_key",
    "caller",
    "cost_usd",
    "cost_basis",
    "pricing_version",
    "error_code",
}


def test_request_log_has_only_metadata_columns() -> None:
    columns = {column.name for column in RequestLog.__table__.columns}
    forbidden = re.compile(r"body|content|header|authorization|secret|key_plain", re.IGNORECASE)
    forbidden_prompt = re.compile(r"^prompt$", re.IGNORECASE)

    assert columns == EXPECTED_REQUEST_LOG_COLUMNS
    assert not [name for name in columns if forbidden.search(name)]
    assert not [name for name in columns if forbidden_prompt.search(name)]
    assert "prompt_tokens" in columns
    assert "context_hash" in columns
