"""
Phase 2 Engine — Behavioral Baselines & Deviation Signals

Implements source‑agnostic Phase 2 logic and Git reference metrics.
Consumes immutable Phase 1 events only.
"""

from pathlib import Path
import json
from collections import defaultdict, deque
from statistics import mean, pstdev
import math

class Phase2Engine:
    def __init__(self, evo_dir: Path, window_size: int = 50, min_baseline: int = 3):
        self.evo_dir = evo_dir
        self.events_path = evo_dir / "events"
        self.output_path = evo_dir / "phase2"
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.window_size = window_size
        self.min_baseline = min_baseline

    def _load_events(self):
        events = []
        for p in sorted(self.events_path.glob("*.json")):
            with open(p, "r", encoding="utf-8") as f:
                events.append(json.load(f))
        return events

    # ---------- Git Metrics ----------

    def _files_touched(self, event):
        return len(event["payload"].get("files", []))

    def _dispersion(self, event):
        files = event["payload"].get("files", [])
        if not files:
            return 0.0
        buckets = defaultdict(int)
        for f in files:
            parts = Path(f).parts
            top = parts[0] if parts else "_root"
            buckets[top] += 1
        total = sum(buckets.values())
        entropy = 0.0
        for count in buckets.values():
            p = count / total
            entropy -= p * math.log2(p)
        return entropy

    # ---------- Phase 2 Execution ----------

    def run_git(self):
        events = [e for e in self._load_events() if e.get("source_type") == "git"]
        window = deque(maxlen=self.window_size)
        signals = []

        for e in events:
            ft = self._files_touched(e)
            disp = self._dispersion(e)

            # compute baseline from PRIOR history only
            if len(window) >= self.min_baseline:
                fts = [x[0] for x in window]
                disps = [x[1] for x in window]

                baseline = {
                    "files_touched": {
                        "mean": mean(fts),
                        "stddev": pstdev(fts) if len(fts) > 1 else 0.0,
                    },
                    "dispersion": {
                        "mean": mean(disps),
                        "stddev": pstdev(disps) if len(disps) > 1 else 0.0,
                    },
                }

                signal = {
                    "engine": "git",
                    "event_ref": e["event_id"],
                    "metrics": {
                        "files_touched": {
                            "observed": ft,
                            "baseline": baseline["files_touched"],
                            "deviation": (ft - baseline["files_touched"]["mean"]) / (baseline["files_touched"]["stddev"] or 1.0),
                        },
                        "dispersion": {
                            "observed": disp,
                            "baseline": baseline["dispersion"],
                            "deviation": (disp - baseline["dispersion"]["mean"]) / (baseline["dispersion"]["stddev"] or 1.0),
                        },
                    },
                    "confidence": {
                        "sample_count": len(window),
                        "status": "sufficient" if len(window) >= self.window_size else "accumulating",
                    },
                }

                signals.append(signal)

            # AFTER evaluation, extend baseline window
            window.append((ft, disp))

        out_file = self.output_path / "git_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)

        return signals
