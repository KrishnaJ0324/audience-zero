"""Population Sweep tests (§2.10) — deterministic crowd extrapolation."""
from __future__ import annotations

import asyncio

from app.config import get_settings
from app.pipeline import Pipeline
from app.services import population_sweep


def _episode():
    async def _go():
        s = get_settings()
        s.provider = "mock"
        s.reveal_delay_s = 0.0
        p = Pipeline(settings=s)
        await p.init()
        text = (s.scripts_dir / "demo_episode.txt").read_text(encoding="utf-8")
        ep = await p.ingest_script("demo", text)
        return ep, p.registry.load()

    return asyncio.run(_go())


def test_histogram_accounts_for_every_listener():
    ep, personas = _episode()
    sweep = population_sweep.sweep(ep, personas, n=200)
    assert sum(sweep.drop_histogram) + sweep.completed == sweep.n
    assert sweep.n >= 190  # quota rounding stays close to requested n
    assert len(sweep.drop_histogram) == len(ep.beats)


def test_sweep_is_deterministic():
    ep, personas = _episode()
    a = population_sweep.sweep(ep, personas, n=150)
    b = population_sweep.sweep(ep, personas, n=150)
    assert a.model_dump() == b.model_dump()


def test_modal_drop_lands_on_a_real_weak_beat():
    ep, personas = _episode()
    sweep = population_sweep.sweep(ep, personas, n=200)
    # the crowd should bunch its drops on the planted recap beat (index 6)
    # or its immediate neighbours, not the strong opening/closing.
    assert 4 <= sweep.modal_drop_beat <= 8
    assert 0.0 <= sweep.completion_rate <= 1.0
