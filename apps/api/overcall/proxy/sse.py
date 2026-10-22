from __future__ import annotations

from dataclasses import dataclass

MAX_LINE_BYTES = 1_000_000


@dataclass(frozen=True)
class SSEEvent:
    event: str
    data: str


class SSEParser:
    """Incremental Server-Sent Events parser.

    Works on bytes so a multi-byte character split across chunks is never decoded
    until its whole line has arrived (newline bytes never occur inside a UTF-8 sequence).
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._data: list[str] = []
        self._event = ""
        self.overflowed = False

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        self._buf += chunk
        events: list[SSEEvent] = []
        while True:
            end = self._find_line_end()
            if end is None:
                break
            line_end, next_start = end
            line = bytes(self._buf[:line_end])
            del self._buf[:next_start]
            self._line(line, events)
        if len(self._buf) > MAX_LINE_BYTES:
            self._buf.clear()
            self.overflowed = True
        return events

    def finish(self) -> list[SSEEvent]:
        events: list[SSEEvent] = []
        if self._buf:
            line = bytes(self._buf).rstrip(b"\r")
            self._buf.clear()
            self._line(line, events)
        self._dispatch(events)
        return events

    def _find_line_end(self) -> tuple[int, int] | None:
        buf = self._buf
        for index, byte in enumerate(buf):
            if byte == 0x0A:
                return index, index + 1
            if byte == 0x0D:
                if index + 1 >= len(buf):
                    return None
                return index, index + 2 if buf[index + 1] == 0x0A else index + 1
        return None

    def _dispatch(self, events: list[SSEEvent]) -> None:
        if self._data:
            events.append(SSEEvent(self._event or "message", "\n".join(self._data)))
        self._data = []
        self._event = ""

    def _line(self, raw: bytes, events: list[SSEEvent]) -> None:
        if not raw:
            self._dispatch(events)
            return
        if raw.startswith(b":"):
            return
        text = raw.decode("utf-8", errors="replace")
        field, sep, value = text.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if field == "data":
            self._data.append(value)
        elif field == "event":
            self._event = value
