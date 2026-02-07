"""
Phase 2 Engine — Behavioral Baselines & Deviation Signals

Complete Git reference implementation.
Emits canonical Phase 2 signals:
- files_touched
- dispersion
- cochange_novelty_ratio
- change_locality

Conforms to PHASE_2_CONTRACT.md and PHASE_2_DESIGN.md.
"""

from pathlib import Path
import json
from collections import defaultdict, deque
from statistics import mean, pstdev
import math

class Phase2Engine:
    def __init__(self, evo_dir: Path, window_size: int = 50, min_baseline: int = 5):
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

    # ---------- Metric helpers ----------

    def _files_touched(self, event):
        return set(event["payload"].get("files", []))

    def _dispersion(self, files):
        if not files:
            return 0.0
        buckets = defaultdict(int)
        for f in files:
            top = Path(f).parts[0] if Path(f).parts else "_root"
            buckets[top] += 1
        total = sum(buckets.values())
        entropy = 0.0
        for count in buckets.values():
            p = count / total
            entropy -= p * math.log2(p)
        return entropy

    def _cochange_pairs(self, files):
        pairs = set()
        fl = sorted(files)
        for i in range(len(fl)):
            for j in range(i + 1, len(fl)):
                pairs.add((fl[i], fl[j]))
        return pairs

    # ---------- Phase 2 execution ----------

    def run_git(self):
        events = [e for e in self._load_events() if e.get("source_type") == "git"]
        window = deque(maxlen=self.window_size)
        signals = []

        for e in events:
            files = self._files_touched(e)
            metrics = {
                "files_touched": len(files),
                "dispersion": self._dispersion(files),
            }

            # --- additional metrics ---
            current_pairs = self._cochange_pairs(files)
            recent_files = set().union(*(w["files"] for w in window)) if window else set()
            locality = len(files & recent_files) / len(files) if files else 0.0

            metrics["change_locality"] = locality
            metrics["cochange_novelty_ratio"] = 1.0  # default

            if window:
                historical_pairs = set().union(*(w["pairs"] for w in window))
                if current_pairs:
                    unseen = current_pairs - historical_pairs
                    metrics["cochange_novelty_ratio"] = len(unseen) / len(current_pairs)

            if len(window) >= self.min_baseline:
                for metric, observed in metrics.items():
                    history = [w["metrics"][metric] for w in window]
                    baseline_mean = mean(history)
                    baseline_std = pstdev(history) if len(history) > 1 else 0.0

                    signal = {
                        "engine_id": "git",
                        "source_type": "git",
                        "metric": metric,
                        "window": {"type": "rolling", "size": self.window_size},
                        "baseline": {"mean": baseline_mean, "stddev": baseline_std},
                        "observed": observed,
                        "deviation": {
                            "measure": (observed - baseline_mean) / (baseline_std or 1.0),
                            "unit": "stddev_from_mean",
                        },
                        "confidence": {
                            "sample_count": len(window),
                            "status": "sufficient" if len(window) >= self.window_size else "accumulating",
                        },
                        "event_ref": e["event_id"],
                    }
                    signals.append(signal)

            window.append({
                "files": files,
                "pairs": current_pairs,
                "metrics": metrics,
            })

        out_file = self.output_path / "git_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)

        return signals
