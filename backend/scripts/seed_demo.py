"""Pre-seed a demo Project -> Episode -> Version -> AnalysisRun (+ a revision
variant and a before/after re-run), with all TTS assets pre-generated.

On stage the cached run replays instantly and deterministically; if wifi dies
the whole golden path still works from cache + local audio. Also gives the v2
dashboard a populated project to open on load.

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

    text = (s.scripts_dir / "demo_episode.txt").read_text(encoding="utf-8")

    print("-> creating project + episode…")
    project = await pipe.create_project(
        "Nightshade — Season 1", "Serialized audio drama · daily-episode QA")
    episode = await pipe.create_episode(project.id, "Ep. 07 — The Third Floor")

    print("-> ingesting script as version v1…")
    version = await pipe.add_script_version(
        episode.title, text, project_id=project.id, episode_id=episode.id, label="v1")

    print("-> running the panel (6 personas)…")
    run = await pipe.run_panel(version, pipe.new_run_id())
    print(f"   {run.verdict.headline} · confidence {run.confidence.label} "
          f"· binge {run.verdict.binge_probability:.0%}")
    print(f"   {len(run.evidence_spans)} evidence spans · {len(run.diagnostics)} diagnostics")

    print("-> proposing a fix for the weakest beat + producing audio…")
    run = await pipe.revise_run(run.id, target="weakest")
    variant = run.revision_variants[-1]
    await pipe.set_variant_status(run.id, variant.id, "accepted")

    print("-> re-running the accepted variant for before/after…")
    child, cmp = await pipe.rerun_with_fix(run.id)
    print(f"   lift: +{cmp.lift_pct:.0f} pts at beat {cmp.beat_index + 1}")

    print("\n[OK] Seeded.")
    print(f"   project:    {project.id}")
    print(f"   episode:    {episode.id}")
    print(f"   version:    {version.id}")
    print(f"   parent run: {run.id}")
    print(f"   child run:  {child.id}")
    print(f"   db:         {s.db_path}")


if __name__ == "__main__":
    asyncio.run(main())
