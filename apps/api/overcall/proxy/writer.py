from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ..logging import get_logger

logger = get_logger(__name__)

Sink = Callable[[list[dict[str, Any]]], Awaitable[None]]


class LogWriter:
    def __init__(
        self,
        sink: Sink,
        *,
        queue_max: int = 5000,
        batch_size: int = 200,
        flush_interval: float = 1.0,
        retry_delays: tuple[float, ...] = (0.5, 1.0, 2.0),
        drain_timeout: float = 10.0,
    ) -> None:
        self.sink = sink
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.retry_delays = retry_delays
        self.drain_timeout = drain_timeout
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_max)
        self.dropped = 0
        self.written = 0
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._last_drop_log = 0.0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run())

    def submit(self, row: dict[str, Any]) -> bool:
        try:
            self.queue.put_nowait(row)
            return True
        except asyncio.QueueFull:
            self._count_drop(1, "queue_full")
            return False

    def _count_drop(self, n: int, reason: str) -> None:
        self.dropped += n
        now = time.monotonic()
        if now - self._last_drop_log >= 60:
            self._last_drop_log = now
            logger.error("log_rows_dropped reason=%s total_dropped=%s", reason, self.dropped)

    def _take_batch(self) -> list[dict[str, Any]]:
        batch: list[dict[str, Any]] = []
        while len(batch) < self.batch_size:
            try:
                batch.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _write(self, batch: list[dict[str, Any]]) -> None:
        for attempt in range(len(self.retry_delays) + 1):
            try:
                await self.sink(batch)
                self.written += len(batch)
                return
            except Exception:
                if attempt == len(self.retry_delays) or self._stopping:
                    self._count_drop(len(batch), "write_failed")
                    return
                await asyncio.sleep(self.retry_delays[attempt])

    async def _run(self) -> None:
        while not self._stopping:
            try:
                first = await asyncio.wait_for(self.queue.get(), timeout=self.flush_interval)
            except TimeoutError:
                continue
            batch = [first, *self._take_batch()][: self.batch_size]
            await self._write(batch)

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self.drain_timeout)
            except (TimeoutError, asyncio.CancelledError):
                pass
            self._task = None
        deadline = time.monotonic() + self.drain_timeout
        while not self.queue.empty() and time.monotonic() < deadline:
            await self._write(self._take_batch())
        if not self.queue.empty():
            self._count_drop(self.queue.qsize(), "shutdown")
