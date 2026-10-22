from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import unquote

import httpx


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, queue: asyncio.Queue, task: asyncio.Task, closed: asyncio.Event) -> None:
        self._queue = queue
        self._task = task
        self._closed = closed

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            kind, value = await self._queue.get()
            if kind == "body":
                if value:
                    yield value
            elif kind == "error":
                raise httpx.ReadError("in-process app failed") from value
            else:
                return

    async def aclose(self) -> None:
        self._closed.set()
        if not self._task.done():
            self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task


class StreamingASGITransport(httpx.AsyncBaseTransport):
    """Runs an ASGI app in-process and hands response chunks over as they are produced.

    httpx.ASGITransport collects the whole response first, which hides streaming behaviour.
    """

    def __init__(self, app: Any, client: tuple[str, int] = ("127.0.0.1", 123)) -> None:
        self.app = app
        self.client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "headers": [(k.lower(), v) for k, v in request.headers.raw],
            "scheme": request.url.scheme,
            "path": unquote(request.url.path),
            "raw_path": request.url.raw_path.split(b"?")[0],
            "query_string": request.url.query,
            "server": (request.url.host, request.url.port or 80),
            "client": self.client,
            "root_path": "",
        }
        queue: asyncio.Queue = asyncio.Queue(maxsize=16)
        closed = asyncio.Event()
        sent_body = False

        async def receive() -> dict[str, Any]:
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": body, "more_body": False}
            await closed.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            if closed.is_set():
                return
            if message["type"] == "http.response.start":
                await queue.put(("start", (message["status"], message.get("headers", []))))
            elif message["type"] == "http.response.body":
                await queue.put(("body", message.get("body", b"")))

        async def run() -> None:
            try:
                await self.app(scope, receive, send)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await queue.put(("error", exc))
            else:
                await queue.put(("end", None))

        task = asyncio.get_running_loop().create_task(run())
        kind, value = await queue.get()
        if kind != "start":
            closed.set()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            raise httpx.ReadError("in-process app did not respond")
        status, headers = value
        return httpx.Response(
            status, headers=headers, stream=_ResponseStream(queue, task, closed), request=request
        )
