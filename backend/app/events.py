"""Telemetry events emitted on the internal pub/sub bus and streamed to the UI
over SSE (§2.5). Computation is real; the progressive reveal is theatre (#4) —
these events carry already-computed results, we never claim real-time inference.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "run_started",
    "beats_ready",
    "agent_started",
    "beat_scored",
    "agent_done",
    "agent_failed",
    "verdict_ready",
    "revision_started",
    "revision_ready",
    "audio_ready",
    "run_complete",
    "error",
]


class Event(BaseModel):
    type: EventType
    run_id: str
    data: dict[str, Any] = Field(default_factory=dict)

    def sse(self) -> dict[str, str]:
        """Shape expected by sse-starlette's EventSourceResponse."""
        return {"event": self.type, "data": self.model_dump_json()}
