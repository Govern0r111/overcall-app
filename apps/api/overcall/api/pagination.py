from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from ..errors import OvercallError

MAX_CURSOR_LENGTH = 512
DEFAULT_LIMIT = 50


def _invalid() -> OvercallError:
    return OvercallError("invalid_cursor", 400, "The page cursor is not valid. Start again.")


def encode_cursor(timestamp: datetime, item_id: UUID) -> str:
    payload = json.dumps({"t": timestamp.isoformat(), "id": str(item_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(raw: str) -> tuple[datetime, UUID]:
    """Cursors carry no authority: every query is already scoped to the user in SQL.

    Anything that does not parse strictly is rejected, so tampering can only
    produce `invalid_cursor`.
    """
    if not raw or len(raw) > MAX_CURSOR_LENGTH:
        raise _invalid()
    try:
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if not isinstance(data, dict) or set(data) != {"t", "id"}:
            raise ValueError
        timestamp = datetime.fromisoformat(data["t"])
        if timestamp.tzinfo is None:
            raise ValueError
        return timestamp, UUID(data["id"])
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError):
        raise _invalid() from None
