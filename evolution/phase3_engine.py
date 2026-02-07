"""
Phase 3 Engine — Deterministic Explanation Layer (Minimal)

Implements Phase 3 baseline:
- One explanation per Phase 2 signal
- Template-based, deterministic rendering
- No aggregation, no judgment, no recommendations

Conforms to PHASE_3_CONTRACT.md and PHASE_3_DESIGN.md.
"""

from pathlib import Path
import json
import hashlib
from datetime import datetime

class Phase3Engine:
    def __init__(self, evo_dir: Path):
        self.evo_dir = evo_dir
        self.phase2_path = evo_dir / "phase2" / "git_signals.json"
        self.output_path = evo_dir / "phase3"
        self.output_path.mkdir(parents=True, exist_ok=True)

    # ---------- Templates ----------

    def _template(self, signal: dict) -> str:
        metric = signal["metric"]
        observed = signal["observed"]
        mean = signal["baseline"]["mean"]
        std = signal["baseline"]["stddev"]
        window = signal["window"]["size"]
        conf = signal["confidence"]["status"]

        if metric == "files_touched":
            base = (
                f"This change touched {observed} files. "
                f"Over the last {window} changes, similar changes typically touched "
                f"{mean:.2f} ± {std:.2f} files."
            )
        elif metric == "dispersion":
            base = (
                f"This change had a dispersion value of {observed:.2f}. "
                f"Recent changes typically had a dispersion of "
                f"{mean:.2f} ± {std:.2f}."
            )
        elif metric == "change_locality":
            base = (
                f"The change locality for this commit was {observed:.2f}. "
                f"Recent changes typically had a locality of "
                f"{mean:.2f} ± {std:.2f}."
            )
        elif metric == "cochange_novelty_ratio":
            base = (
                f"The co-change novelty ratio for this change was {observed:.2f}. "
                f"Historically, similar changes had a novelty ratio of "
                f"{mean:.2f} ± {std:.2f}."
            )
        else:
            base = (
                f"Metric '{metric}' had a value of {observed}. "
                f"Baseline was {mean:.2f} ± {std:.2f}."
            )

        if conf != "sufficient":
            base += " This comparison is based on limited history and may change as more data becomes available."

        return base

    def _hash(self, data: dict) -> str:
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    # ---------- Execution ----------

    def run(self):
        if not self.phase2_path.exists():
            raise FileNotFoundError("Phase 2 signals not found")

        with open(self.phase2_path, "r", encoding="utf-8") as f:
            signals = json.load(f)

        explanations = []

        for signal in signals:
            explanation = {
                "engine_id": signal["engine_id"],
                "source_type": signal["source_type"],
                "signal_ref": signal.get("event_ref"),
                "summary": self._template(signal),
                "details": {
                    "metric": signal["metric"],
                    "observed": signal["observed"],
                    "baseline": signal["baseline"],
                    "deviation": signal["deviation"],
                },
                "confidence": signal["confidence"],
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }

            explanation_id = self._hash(explanation)
            explanation["explanation_id"] = explanation_id

            explanations.append(explanation)

        out_file = self.output_path / "explanations.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(explanations, f, indent=2)

        return explanations
