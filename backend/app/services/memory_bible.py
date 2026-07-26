"""Story Bible (memory.md) — pure rendering only.

Generation itself is an LLM call (``providers.LLMJudge.generate_memory``,
mock heuristic in ``providers/heuristics.py::build_memory_spec``); this module
just turns the resulting structured ``MemorySpec`` into the markdown text
attached to a Version. Deterministic, zero LLM calls — same split as the
Verdict Engine (LLMs judge/generate, deterministic code renders/decides).
"""
from __future__ import annotations

from ..contracts import MemorySpec


def render_markdown(spec: MemorySpec, title: str) -> str:
    lines = [f"# Story Bible — {title}", "", "## Theme", spec.theme or "(unspecified)", "", "## Characters"]
    if spec.characters:
        for c in spec.characters:
            heading = f"### {c.name}" + (f" — {c.role}" if c.role else "")
            lines.append(heading)
            lines.append(c.behavior_notes or "(no notes yet)")
            lines.append("")
    else:
        lines.append("(no characters yet)")
        lines.append("")
    lines.append("## Constraints")
    if spec.constraints:
        lines.extend(f"- {c}" for c in spec.constraints)
    else:
        lines.append("(none yet)")
    return "\n".join(lines)
