from __future__ import annotations

import hashlib
import hmac
import secrets

KEY_PREFIX = "oc_"
PREFIX_LENGTH = 9


def generate_key() -> tuple[str, str]:
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    return key, key[:PREFIX_LENGTH]


def hash_key(key: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), key.encode(), hashlib.sha256).hexdigest()


def looks_like_key(value: str) -> bool:
    return value.startswith(KEY_PREFIX) and 12 <= len(value) <= 128 and value.isascii()
