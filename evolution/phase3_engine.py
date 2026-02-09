"""
Phase 3 Engine — Deterministic Explanation Layer

Multi-family implementation with optional Phase 3.1 LLM enhancement:
- One explanation per Phase 2 signal (any family)
- Template-based, deterministic rendering (Phase 3)
- Validation-gated LLM rendering when enabled (Phase 3.1)
- No aggregation, no judgment, no recommendations

Conforms to PHASE_3_CONTRACT.md and PHASE_3_DESIGN.md.
"""

from pathlib import Path
import json
import hashlib
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed; rely on actual environment variables

from evolution.phase3_1_renderer import Phase31Renderer

# All Phase 2 signal files, keyed by family
SIGNAL_FILES = {
    "git": "git_signals.json",
    "ci": "ci_signals.json",
    "testing": "testing_signals.json",
    "dependency": "dependency_signals.json",
    "schema": "schema_signals.json",
    "deployment": "deployment_signals.json",
    "config": "config_signals.json",
    "security": "security_signals.json",
}


class Phase3Engine:
    def __init__(self, evo_dir: Path):
        self.evo_dir = evo_dir
        self.phase2_path = evo_dir / "phase2"
        self.output_path = evo_dir / "phase3"
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.renderer = Phase31Renderer()

    # ---------- Templates ----------

    def _baseline_str(self, signal: dict) -> str:
        """Format baseline summary using median/MAD when available, else mean/stddev."""
        baseline = signal["baseline"]
        med = baseline.get("median")
        mad = baseline.get("mad")
        if med is not None and mad is not None and mad > 0:
            return f"median {med:.2f} (MAD {mad:.2f})"
        return f"{baseline['mean']:.2f} \u00b1 {baseline['stddev']:.2f}"

    def _template(self, signal: dict) -> str:
        metric = signal["metric"]
        observed = signal["observed"]
        baseline = signal["baseline"]
        m = baseline["mean"]
        std = baseline["stddev"]
        window = signal["window"]["size"]
        conf = signal["confidence"]["status"]
        engine = signal.get("engine_id", "unknown")
        bl = self._baseline_str(signal)

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
            base = (
                f"This change touched {observed} files. "
                f"Over the last {window} changes, the baseline was {bl}."
            )
        elif metric == "dispersion":
            base = (
                f"This change had a dispersion value of {observed:.2f}. "
                f"Recent baseline: {bl}."
            )
        elif metric == "change_locality":
            base = (
                f"The change locality for this commit was {observed:.2f}. "
                f"Recent baseline: {bl}."
            )
        elif metric == "cochange_novelty_ratio":
            base = (
                f"The co-change novelty ratio for this change was {observed:.2f}. "
                f"Recent baseline: {bl}."
            )

        # ---- CI metrics ----
        elif metric == "run_duration":
            base = (
                f"This CI run took {observed:.1f} seconds. "
                f"Recent runs: {bl} seconds."
            )
        elif metric == "run_failed":
            status = "failed" if observed > 0 else "succeeded"
            base = (
                f"This CI run {status}. "
                f"Recent failure rate: {m:.2%}."
            )

        # ---- Testing metrics ----
        elif metric == "total_tests":
            base = (
                f"This test run executed {observed:.0f} tests. "
                f"Recent baseline: {bl} tests."
            )
        elif metric == "suite_duration":
            base = (
                f"This test suite completed in {observed:.1f} seconds. "
                f"Recent baseline: {bl} seconds."
            )
        elif metric == "skip_rate":
            base = (
                f"The skip rate for this run was {observed:.2%}. "
                f"Recent baseline: {m:.2%} \u00b1 {std:.2%}."
            )

        # ---- Dependency metrics ----
        elif metric == "dependency_count":
            base = (
                f"This snapshot contains {observed:.0f} dependencies. "
                f"Recent baseline: {bl}."
            )
        elif metric == "max_depth":
            base = (
                f"The maximum transitive depth is {observed:.0f}. "
                f"Recent baseline: {bl}."
            )

        # ---- Schema metrics ----
        elif metric == "endpoint_count":
            base = (
                f"This schema version has {observed:.0f} endpoints. "
                f"Recent baseline: {bl}."
            )
        elif metric == "type_count":
            base = (
                f"This schema version defines {observed:.0f} types. "
                f"Recent baseline: {bl}."
            )
        elif metric == "field_count":
            base = (
                f"This schema version contains {observed:.0f} fields. "
                f"Recent baseline: {bl}."
            )
        elif metric == "schema_churn":
            base = (
                f"Schema churn for this version was {observed:.2f}. "
                f"Recent baseline: {bl}."
            )

        # ---- Deployment metrics ----
        elif metric == "release_cadence_hours":
            base = (
                f"This release came {observed:.1f} hours after the previous one. "
                f"Recent cadence baseline: {bl} hours."
            )
        elif metric == "is_prerelease":
            status = "a pre-release" if observed > 0 else "a stable release"
            base = (
                f"This was {status}. "
                f"Recent pre-release rate: {m:.2%}."
            )
        elif metric == "asset_count":
            base = (
                f"This release included {observed:.0f} assets. "
                f"Recent baseline: {bl} assets."
            )

        # ---- Config metrics ----
        elif metric == "resource_count":
            base = (
                f"This configuration manages {observed:.0f} resources. "
                f"Recent baseline: {bl}."
            )
        elif metric == "resource_type_count":
            base = (
                f"This configuration uses {observed:.0f} distinct resource types. "
                f"Recent baseline: {bl}."
            )
        elif metric == "config_churn":
            base = (
                f"Configuration churn was {observed:.0f} (total changes). "
                f"Recent baseline: {bl}."
            )

        # ---- Security metrics ----
        elif metric == "vulnerability_count":
            base = (
                f"This scan found {observed:.0f} vulnerabilities. "
                f"Recent baseline: {bl}."
            )
        elif metric == "critical_count":
            base = (
                f"This scan found {observed:.0f} critical vulnerabilities. "
                f"Recent baseline: {bl}."
            )
        elif metric == "fixable_ratio":
            base = (
                f"The fixable ratio is {observed:.2%} of findings. "
                f"Recent baseline: {m:.2%} \u00b1 {std:.2%}."
            )

        # ---- Fallback ----
        else:
            base = (
                f"Metric '{metric}' had a value of {observed}. "
                f"Baseline: {bl}."
            )

        if conf != "sufficient":
            base += " This comparison is based on limited history and may change as more data becomes available."

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

            # Phase 3.1: LLM enhancement with validation gate (if enabled)
            explanation = self.renderer.render(explanation)

            explanations.append(explanation)

        out_file = self.output_path / "explanations.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(explanations, f, indent=2)

        return explanations
