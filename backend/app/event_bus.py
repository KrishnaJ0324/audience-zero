"""Internal async pub/sub event bus (§2.3, component 10).

Decouples computation from UI theatrics: the orchestrator publishes events as
work completes; SSE subscribers replay history + live tail. A late subscriber
(dashboard connects after a cached run finished) still receives the full
history first, then any live events — this is what makes cached replay look
identical to a live run, and lets the *revise* / *audio* events that arrive
after ``run_complete`` still reach the open stream.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict

from .events import Event


class EventBus:
    def __init__(self) -> None:
        self._history: dict[str, list[Event]] = defaultdict(list)
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, event: Event) -> None:
        async with self._lock:
            self._history[event.run_id].append(event)
            subs = list(self._subscribers.get(event.run_id, set()))
        for q in subs:
            await q.put(event)

    async def subscribe(self, run_id: str) -> "asyncio.Queue[Event]":
        q: asyncio.Queue[Event] = asyncio.Queue()
        async with self._lock:
            for past in self._history.get(run_id, []):
                await q.put(past)
            self._subscribers[run_id].add(q)
        return q

    async def unsubscribe(self, run_id: str, q: "asyncio.Queue[Event]") -> None:
        async with self._lock:
            self._subscribers.get(run_id, set()).discard(q)

    def history(self, run_id: str) -> list[Event]:
        return list(self._history.get(run_id, []))


# module-level singleton
bus = EventBus()
