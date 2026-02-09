#!/usr/bin/env python
"""E2E re-run of Phases 2-5 with progress output."""
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# Default LLM off unless explicitly enabled via env var
if "PHASE31_ENABLED" not in os.environ:
    os.environ["PHASE31_ENABLED"] = "false"
if "PHASE4B_ENABLED" not in os.environ:
    os.environ["PHASE4B_ENABLED"] = "false"

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

evo_dir = Path(".calibration/runs/fastapi")
scope = "tiangolo/fastapi"
start = datetime.now()

print("=" * 70)
print(f"E2E Calibration Re-run (Phases 2-5): {scope}")
print(f"Started: {start.isoformat()}")
print("=" * 70)

events_dir = evo_dir / "events"
event_count = len(list(events_dir.glob("*.json")))
print(f"\n[Phase 1] Using {event_count} cached events")

# ── Phase 2 ──
print("\n[Phase 2] Computing baselines and deviation signals...")
from evolution.phase2_engine import Phase2Engine
t0 = time.monotonic()
phase2 = Phase2Engine(evo_dir, window_size=50, min_baseline=5)
signals = phase2.run_all()
signal_counts = {f: len(s) for f, s in signals.items() if s}
total_signals = sum(signal_counts.values())
print(f"  {total_signals} signals across {len(signal_counts)} families ({time.monotonic()-t0:.1f}s)")
for family, count in sorted(signal_counts.items()):
    print(f"    {family}: {count}")

# ── Phase 3 ──
print("\n[Phase 3] Generating explanations...")
from evolution.phase3_engine import Phase3Engine
t0 = time.monotonic()
phase3 = Phase3Engine(evo_dir)
explanations = phase3.run()
print(f"  {len(explanations)} explanations generated ({time.monotonic()-t0:.1f}s)")

# ── Phase 4 ──
print("\n[Phase 4] Discovering cross-family patterns...")
from evolution.phase4_engine import Phase4Engine
t0 = time.monotonic()
phase4 = Phase4Engine(evo_dir)
p4_result = phase4.run()
print(f"  Status: {p4_result['status']}")
print(f"  Total signals: {p4_result['total_signals']}")
print(f"  Deviating: {p4_result['deviating_signals']}")
print(f"  Patterns discovered: {p4_result['patterns_discovered']}")
print(f"  Patterns recognized: {p4_result['patterns_recognized']}")
print(f"  Patterns incremented: {p4_result['patterns_incremented']}")
print(f"  Knowledge artifacts: {p4_result['knowledge_artifacts']}")
print(f"  ({time.monotonic()-t0:.1f}s)")
if p4_result.get("details"):
    print("  Details:")
    for d in p4_result["details"]:
        print(f"    {d}")

# ── Phase 5 ──
print("\n[Phase 5] Generating advisory report...")
from evolution.phase5_engine import Phase5Engine
t0 = time.monotonic()
phase5 = Phase5Engine(evo_dir)
advisory_result = phase5.run(scope=scope)

if advisory_result["status"] == "complete":
    advisory = advisory_result["advisory"]
    print(f"  Significant changes: {advisory['summary']['significant_changes']}")
    print(f"  Families affected: {advisory['summary']['families_affected']}")
    print(f"  Pattern matches: {advisory['summary']['known_patterns_matched']}")
    print(f"  Candidate patterns: {advisory['summary'].get('candidate_patterns_matched', 0)}")
    print(f"  Event groups: {advisory['summary'].get('event_groups', 'n/a')}")
    print(f"  ({time.monotonic()-t0:.1f}s)")
    print(f"\n  Outputs:")
    for fmt, path in advisory_result.get("formats", {}).items():
        print(f"    {fmt}: {path}")
else:
    print(f"  Status: {advisory_result['status']}")

elapsed = (datetime.now() - start).total_seconds()
print("\n" + "=" * 70)
print(f"Calibration complete: {scope}")
print(f"  Events: {event_count} | Signals: {total_signals} | Time: {elapsed:.1f}s")
print("=" * 70)
