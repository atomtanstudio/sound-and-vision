"""Live updates to every open window. Anything that changes (a job's stage, a take finishing, a
project saved elsewhere) is published here; nothing is polled.

Windows listen over a WebSocket (/api/live). An event stream (SSE, /api/events) is kept for
tools and tests, but browsers use the socket: a long-lived SSE request holds one of the six
connections a browser allows per site over HTTP/1.1, and a few open tabs then starve the rest
of the page (audio stops loading, saves hang)."""

from __future__ import annotations

import asyncio
import json
from typing import Any


class Hub:
    def __init__(self) -> None:
        self.queues: set[asyncio.Queue[tuple[str, Any]]] = set()

    def publish(self, kind: str, data: Any) -> None:
        for q in list(self.queues):
            if q.qsize() < 500:  # a stalled window drops events instead of holding memory
                q.put_nowait((kind, data))

    def subscribe(self) -> asyncio.Queue[tuple[str, Any]]:
        q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self.queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.queues.discard(q)

    async def stream(self):
        """Server-Sent Events, for tools (curl, tests)."""
        q = self.subscribe()
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    kind, data = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"event: {kind}\ndata: {json.dumps(data)}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self.unsubscribe(q)
