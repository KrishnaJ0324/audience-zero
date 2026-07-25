"""Revision Service (§2.3 component 7).

Takes the weakest beat + the panel's critiques and rewrites ONE scene (never the
full episode). Structured output → RevisedScene.
"""
from __future__ import annotations

import re

from ..contracts import Beat, PersonaReport, RevisedScene
from ..providers.factory import Providers

_SPEAKER_RE = re.compile(r"(?m)^\s*([A-Z][A-Za-z .'-]{1,24}):")


class RevisionService:
    def __init__(self, providers: Providers) -> None:
        self.p = providers

    async def revise(
        self,
        beat: Beat,
        reports: list[PersonaReport],
        target_beat: int,
        mode: str = "weakest",
    ) -> RevisedScene:
        critiques = [
            r.verdict_text
            for r in reports
            if r.verdict_text and (r.skip_at_beat == target_beat or r.drop_reason)
        ]
        if not critiques:
            critiques = [r.verdict_text for r in reports if r.verdict_text][:3]
        if mode == "ending":
            # steer the rewrite toward a stronger closing hook (Cliffhanger
            # Optimizer): the mock/LLM reviser plants a cliffhanger when it sees
            # hook language in the critiques.
            critiques = [
                "The ending needs a stronger hook — no reason to press play on the next episode.",
                *critiques,
            ]
        speakers = list(dict.fromkeys(_SPEAKER_RE.findall(beat.text)))
        return await self.p.llm.revise(beat, critiques[:6], speakers)
