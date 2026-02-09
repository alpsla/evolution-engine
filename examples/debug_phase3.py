#!/usr/bin/env python
"""Debug Phase 3 performance."""
import sys, time, json, hashlib
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, ".")
from pathlib import Path
from datetime import datetime

evo_dir = Path(".calibration/runs/fastapi")

# Load signals
print("Loading signals...")
t0 = time.monotonic()
all_signals = []
p2 = evo_dir / "phase2"
for f in sorted(p2.glob("*.json")):
    with open(f) as fh:
        sigs = json.load(fh)
        print(f"  {f.name}: {len(sigs)}")
        all_signals.extend(sigs)
print(f"  Total: {len(all_signals)} in {time.monotonic()-t0:.2f}s")

# Import renderer
print("\nImporting Phase3.1 renderer...")
t0 = time.monotonic()
from evolution.phase3_1_renderer import Phase31Renderer
renderer = Phase31Renderer()
print(f"  Done in {time.monotonic()-t0:.2f}s, enabled={renderer.enabled}")

# Import phase3 engine for template
from evolution.phase3_engine import Phase3Engine
phase3 = Phase3Engine(evo_dir)

# Template all signals
print(f"\nTemplating {len(all_signals)} signals...")
t0 = time.monotonic()
explanations = []
errors = 0
for i, signal in enumerate(all_signals):
    try:
        summary = phase3._template(signal)
    except Exception as e:
        if errors < 3:
            print(f"  ERROR at signal {i}: {e}")
        errors += 1
        summary = f"Error: {e}"

    explanation = {
        "engine_id": signal["engine_id"],
        "source_type": signal["source_type"],
        "signal_ref": signal.get("event_ref"),
        "summary": summary,
        "details": {
            "metric": signal["metric"],
            "observed": signal["observed"],
            "baseline": signal["baseline"],
            "deviation": signal["deviation"],
        },
        "confidence": signal["confidence"],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    # Hash
    encoded = json.dumps(explanation, sort_keys=True, separators=(",", ":")).encode("utf-8")
    explanation["explanation_id"] = hashlib.sha256(encoded).hexdigest()

    # Render (should be no-op)
    explanation = renderer.render(explanation)

    explanations.append(explanation)

    if (i + 1) % 5000 == 0:
        elapsed = time.monotonic() - t0
        print(f"  {i+1}/{len(all_signals)} in {elapsed:.1f}s ({errors} errors)")

elapsed = time.monotonic() - t0
print(f"  Done: {len(explanations)} explanations in {elapsed:.1f}s ({errors} errors)")

# Write JSON
print(f"\nWriting JSON...")
t0 = time.monotonic()
out_file = evo_dir / "phase3" / "explanations.json"
out_file.parent.mkdir(parents=True, exist_ok=True)
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(explanations, f, indent=2)
fsize = out_file.stat().st_size
print(f"  Written {fsize/1024/1024:.1f}MB in {time.monotonic()-t0:.1f}s")
print("DONE")
