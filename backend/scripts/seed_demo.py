"""Pre-cache the rehearsed golden-path run (§2.8 demo-safety strategy).

Runs the demo episode through panel -> revise -> re-run and persists everything to
the SQLite store with all TTS assets pre-generated. On stage the cached run
replays instantly and deterministically while looking identical to a live run;
if wifi dies the entire golden path still works from cache + local audio.

Usage (from backend/):  ../venv/Scripts/python.exe scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402


async def main() -> None:
    s = get_settings()
    s.provider = "mock"  # cached path is always deterministic & offline
    s.reveal_delay_s = 0.0
    pipe = Pipeline(settings=s)
    await pipe.init()

    script_path = s.scripts_dir / "demo_episode.txt"
    text = script_path.read_text(encoding="utf-8")

    print("-> ingesting demo episode…")
    ep = await pipe.ingest_script("Audience Zero — Demo Episode", text)
    run_id = pipe.new_run_id()

    print("-> running panel (6 personas)…")
    run = await pipe.run_panel(ep, run_id)
    print(f"   {run.verdict.headline}")

    print("-> revising weakest beat + producing audio…")
    await pipe.revise_run(run_id)

    print("-> re-running for before/after…")
    child, cmp = await pipe.rerun_with_fix(run_id)
    print(f"   lift: +{cmp.lift_pct:.0f} pts at beat {cmp.beat_index + 1}")

    print("\n[OK] Cached demo seeded.")
    print(f"   parent run: {run_id}")
    print(f"   child run:  {child.id}")
    print(f"   db:         {s.db_path}")
    print(f"   audio dir:  {s.audio_dir}")


if __name__ == "__main__":
    asyncio.run(main())
