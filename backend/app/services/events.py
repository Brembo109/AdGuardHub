"""In-process pub/sub feeding the SSE stream that the UI subscribes to."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any


class EventBus:
    """Fan-out to every connected SSE client.

    Subscribers get a bounded queue; a client that cannot keep up drops events
    rather than stalling the producer.
    """

    def __init__(self, queue_size: int = 200) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    async def publish(self, event: str, data: Any) -> None:
        payload = json.dumps({"event": event, "data": data}, default=str)
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(payload)

    async def subscribe(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {payload}\n\n"
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


bus = EventBus()
