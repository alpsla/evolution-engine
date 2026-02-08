"""
Phase 4 Engine — Pattern Learning & Knowledge Layer

Sub-layers:
  4a: Algorithmic Pattern Discovery (deterministic)
      - Signal fingerprinting
      - KB lookup (fast path)
      - Co-occurrence detection
      - Temporal sequence detection
  4b: Semantic Pattern Interpretation (LLM-assisted)
      - Enriches patterns with human-readable descriptions
      - Bounded by validation gate

Conforms to PHASE_4_CONTRACT.md and PHASE_4_DESIGN.md.
"""

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from statistics import mean, pstdev
from typing import Optional

from evolution.knowledge_store import SQLiteKnowledgeStore
from evolution.validation_gate import ValidationGate

try:
    from evolution.llm_openrouter import OpenRouterClient
except ImportError:
    OpenRouterClient = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─────────────────── Configuration ───────────────────

DEFAULT_PARAMS = {
    "min_support": 3,          # Lowered from 10 for early-stage use; raise for production
    "min_correlation": 0.5,    # Minimum pairwise correlation for co-occurrence
    "promotion_threshold": 10, # Occurrences to promote to knowledge (lowered for testing)
    "decay_window": 90,        # Days before unseen patterns decay
    "semantic_multiplier": 3,  # Extra evidence for LLM-only hypotheses
    "direction_threshold": 1.0, # Stddev threshold for direction classification
}

# Signal files from Phase 2 (same map as Phase 3)
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


# ─────────────────── Signal Fingerprinting ───────────────────


def classify_direction(deviation: float, threshold: float = 1.0) -> str:
    """Classify a signal's deviation into a direction.

    Per PHASE_4_DESIGN.md §3.4:
      increased:  deviation > +threshold stddev
      decreased:  deviation < -threshold stddev
      unchanged:  within ±threshold stddev
    """
    if deviation > threshold:
        return "increased"
    elif deviation < -threshold:
        return "decreased"
    return "unchanged"


def compute_fingerprint(signal_components: list[tuple[str, str, str]]) -> str:
    """Compute a fingerprint from sorted (engine_id, metric, direction) tuples.

    Per PHASE_4_DESIGN.md §3.2:
      fingerprint = hash(sorted([(engine_id, metric, direction), ...]))
    """
    canonical = sorted(signal_components)
    encoded = json.dumps(canonical, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def signals_to_components(signals: list[dict], threshold: float = 1.0) -> list[tuple[str, str, str]]:
    """Convert Phase 2 signals to fingerprint components.

    Only includes signals that deviate beyond the threshold (i.e. not 'unchanged').
    """
    components = []
    for s in signals:
        deviation = s["deviation"]["measure"]
        direction = classify_direction(deviation, threshold)
        if direction != "unchanged":
            components.append((s["engine_id"], s["metric"], direction))
    return components


# ─────────────────── Phase 4 Engine ───────────────────


class Phase4Engine:
    """Phase 4: Pattern Learning & Knowledge Layer.

    Orchestrates fingerprinting, KB lookup, co-occurrence discovery,
    semantic interpretation, and pattern lifecycle.
    """

    def __init__(self, evo_dir: Path, params: dict = None):
        self.evo_dir = evo_dir
        self.phase2_path = evo_dir / "phase2"
        self.phase3_path = evo_dir / "phase3"
        self.output_path = evo_dir / "phase4"
        self.output_path.mkdir(parents=True, exist_ok=True)

        self.params = {**DEFAULT_PARAMS, **(params or {})}

        # Knowledge Base
        self.kb = SQLiteKnowledgeStore(self.output_path / "knowledge.db")

        # Validation gate (reuse Phase 3.1 gate for 4b)
        self.gate = ValidationGate()

        # LLM client for Phase 4b (optional)
        self._llm = None
        self._llm_enabled = os.getenv("PHASE4B_ENABLED", os.getenv("PHASE31_ENABLED", "false")).lower() == "true"
        self._llm_model = os.getenv("PHASE4B_MODEL", "anthropic/claude-sonnet-4.5")

    def _get_llm(self):
        """Lazy-init LLM client."""
        if self._llm is None and self._llm_enabled and OpenRouterClient:
            try:
                self._llm = OpenRouterClient(self._llm_model)
            except Exception:
                self._llm_enabled = False
        return self._llm

    # ─────────────────── Data Loading ───────────────────

    def _load_all_signals(self) -> list[dict]:
        """Load Phase 2 signals from all family signal files."""
        all_signals = []
        for family, filename in SIGNAL_FILES.items():
            signal_file = self.phase2_path / filename
            if signal_file.exists():
                with open(signal_file, "r", encoding="utf-8") as f:
                    signals = json.load(f)
                all_signals.extend(signals)
        return all_signals

    def _load_explanations(self) -> dict:
        """Load Phase 3 explanations, indexed by signal_ref for fast lookup."""
        exp_file = self.phase3_path / "explanations.json"
        if not exp_file.exists():
            return {}
        with open(exp_file, "r", encoding="utf-8") as f:
            explanations = json.load(f)
        # Index by signal_ref for quick access
        by_ref = {}
        for exp in explanations:
            ref = exp.get("signal_ref")
            if ref:
                by_ref[ref] = exp
        return by_ref

    def _group_signals_by_event(self, signals: list[dict]) -> dict[str, list[dict]]:
        """Group signals by their event_ref (same event = same observation window)."""
        groups = defaultdict(list)
        for s in signals:
            ref = s.get("event_ref", "")
            if ref:
                groups[ref].append(s)
        return dict(groups)

    # ─────────────────── Phase 4a: KB Lookup (Fast Path) ───────────────────

    def _lookup_fingerprint(self, fingerprint: str) -> dict:
        """Check KB for existing pattern or knowledge matching this fingerprint.

        Returns:
          {"match": "knowledge", "artifact": ...} — known pattern
          {"match": "pattern",   "artifact": ...} — candidate pattern (accumulating)
          {"match": None} — no match, proceed to discovery
        """
        # Check approved knowledge first
        ka = self.kb.get_knowledge_by_fingerprint(fingerprint, scope="local")
        if ka:
            return {"match": "knowledge", "artifact": ka}

        # Check candidate patterns
        pat = self.kb.get_pattern_by_fingerprint(fingerprint, scope="local")
        if pat:
            return {"match": "pattern", "artifact": pat}

        return {"match": None}

    # ─────────────────── Phase 4a: Co-Occurrence Discovery ───────────────────

    def _discover_cooccurrences(self, signals: list[dict]) -> list[dict]:
        """Discover co-occurring signal pairs/groups across the signal window.

        Cross-family signals don't share event_refs, so we align them by
        ordinal position within each metric series. This detects when metrics
        from different families deviate in correlated patterns over time.

        Returns list of candidate pattern dicts (not yet stored).
        """
        threshold = self.params["direction_threshold"]
        min_support = self.params["min_support"]
        min_correlation = self.params["min_correlation"]

        # Build per-metric deviation series, ordered by appearance
        # Key: (engine_id, metric) -> list of {deviation, direction, event_ref}
        metric_series = defaultdict(list)

        for s in signals:
            deviation = s["deviation"]["measure"]
            direction = classify_direction(deviation, threshold)
            key = (s["engine_id"], s["metric"])
            metric_series[key].append({
                "event_ref": s.get("event_ref", ""),
                "direction": direction,
                "deviation": deviation,
            })

        # Only consider metrics with enough observations
        active_metrics = [k for k, v in metric_series.items() if len(v) >= min_support]

        candidates = []

        for (k1, k2) in combinations(active_metrics, 2):
            # Skip intra-family correlations (less interesting for cross-source patterns)
            if k1[0] == k2[0]:
                continue

            series1 = metric_series[k1]
            series2 = metric_series[k2]

            # Align by ordinal position (truncate to shorter series)
            n = min(len(series1), len(series2))
            if n < min_support:
                continue

            deviations_1 = [series1[i]["deviation"] for i in range(n)]
            deviations_2 = [series2[i]["deviation"] for i in range(n)]

            # Count co-deviations (both deviate beyond threshold simultaneously)
            co_deviations = 0
            for i in range(n):
                d1 = series1[i]["direction"]
                d2 = series2[i]["direction"]
                if d1 != "unchanged" and d2 != "unchanged":
                    co_deviations += 1

            if co_deviations < min_support:
                continue

            # Compute Pearson correlation on deviation magnitudes
            correlation = self._pearson(deviations_1, deviations_2)

            if abs(correlation) < min_correlation:
                continue

            # Build fingerprint from predominant directions
            dir1 = self._predominant_direction(series1, threshold)
            dir2 = self._predominant_direction(series2, threshold)
            components = [
                (k1[0], k1[1], dir1),
                (k2[0], k2[1], dir2),
            ]
            fingerprint = compute_fingerprint(components)

            # Collect signal_refs from both series
            signal_refs = [e["event_ref"] for e in series1[:10] if e["event_ref"]]
            signal_refs += [e["event_ref"] for e in series2[:10] if e["event_ref"]]

            candidates.append({
                "fingerprint": fingerprint,
                "scope": "local",
                "discovery_method": "statistical",
                "pattern_type": "co_occurrence",
                "sources": sorted(set([k1[0], k2[0]])),
                "metrics": sorted([k1[1], k2[1]]),
                "description_statistical": (
                    f"Signals {k1[0]}.{k1[1]} and {k2[0]}.{k2[1]} co-occur "
                    f"with correlation {correlation:.2f} across {co_deviations} observations."
                ),
                "correlation_strength": round(correlation, 4),
                "occurrence_count": co_deviations,
                "signal_refs": signal_refs,
                "first_seen": datetime.utcnow().isoformat() + "Z",
                "last_seen": datetime.utcnow().isoformat() + "Z",
                "confidence_tier": "statistical",
                "confidence_status": "emerging",
            })

        return candidates

    @staticmethod
    def _pearson(xs: list[float], ys: list[float]) -> float:
        """Compute Pearson correlation coefficient."""
        n = len(xs)
        if n < 2:
            return 0.0

        mx = mean(xs)
        my = mean(ys)
        sx = pstdev(xs)
        sy = pstdev(ys)

        if sx == 0 or sy == 0:
            return 0.0

        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
        return cov / (sx * sy)

    @staticmethod
    def _predominant_direction(entries: list[dict], threshold: float) -> str:
        """Determine the predominant deviation direction for a metric series."""
        directions = [classify_direction(e["deviation"], threshold) for e in entries]
        inc = directions.count("increased")
        dec = directions.count("decreased")
        if inc > dec:
            return "increased"
        elif dec > inc:
            return "decreased"
        return "unchanged"

    # ─────────────────── Phase 4b: Semantic Interpretation ───────────────────

    def _interpret_pattern(self, pattern: dict, explanations_by_ref: dict) -> Optional[str]:
        """Use LLM to generate a semantic description for a discovered pattern.

        Per PHASE_4_DESIGN.md §5:
        - Called only when a new candidate lacks a semantic description
        - Bounded by validation gate
        - Returns None if LLM is unavailable or validation fails
        """
        llm = self._get_llm()
        if not llm:
            return None

        # Gather Phase 3 explanations for the pattern's signals
        signal_explanations = []
        for ref in pattern.get("signal_refs", [])[:5]:  # Cap at 5 for prompt size
            exp = explanations_by_ref.get(ref)
            if exp:
                signal_explanations.append(f"- {exp.get('summary', '')}")

        if not signal_explanations:
            return None

        # Build the prompt per PHASE_4_DESIGN.md §5.2
        prompt = (
            "You are analyzing a set of co-occurring software evolution signals.\n\n"
            f"Statistical finding: {pattern.get('description_statistical', '')}\n\n"
            "Signal explanations:\n"
            + "\n".join(signal_explanations)
            + "\n\n"
            "Describe the structural theme these signals represent in ONE sentence.\n"
            "Do not add judgment, recommendations, or speculation.\n"
            "Do not use words like \"risk\", \"danger\", \"should\", or \"needs\".\n"
            "Describe only what is structurally happening."
        )

        try:
            candidate = llm.generate(prompt)
        except Exception:
            return None

        # Strip preambles
        candidate = re.sub(
            r"^(?:(?:Here(?:'s| is) (?:a |the )?(?:description|sentence)[^:]*:|Description:)\s*\n?)",
            "", candidate, flags=re.IGNORECASE,
        ).strip()

        # Validation gate per PHASE_4_DESIGN.md §5.3
        # No judgment language
        if not self.gate.no_forbidden_language(candidate):
            return None
        # Length constraint: 1-3 sentences
        sentences = [s.strip() for s in candidate.split(".") if s.strip()]
        if len(sentences) > 4:
            return None

        return candidate

    # ─────────────────── Pattern Lifecycle ───────────────────

    def _check_promotion(self, pattern: dict) -> bool:
        """Check if a pattern should be promoted to Knowledge Artifact.

        Per PHASE_4_CONTRACT.md §3:
        - statistical: needs promotion_threshold occurrences
        - speculative: needs promotion_threshold * semantic_multiplier
        - confirmed: already promoted, skip
        """
        # Already promoted
        if pattern.get("confidence_tier") == "confirmed":
            return False

        threshold = self.params["promotion_threshold"]
        count = pattern["occurrence_count"]

        if pattern["confidence_tier"] == "speculative":
            threshold = threshold * self.params["semantic_multiplier"]

        # Also check that knowledge doesn't already exist for this fingerprint
        existing_ka = self.kb.get_knowledge_by_fingerprint(pattern["fingerprint"], pattern.get("scope", "local"))
        if existing_ka:
            return False

        return count >= threshold

    def _promote_pattern(self, pattern: dict) -> str:
        """Promote a pattern to a Knowledge Artifact."""
        knowledge = {
            "derived_from": pattern["pattern_id"],
            "fingerprint": pattern["fingerprint"],
            "scope": pattern.get("scope", "local"),
            "pattern_type": pattern["pattern_type"],
            "sources": pattern["sources"],
            "metrics": pattern["metrics"],
            "description_statistical": pattern.get("description_statistical", ""),
            "description_semantic": pattern.get("description_semantic"),
            "support_count": pattern["occurrence_count"],
            "first_seen": pattern["first_seen"],
            "last_seen": pattern["last_seen"],
            "approval_method": "automatic",
        }

        knowledge_id = self.kb.create_knowledge(knowledge)

        # Update pattern confidence
        self.kb.update_pattern(pattern["pattern_id"], {
            "confidence_tier": "confirmed",
            "confidence_status": "sufficient",
        })

        return knowledge_id

    def _run_decay(self) -> list[str]:
        """Expire patterns not seen within the decay window.

        Per PHASE_4_CONTRACT.md §3: speculative hypotheses that never
        get statistical confirmation must decay and expire.
        """
        decay_days = self.params["decay_window"]
        decayed = self.kb.get_decayed_patterns(decay_days)
        expired_ids = []

        for pat in decayed:
            # Don't expire confirmed patterns
            if pat.get("confidence_tier") == "confirmed":
                continue
            self.kb.expire_pattern(pat["pattern_id"])
            expired_ids.append(pat["pattern_id"])

        return expired_ids

    # ─────────────────── Main Execution ───────────────────

    def run(self) -> dict:
        """Execute the full Phase 4 pipeline.

        Steps:
          1. Load Phase 2 signals and Phase 3 explanations
          2. Compute signal fingerprint for the current batch
          3. KB lookup (fast path — recognition)
          4. Co-occurrence discovery (if no match)
          5. Semantic interpretation (Phase 4b, if enabled)
          6. Pattern lifecycle (accumulate, promote, decay)

        Returns a summary dict with counts and discovered patterns.
        """
        now = datetime.utcnow().isoformat() + "Z"

        # Step 1: Load data
        signals = self._load_all_signals()
        if not signals:
            return {"status": "no_signals", "patterns_discovered": 0, "patterns_recognized": 0}

        explanations_by_ref = self._load_explanations()

        # Step 2: Compute batch fingerprint
        threshold = self.params["direction_threshold"]
        components = signals_to_components(signals, threshold)
        batch_fingerprint = compute_fingerprint(components) if components else None

        result = {
            "status": "complete",
            "total_signals": len(signals),
            "deviating_signals": len(components),
            "batch_fingerprint": batch_fingerprint,
            "patterns_recognized": 0,
            "patterns_incremented": 0,
            "patterns_discovered": 0,
            "patterns_enriched": 0,
            "patterns_promoted": 0,
            "patterns_expired": 0,
            "knowledge_artifacts": 0,
            "details": [],
        }

        # Step 3: KB lookup (fast path)
        recognized = False
        if batch_fingerprint:
            lookup = self._lookup_fingerprint(batch_fingerprint)

            if lookup["match"] == "knowledge":
                result["patterns_recognized"] += 1
                result["details"].append({
                    "action": "recognized",
                    "fingerprint": batch_fingerprint,
                    "knowledge_id": lookup["artifact"]["knowledge_id"],
                    "description": lookup["artifact"].get("description_semantic")
                                   or lookup["artifact"].get("description_statistical"),
                })
                recognized = True

            elif lookup["match"] == "pattern":
                # Increment existing candidate
                signal_refs = [s.get("event_ref", "") for s in signals if s.get("event_ref")][:20]
                self.kb.increment_pattern(lookup["artifact"]["pattern_id"], signal_refs, now)
                result["patterns_incremented"] += 1

                # Check promotion
                updated = self.kb.get_pattern(lookup["artifact"]["pattern_id"])
                if updated and self._check_promotion(updated):
                    kid = self._promote_pattern(updated)
                    result["patterns_promoted"] += 1
                    result["details"].append({
                        "action": "promoted",
                        "pattern_id": updated["pattern_id"],
                        "knowledge_id": kid,
                    })

                recognized = True

        # Step 4: Co-occurrence discovery (if no batch match)
        if not recognized:
            candidates = self._discover_cooccurrences(signals)

            for candidate in candidates:
                # Check if this specific co-occurrence fingerprint already exists
                existing = self.kb.get_pattern_by_fingerprint(candidate["fingerprint"], "local")

                if existing:
                    # Increment existing
                    signal_refs = candidate.get("signal_refs", [])
                    self.kb.increment_pattern(existing["pattern_id"], signal_refs, now)
                    result["patterns_incremented"] += 1

                    # Check promotion
                    updated = self.kb.get_pattern(existing["pattern_id"])
                    if updated and self._check_promotion(updated):
                        kid = self._promote_pattern(updated)
                        result["patterns_promoted"] += 1
                else:
                    # New pattern — store it
                    pattern_id = self.kb.create_pattern(candidate)
                    result["patterns_discovered"] += 1

                    # Step 5: Phase 4b semantic interpretation
                    candidate["pattern_id"] = pattern_id
                    semantic_desc = self._interpret_pattern(candidate, explanations_by_ref)
                    if semantic_desc:
                        self.kb.update_pattern(pattern_id, {
                            "description_semantic": semantic_desc,
                        })
                        result["patterns_enriched"] += 1

                    result["details"].append({
                        "action": "discovered",
                        "pattern_id": pattern_id,
                        "fingerprint": candidate["fingerprint"],
                        "sources": candidate["sources"],
                        "metrics": candidate["metrics"],
                        "correlation": candidate.get("correlation_strength"),
                        "description_statistical": candidate.get("description_statistical"),
                        "description_semantic": semantic_desc,
                    })

        # Step 6: Pattern lifecycle — decay
        expired_ids = self._run_decay()
        result["patterns_expired"] = len(expired_ids)

        # Count total knowledge artifacts
        result["knowledge_artifacts"] = len(self.kb.list_knowledge(scope="local"))

        # Save result summary
        summary_file = self.output_path / "phase4_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        return result

    def close(self):
        """Close KB connection."""
        self.kb.close()
