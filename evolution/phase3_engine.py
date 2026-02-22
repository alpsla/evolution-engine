"""
Phase 3 Engine — Deterministic Explanation Layer

- One explanation per Phase 2 signal (any family)
- Template-based, deterministic rendering with PM-friendly language
- No aggregation, no judgment, no recommendations

Conforms to PHASE_3_CONTRACT.md and PHASE_3_DESIGN.md.
"""

from pathlib import Path
import json
import hashlib
from datetime import datetime

from evolution.friendly import relative_change, metric_insight

# All Phase 2 signal files, keyed by family
SIGNAL_FILES = {
    "git": "git_signals.json",
    "ci": "ci_signals.json",
    "testing": "testing_signals.json",
    "coverage": "coverage_signals.json",
    "dependency": "dependency_signals.json",
    "schema": "schema_signals.json",
    "deployment": "deployment_signals.json",
    "config": "config_signals.json",
    "security": "security_signals.json",
    "error_tracking": "error_tracking_signals.json",
}


class Phase3Engine:
    def __init__(self, evo_dir: Path):
        self.evo_dir = evo_dir
        self.phase2_path = evo_dir / "phase2"
        self.output_path = evo_dir / "phase3"
        self.output_path.mkdir(parents=True, exist_ok=True)

    # ---------- Templates ----------

    def _get_median(self, signal: dict) -> float:
        """Get the best available central tendency from a signal's baseline."""
        baseline = signal["baseline"]
        med = baseline.get("median")
        if med is not None and baseline.get("mad") is not None and baseline["mad"] > 0:
            return med
        return baseline["mean"]

    def _direction(self, signal: dict) -> str:
        """Return 'up' or 'down' based on observed vs baseline."""
        observed = signal["observed"]
        median = self._get_median(signal)
        if median is None or median == 0:
            return "up" if observed > 0 else "down"
        return "up" if observed >= median else "down"

    def _template(self, signal: dict) -> str:
        metric = signal["metric"]
        observed = signal["observed"]
        baseline = signal["baseline"]
        m = baseline["mean"]
        window = signal["window"]["size"]
        conf = signal["confidence"]["status"]
        median = self._get_median(signal)
        direction = self._direction(signal)
        change_str = relative_change(observed, median)
        insight = metric_insight(metric, direction)

        # Handle degenerate baselines
        dev = signal.get("deviation", {})
        if dev.get("degenerate", False):
            med = baseline.get("median", m)
            base = (
                f"Metric '{metric}' was {observed}. "
                f"Baseline was constant at {med:.4g} across {window} observations. "
                f"No meaningful deviation."
            )
            return base

        # ---- Git metrics ----
        if metric == "files_touched":
            base = f"This commit touched {observed} files — {change_str}."
        elif metric == "dispersion":
            base = f"This change is spread across many parts of the codebase — {change_str}."
        elif metric == "change_locality":
            base = f"The change locality for this commit was {observed:.2f} — {change_str}."
        elif metric == "cochange_novelty_ratio":
            base = f"The co-change novelty ratio was {observed:.2f} — {change_str}."

        # ---- CI metrics ----
        elif metric == "run_duration":
            base = f"This CI build took {observed:.1f} seconds — {change_str}."
        elif metric == "run_failed":
            if observed > 0:
                base = "This CI build failed."
            else:
                base = "This CI build succeeded."

        # ---- Testing metrics ----
        elif metric == "total_tests":
            base = f"This test run executed {observed:.0f} tests — {change_str}."
        elif metric == "suite_duration":
            base = f"The test suite completed in {observed:.1f} seconds — {change_str}."
        elif metric == "skip_rate":
            base = f"The skip rate for this run was {observed:.2%} — {change_str}."

        # ---- Dependency metrics ----
        elif metric == "dependency_count":
            base = f"This snapshot has {observed:.0f} dependencies — {change_str}."
        elif metric == "max_depth":
            base = f"The maximum dependency depth is {observed:.0f} — {change_str}."

        # ---- Schema metrics ----
        elif metric == "endpoint_count":
            base = f"This schema version has {observed:.0f} endpoints — {change_str}."
        elif metric == "type_count":
            base = f"This schema version defines {observed:.0f} types — {change_str}."
        elif metric == "field_count":
            base = f"This schema version contains {observed:.0f} fields — {change_str}."
        elif metric == "schema_churn":
            base = f"Schema churn was {observed:.2f} — {change_str}."

        # ---- Deployment metrics ----
        elif metric == "release_cadence_hours":
            base = f"This release came {observed:.1f} hours after the previous one — {change_str}."
        elif metric == "is_prerelease":
            status = "a pre-release" if observed > 0 else "a stable release"
            base = f"This was {status}."
        elif metric == "asset_count":
            base = f"This release included {observed:.0f} assets — {change_str}."

        # ---- Config metrics ----
        elif metric == "resource_count":
            base = f"This configuration manages {observed:.0f} resources — {change_str}."
        elif metric == "resource_type_count":
            base = f"This configuration uses {observed:.0f} distinct resource types — {change_str}."
        elif metric == "config_churn":
            base = f"Configuration churn was {observed:.0f} — {change_str}."

        # ---- Error tracking metrics ----
        elif metric == "event_count":
            base = f"This error has {observed:.0f} occurrences — {change_str}."
        elif metric == "user_count":
            base = f"This error affected {observed:.0f} users — {change_str}."
        elif metric == "is_unhandled":
            if observed > 0:
                base = "This is an unhandled exception."
            else:
                base = "This error is handled."

        # ---- Security metrics ----
        elif metric == "vulnerability_count":
            base = f"This scan found {observed:.0f} vulnerabilities — {change_str}."
        elif metric == "critical_count":
            base = f"This scan found {observed:.0f} critical vulnerabilities — {change_str}."
        elif metric == "fixable_ratio":
            base = f"The fixable ratio is {observed:.2%} — {change_str}."

        # ---- Fallback ----
        else:
            base = f"Metric '{metric}' was {observed} — {change_str}."

        if insight:
            base += f" {insight}"

        if conf != "sufficient":
            base += " (based on limited history — may change as more data arrives)"

        return base

    def _hash(self, data: dict) -> str:
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    # ---------- Execution ----------

    def _load_signals(self):
        """Load Phase 2 signals from all family signal files."""
        all_signals = []
        for family, filename in SIGNAL_FILES.items():
            signal_file = self.phase2_path / filename
            if signal_file.exists():
                with open(signal_file, "r", encoding="utf-8") as f:
                    signals = json.load(f)
                all_signals.extend(signals)
        return all_signals

    def run(self):
        signals = self._load_signals()

        if not signals:
            raise FileNotFoundError(
                "No Phase 2 signals found. "
                "Ensure Phase 2 has been run for at least one source family."
            )

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
