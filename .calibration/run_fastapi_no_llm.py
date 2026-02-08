"""
Calibration Run: fastapi (retry without Phase 3.1 LLM)

Runs the full pipeline (Phase 1-5) on the fastapi repository.
Phase 3.1 disabled to avoid LLM API issues during autonomous run.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Disable Phase 3.1 LLM enhancement for this run
os.environ["PHASE31_ENABLED"] = "false"

from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.phase3_engine import Phase3Engine
from evolution.phase4_engine import Phase4Engine
from evolution.phase5_engine import Phase5Engine
from evolution.adapters.git import GitSourceAdapter

REPO_NAME = "fastapi"
REPO_PATH = Path(__file__).parent / "repos" / REPO_NAME
RUN_DIR = Path(__file__).parent / "runs" / REPO_NAME

print(f"Calibration: {REPO_NAME} (Phase 3.1 disabled)")
print(f"Repository: {REPO_PATH}")
print(f"Output: {RUN_DIR}")
print("=" * 60)

# Phase 1: Already complete, skip if events exist
events_exist = (RUN_DIR / "events").exists() and len(list((RUN_DIR / "events").glob("*.json"))) > 0
if events_exist:
    print("\n[Phase 1] Skipping (already complete)")
    print(f"✓ {len(list((RUN_DIR / 'events').glob('*.json')))} git events exist")
else:
    print("\n[Phase 1] Ingesting git events...")
    phase1 = Phase1Engine(RUN_DIR)
    git_adapter = GitSourceAdapter(str(REPO_PATH))
    git_count = phase1.ingest(git_adapter)
    print(f"✓ Ingested {git_count} git events")

# Phase 2: Compute baselines and signals
print("\n[Phase 2] Computing baselines and signals...")
phase2 = Phase2Engine(RUN_DIR, min_baseline=10)
git_signals = phase2.run_git()
print(f"✓ {len(git_signals)} git signals")

# Phase 3: Generate explanations (without LLM enhancement)
print("\n[Phase 3] Generating explanations (baseline, no LLM)...")
phase3 = Phase3Engine(RUN_DIR)
explanations = phase3.run()
print(f"✓ {len(explanations)} explanations")

# Phase 4: Discover patterns (adjusted params for larger repo)
print("\n[Phase 4] Discovering patterns...")
os.environ["PHASE4B_ENABLED"] = "false"  # Also disable Phase 4b LLM for this run
phase4 = Phase4Engine(RUN_DIR, params={
    "min_support": 5,
    "min_correlation": 0.5,
    "promotion_threshold": 15,
    "direction_threshold": 1.0,
})
p4_result = phase4.run()
print(f"✓ {p4_result['patterns_discovered']} patterns discovered")
print(f"  - Knowledge artifacts: {p4_result['knowledge_artifacts']}")

# Phase 5: Generate advisory
print("\n[Phase 5] Generating advisory...")
phase5 = Phase5Engine(RUN_DIR, significance_threshold=1.5)
p5_result = phase5.run(scope=REPO_NAME)
print(f"✓ Status: {p5_result['status']}")
if p5_result.get('advisory'):
    summary = p5_result['advisory']['summary']
    print(f"  - Significant changes: {summary['significant_changes']}")
    print(f"  - Families affected: {', '.join(summary['families_affected'])}")
    print(f"  - Pattern matches: {summary['known_patterns_matched']}")

phase4.close()

print("\n" + "=" * 60)
print("Pipeline complete!")
