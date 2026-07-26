"""Deterministic persona-judgment heuristics.

Powers the offline ``mock`` LLM. The goal is *genuinely divergent judgment
distributions* between personas (the #1 product risk per §2.6) without any
network call — so the whole golden path is demoable with zero API keys, and the
divergence acceptance test is meaningful.

Each persona carries a ``weights`` dict (taste knobs, loaded from YAML). We
extract length-invariant features per beat, combine them with the persona's
weights, and clamp to an integer engagement in [0, 100]. Same input => same
output, always.
"""
from __future__ import annotations

import hashlib
import re

from ..contracts import (
    Beat,
    BeatScore,
    CharacterProfile,
    CharacterState,
    ConsistencyIssue,
    Episode,
    MemorySpec,
    PersonaConfig,
    PersonaReport,
)

# --------------------------------------------------------------------------- #
# Lexicons (deliberately small & explicit — this is a heuristic, not an NLP)
# --------------------------------------------------------------------------- #
RECAP = ["previously", "as you know", "as you recall", "remember when", "recap",
         "last time", "earlier we", "to remind", "if you recall", "back then",
         "let me explain again", "as i said", "once again"]
TENSION = ["suddenly", "gun", "blood", "scream", "danger", "kill", "threat",
           "shadow", "footsteps", "knife", "chase", "trapped", "silence",
           "heartbeat", "gasp", "darkness", "warning", "betray"]
ROMANCE = ["love", "kiss", "heart", "embrace", "whisper", "tender", "longing",
           "touch", "blush", "gaze", "together", "promise", "hold"]
TROPE = ["little did they know", "it was a dark and stormy", "plot twist",
         "chosen one", "long lost twin", "it was all a dream", "amnesia",
         "evil twin", "suddenly a ninja", "deus ex", "as luck would have it"]
PAYOFF = ["finally", "at last", "revealed", "truth", "confession", "reunion",
          "payoff", "answer", "resolved", "victory", "confessed"]
HOOK = ["cliffhanger", "to be continued", "who was", "what happens next",
        "she opened the door", "the phone rang", "one message", "but then",
        "unknown number", "don't hang up"]

_SPEAKER_RE = re.compile(r"(?m)^\s*([A-Z][A-Za-z .'-]{1,24}):")
_WORD_RE = re.compile(r"[a-z']+")


def _density(text_lower: str, terms: list[str], nwords: int) -> float:
    hits = sum(text_lower.count(t) for t in terms)
    return (hits / nwords) * 100.0


def extract_features(beat: Beat, is_final: bool) -> dict[str, float]:
    text = beat.text or beat.summary
    tl = text.lower()
    nwords = max(len(_WORD_RE.findall(tl)), 1)
    speakers = set(_SPEAKER_RE.findall(text))
    num_chars = len(speakers)
    ends_hook = tl.rstrip().endswith("?") or any(h in tl for h in HOOK)
    return {
        "recap": _density(tl, RECAP, nwords),
        "tension": _density(tl, TENSION, nwords),
        "romance": _density(tl, ROMANCE, nwords),
        "trope": _density(tl, TROPE, nwords),
        "payoff": _density(tl, PAYOFF, nwords),
        "hook": (_density(tl, HOOK, nwords) + (6.0 if ends_hook else 0.0)),
        "num_chars": float(num_chars),
        "length": float(nwords),
        "is_final": 1.0 if is_final else 0.0,
        # salience: is anything actually happening here?
        "salience": _density(tl, TENSION + ROMANCE + PAYOFF, nwords),
    }


DEFAULT_WEIGHTS: dict[str, float] = {
    "base": 62.0,
    "recap_penalty": 3.0,
    "tension_reward": 2.0,
    "romance_reward": 2.0,
    "payoff_reward": 2.0,
    "hook_reward": 1.5,
    "trope_penalty": 3.0,
    "char_threshold": 3.0,
    "char_penalty": 4.0,
    "boredom_penalty": 3.0,       # applied when salience is near zero
    "long_penalty": 0.0,          # per 100 words over 120
    "final_focus": 0.0,           # 0..1: how much this persona ignores non-final beats
    "final_hook_reward": 0.0,     # extra boost on the final beat's hook
    "impatience_decay": 0.0,      # engagement bleeds down over the episode
}


def _clamp(x: float) -> int:
    return int(max(0, min(100, round(x))))


def score_beat(persona: PersonaConfig, feat: dict[str, float], position: float) -> int:
    """position: 0.0 (first beat) .. 1.0 (last beat)."""
    w = {**DEFAULT_WEIGHTS, **(persona.weights or {})}
    e = w["base"]
    e -= w["recap_penalty"] * feat["recap"]
    e += w["tension_reward"] * feat["tension"]
    e += w["romance_reward"] * feat["romance"]
    e += w["payoff_reward"] * feat["payoff"]
    e += w["hook_reward"] * feat["hook"]
    e -= w["trope_penalty"] * feat["trope"]

    over = feat["num_chars"] - w["char_threshold"]
    if over > 0:
        e -= w["char_penalty"] * over

    if feat["salience"] < 1.0:
        e -= w["boredom_penalty"] * 3.0

    if w["long_penalty"] and feat["length"] > 120:
        e -= w["long_penalty"] * ((feat["length"] - 120) / 100.0)

    # impatience: later beats erode for low-patience personas
    e -= w["impatience_decay"] * position * 20.0

    # cliffhanger addict: compress non-final beats toward a flat mid, then let
    # the final beat's hook dominate.
    if w["final_focus"] > 0:
        if feat["is_final"] < 1.0:
            e = 50.0 + (e - 50.0) * (1.0 - w["final_focus"])
        else:
            e += w["final_hook_reward"] * feat["hook"]

    return _clamp(e)


# --------------------------------------------------------------------------- #
# Verdict phrasing (persona voice) — templated, deterministic
# --------------------------------------------------------------------------- #

def _dominant_complaint(feat: dict[str, float]) -> str:
    signals = {
        "recap": feat["recap"] * 3.0,
        "boredom": (5.0 if feat["salience"] < 1.0 else 0.0),
        "crowded": max(0.0, feat["num_chars"] - 3.0) * 2.0,
        "trope": feat["trope"] * 3.0,
        "no_hook": 3.0 - min(feat["hook"], 3.0),
    }
    return max(signals, key=signals.get)


_VOICE = {
    "recap": {
        "arjun": "Too much recap — I'd skip here.",
        "dev": "It's just re-explaining stuff I already got. I tuned out.",
        "default": "The recap stalls the momentum; I drifted here.",
    },
    "boredom": {
        "meera": "Nothing's breathing here — even I wanted the story to move.",
        "kavya": "Dead air. No tension is being built, so nothing pays off.",
        "default": "This beat is inert — nothing happens, so I checked out.",
    },
    "crowded": {
        "dev": "Too many voices at once — I lost the thread completely.",
        "default": "Crowded beat; I couldn't track who mattered.",
    },
    "trope": {
        "ananya": "I've heard this exact beat a hundred times. Cliché — audiences will roll their eyes.",
        "kavya": "Unearned twist. The mechanics don't hold, so it lands hollow.",
        "default": "Feels derivative here; the cliché deflates it.",
    },
    "no_hook": {
        "ravi": "No hook to carry me forward. I need a reason to hit next episode.",
        "default": "There's no pull into the next beat; the tension leaks out.",
    },
}

_PRAISE = {
    "meera": "The relationship work here is gorgeous — I'd binge straight through.",
    "kavya": "Clean tension mechanics. The screws turn and the payoff is earned.",
    "arjun": "Tight and moving — this earned my next 90 seconds.",
    "dev": "Clear and easy to follow even with half my attention. Nice.",
    "ananya": "Fresh angle — this sidesteps the obvious trope. Rare.",
    "ravi": "That final hook is a knife to the ribs. I'm not going anywhere.",
}


def _voice_line(persona_id: str, complaint: str) -> str:
    table = _VOICE.get(complaint, {})
    return table.get(persona_id, table.get("default", "This beat lost me."))


def make_report(persona: PersonaConfig, episode: Episode, beats: list[Beat]) -> PersonaReport:
    n = len(beats)
    scores: list[BeatScore] = []
    feats: list[dict[str, float]] = []
    for i, b in enumerate(beats):
        position = i / max(n - 1, 1)
        feat = extract_features(b, is_final=(i == n - 1))
        feats.append(feat)
        scores.append(BeatScore(beat_index=b.index, engagement=score_beat(persona, feat, position)))

    # skip point: first beat that falls below this persona's tolerance.
    skip_at: int | None = None
    for s in scores:
        if s.engagement < persona.skip_threshold:
            skip_at = s.beat_index
            break

    # weakest beat from this persona's own eyes (drives the critique voice)
    weakest = min(scores, key=lambda s: s.engagement)
    complaint = _dominant_complaint(feats[[b.index for b in beats].index(weakest.beat_index)])
    focus_idx = skip_at if skip_at is not None else weakest.beat_index

    mean_eng = sum(s.engagement for s in scores) / len(scores)
    if mean_eng >= 68 and skip_at is None:
        verdict = _PRAISE.get(persona.id, "Solid — this held me.")
        drop_reason = ""
    else:
        verdict = _voice_line(persona.id, complaint)
        drop_reason = complaint

    # confidence: stable per persona (Ananya is loud), nudged by score variance
    conf = float(persona.weights.get("confidence", 0.6)) if persona.weights else 0.6
    conf = max(0.3, min(0.95, conf))

    return PersonaReport(
        persona_id=persona.id,
        scores=scores,
        skip_at_beat=focus_idx if (skip_at is not None or mean_eng < 68) else None,
        drop_reason=drop_reason,
        verdict_text=verdict,
        confidence=round(conf, 2),
    )


def stable_seed(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16)


# --------------------------------------------------------------------------- #
# Story-tree heuristics: character-state folding + coarse consistency checks.
# Deterministic, no network — same input => same output, same philosophy as
# the persona-scoring heuristics above. Explicitly an approximation, not
# semantic understanding.
# --------------------------------------------------------------------------- #

# Antonym-ish cue pairs: if a character's established memory/relationships
# mention one side and a new branch's text contains the other, that's a coarse
# signal of a contradiction worth surfacing (never blocking).
_ANTONYM_PAIRS: list[tuple[str, str]] = [
    ("trust", "betray"), ("protect", "abandon"), ("love", "hate"),
    ("truth", "lie"), ("together", "alone"), ("ally", "enemy"),
    ("forgive", "resent"), ("loyal", "traitor"), ("alive", "dead"),
]

_MEMORY_CAP = 8


def speakers_in(text: str) -> list[str]:
    """Dialogue speakers in a beat/scene, in first-appearance order, NARRATOR
    excluded (it's not a character with state)."""
    found = [s.strip() for s in _SPEAKER_RE.findall(text or "")]
    return list(dict.fromkeys(s for s in found if s and s.upper() != "NARRATOR"))


def _dominant_emotion(text_lower: str) -> str:
    nwords = max(len(_WORD_RE.findall(text_lower)), 1)
    candidates = {
        "tense": _density(text_lower, TENSION, nwords),
        "tender": _density(text_lower, ROMANCE, nwords),
        "relieved": _density(text_lower, PAYOFF, nwords),
    }
    best = max(candidates, key=candidates.get)
    return best if candidates[best] > 0 else "neutral"


def fold_character_state(
    prior: dict[str, CharacterState], beat_text: str
) -> dict[str, CharacterState]:
    """Fold one beat/scene of text into cumulative character state. NEVER
    mutates ``prior`` — always returns fresh CharacterState copies, which is
    the concrete mechanism behind the copy-on-write guarantee (branches must
    never share mutable state)."""
    out = {k: v.model_copy(deep=True) for k, v in prior.items()}
    text = beat_text or ""
    present = speakers_in(text)
    if not present:
        return out
    tl = text.lower()
    emotion = _dominant_emotion(tl)
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    memory_line = (first_line[:140] + "…") if len(first_line) > 140 else first_line
    for name in present:
        cs = (out.get(name) or CharacterState(name=name)).model_copy(deep=True)
        if memory_line:
            cs.memory = ([*cs.memory, memory_line])[-_MEMORY_CAP:]
        cs.emotional_state = emotion
        for other in present:
            if other == name:
                continue
            if emotion == "tense":
                tag = "tense"
            elif emotion in ("tender", "relieved"):
                tag = "ally"
            else:
                tag = cs.relationships.get(other, "acquainted")
            cs.relationships[other] = tag
        out[name] = cs
    return out


_THEME_LABELS = {
    "romance": "romance / relationship drama",
    "tense": "thriller / tension",
    "relieved": "mystery with a payoff-driven arc",
}


def infer_theme(text: str) -> str:
    tl = (text or "").lower()
    nwords = max(len(_WORD_RE.findall(tl)), 1)
    scores = {
        "romance": _density(tl, ROMANCE, nwords),
        "tense": _density(tl, TENSION, nwords),
        "relieved": _density(tl, PAYOFF, nwords),
    }
    best = max(scores, key=scores.get)
    return _THEME_LABELS[best] if scores[best] > 0 else "character drama"


def build_memory_spec(
    parent_spec: MemorySpec | None,
    episode_text: str,
    prior_states: dict[str, CharacterState],
) -> MemorySpec:
    """Deterministic story-bible builder (theme + character roles/behavior +
    cross-cutting constraints) — an approximation, not literary analysis,
    matching the mock philosophy elsewhere in this app. Never mutates
    ``parent_spec``; always builds a fresh spec for the caller to attach."""
    theme = parent_spec.theme if parent_spec and parent_spec.theme else infer_theme(episode_text)

    chars_by_name: dict[str, CharacterProfile] = {
        c.name: c for c in (parent_spec.characters if parent_spec else [])
    }
    for name in speakers_in(episode_text):
        cs = prior_states.get(name)
        prior = chars_by_name.get(name)
        role = (prior.role if prior and prior.role else "") or (
            "lead" if len(chars_by_name) < 2 else "supporting"
        )
        notes = (cs.emotional_state if cs else "") or (prior.behavior_notes if prior else "") or "steady"
        chars_by_name[name] = CharacterProfile(name=name, role=role, behavior_notes=notes)

    constraints = list(parent_spec.constraints) if parent_spec else []
    for name in speakers_in(episode_text):
        cs = prior_states.get(name)
        if not cs:
            continue
        for other, tag in cs.relationships.items():
            note = f"{name} & {other}: {tag}"
            if note not in constraints:
                constraints.append(note)

    return MemorySpec(
        theme=theme, characters=list(chars_by_name.values())[:12], constraints=constraints[:12],
    )


def check_consistency_heuristic(
    established: dict[str, CharacterState], new_text: str, new_states: dict[str, CharacterState]
) -> list[ConsistencyIssue]:
    """Coarse antonym-cue scan — an approximation, not semantic checking.
    Deterministic: same input => same output."""
    tl = (new_text or "").lower()
    issues: list[ConsistencyIssue] = []
    for name, cs in established.items():
        blob = " ".join(cs.memory).lower() + " " + " ".join(cs.relationships.values()).lower()
        for a, b in _ANTONYM_PAIRS:
            hit = None
            if a in blob and b in tl:
                hit = (a, b)
            elif b in blob and a in tl:
                hit = (b, a)
            if hit:
                was, now = hit
                issues.append(
                    ConsistencyIssue(
                        id=f"ci_{stable_seed(name, was, now):08x}",
                        severity="warning",
                        summary=f"{name} was established as '{was}' — this branch reads like '{now}'.",
                        conflicting_fact=was,
                        character=name,
                    )
                )
    return issues
