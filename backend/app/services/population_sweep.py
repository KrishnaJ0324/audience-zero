"""Population Sweep (§2.10, STRETCH).

Extrapolates from the 6 deeply-calibrated archetypes to a *crowd* of sampled
listeners — answering the P5 "thousands of AI users react to a story" framing —
and reports where that crowd drops off as a histogram.

Deterministic by design: each sampled listener is one archetype with its taste
knobs jittered by a stable hash of (archetype_id, sample_index). No randomness,
no live model calls — so the histogram is reproducible and instant, and the
golden path never depends on it. (A real-LLM sweep would be ~200 gpt-4o-mini
calls; that's a config swap, not a rewrite, but off by default to avoid
surprise cost.)
"""
from __future__ import annotations

from ..contracts import Episode, PersonaConfig, PopulationSweep
from ..providers import heuristics


def _jitter(archetype_id: str, sample_idx: int, key: str, spread: float) -> float:
    """Deterministic signed jitter in [-spread, +spread] from a stable hash."""
    h = heuristics.stable_seed(archetype_id, str(sample_idx), key)
    unit = (h % 10_000) / 10_000.0  # 0..1
    return (unit * 2 - 1) * spread


def _sample_listener(base: PersonaConfig, idx: int) -> PersonaConfig:
    weights = dict(base.weights or {})
    for k, v in weights.items():
        # jitter each taste knob by up to ±35% of its magnitude
        weights[k] = v * (1 + _jitter(base.id, idx, k, 0.35))
    thr = int(base.skip_threshold + _jitter(base.id, idx, "skip_threshold", 0.18) * 40)
    return base.model_copy(update={
        "id": f"{base.id}_s{idx}",
        "weights": weights,
        "skip_threshold": max(10, min(90, thr)),
    })


def sweep(episode: Episode, personas: list[PersonaConfig], n: int = 200) -> PopulationSweep:
    beats = episode.beats
    n_beats = len(beats)
    drop_hist = [0] * n_beats
    completed = 0
    archetype_drop_sum: dict[str, float] = {p.id: 0.0 for p in personas}
    archetype_count: dict[str, int] = {p.id: 0 for p in personas}

    # distribute the sample across archetypes proportional to audience weight
    total_w = sum(max(p.audience_weight, 0.0) for p in personas) or 1.0
    quotas = [max(1, round(n * max(p.audience_weight, 0.0) / total_w)) for p in personas]

    idx = 0
    for base, quota in zip(personas, quotas):
        for s in range(quota):
            listener = _sample_listener(base, s)
            report = heuristics.make_report(listener, episode, beats)
            if report.skip_at_beat is None:
                completed += 1
                archetype_drop_sum[base.id] += n_beats  # "finished" == end
            else:
                drop_hist[report.skip_at_beat] += 1
                archetype_drop_sum[base.id] += report.skip_at_beat
            archetype_count[base.id] += 1
            idx += 1

    total = idx
    modal = max(range(n_beats), key=lambda i: drop_hist[i]) if n_beats else 0
    per_archetype = {
        pid: round(archetype_drop_sum[pid] / archetype_count[pid], 2)
        for pid in archetype_drop_sum
        if archetype_count[pid]
    }
    return PopulationSweep(
        episode_id=episode.id,
        n=total,
        n_beats=n_beats,
        drop_histogram=drop_hist,
        completed=completed,
        modal_drop_beat=modal,
        completion_rate=round(completed / total, 3) if total else 0.0,
        per_archetype=per_archetype,
    )
