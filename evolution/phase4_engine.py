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
import logging
import os
import re
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from statistics import mean, pstdev
from typing import Optional

log = logging.getLogger("evolution.phase4")

from evolution.knowledge_store import SQLiteKnowledgeStore
from evolution.validation_gate import ValidationGate

try:
    from evolution.llm_openrouter import OpenRouterClient
except ImportError:
    OpenRouterClient = None

try:
    from evolution.llm_anthropic import AnthropicClient
except ImportError:
    AnthropicClient = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─────────────────── Configuration ───────────────────

DEFAULT_PARAMS = {
    "min_support": 3,          # Lowered from 10 for early-stage use; raise for production
    "min_correlation": 0.3,    # Minimum pairwise correlation for co-occurrence
    "min_lift": 1.5,           # Minimum lift for co-occurrence detection (alternative to correlation)
    "min_effect_size": 0.2,    # Minimum Cohen's d for presence-based patterns
    "promotion_threshold": 10, # Occurrences to promote to knowledge (lowered for testing)
    "decay_window": 90,        # Days before unseen patterns decay
    "semantic_multiplier": 3,  # Extra evidence for LLM-only hypotheses
    "direction_threshold": 1.0, # Stddev threshold for direction classification
    "confidence_full_at": 30,  # Sample count at which confidence weight reaches 1.0
    "temporal_window_hours": 24,  # Time window for temporal alignment (supplementary to commit-SHA)
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


def classify_direction(deviation: float, threshold: float = 1.0,
                       unit: str = "modified_zscore") -> str:
    """Classify a signal's deviation into a direction.

    Per PHASE_4_DESIGN.md §3.4:
      increased:  deviation > +threshold
      decreased:  deviation < -threshold
      unchanged:  within ±threshold or degenerate baseline
    """
    if unit == "degenerate":
        return "unchanged"
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
    Skips degenerate signals.
    """
    components = []
    for s in signals:
        dev = s.get("deviation", {})
        if dev.get("degenerate", False):
            continue
        deviation = dev.get("measure", 0)
        if deviation is None:
            continue
        unit = dev.get("unit", "modified_zscore")
        direction = classify_direction(deviation, threshold, unit)
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
        if self._llm is None and self._llm_enabled:
            # Try Anthropic direct first
            if os.getenv("ANTHROPIC_API_KEY") and AnthropicClient:
                try:
                    self._llm = AnthropicClient(self._llm_model)
                    return self._llm
                except Exception:
                    pass

            # Fallback to OpenRouter
            if OpenRouterClient:
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

    # ─────────────────── Commit Index ───────────────────

    def _build_commit_index(self) -> dict[str, str]:
        """Build a mapping from event_id to commit SHA.

        Reads Phase 1 event files and extracts the commit SHA each event
        is associated with, enabling cross-family signal alignment by commit.

        Returns:
            {event_id: commit_sha} for all events that have a commit SHA.
        """
        if hasattr(self, "_commit_index"):
            return self._commit_index

        index: dict[str, str] = {}
        events_dir = self.evo_dir / "events"
        if not events_dir.exists():
            self._commit_index = index
            return index

        for p in events_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    ev = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            event_id = ev.get("event_id", "")
            if not event_id:
                continue

            payload = ev.get("payload", {})
            source_type = ev.get("source_type", "")

            # Git events store commit hash directly in payload
            if source_type == "git":
                sha = payload.get("commit_hash")
            else:
                # All other families use payload.trigger.commit_sha
                sha = (payload.get("trigger") or {}).get("commit_sha")

            if sha:
                index[event_id] = sha

        self._commit_index = index
        return index

    # ─────────────────── Temporal Index ───────────────────

    @staticmethod
    def _extract_event_timestamp(ev: dict) -> str:
        """Extract the actual event timestamp from a Phase 1 event.

        Uses the real event time (commit date, CI run creation, release date)
        rather than ``observed_at`` which reflects ingestion time and collapses
        all events into a single time bucket.

        Falls back to ``observed_at`` for walker-produced events (dependency,
        schema, config) where ``observed_at`` is already set to the commit time
        via ``override_observed_at``.
        """
        payload = ev.get("payload", {})
        source_type = ev.get("source_type", "")

        if source_type == "git":
            ts = payload.get("committed_at") or payload.get("authored_at")
            if ts:
                return ts

        elif source_type == "github_actions":
            timing = payload.get("timing", {})
            ts = timing.get("created_at") or timing.get("started_at")
            if ts:
                return ts

        elif source_type == "github_releases":
            timing = payload.get("timing", {})
            ts = timing.get("initiated_at") or timing.get("completed_at")
            if ts:
                return ts

        # Fallback: observed_at (correct for walker events that used override)
        return ev.get("observed_at", "")

    def _build_temporal_index(self) -> dict[str, str]:
        """Build a mapping from event_id to actual event timestamp.

        Uses the real event time (commit date, CI run creation, release date)
        rather than ``observed_at`` which reflects ingestion time.

        Used for temporal alignment when commit-SHA alignment has insufficient
        overlap (e.g. CI runs cover multiple commits, deployment events are rare).

        Returns:
            {event_id: event_timestamp_iso} for all events that have a timestamp.
        """
        if hasattr(self, "_temporal_index"):
            return self._temporal_index

        index: dict[str, str] = {}
        events_dir = self.evo_dir / "events"
        if not events_dir.exists():
            self._temporal_index = index
            return index

        for p in events_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    ev = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            event_id = ev.get("event_id", "")
            ts = self._extract_event_timestamp(ev)
            if event_id and ts:
                index[event_id] = ts

        self._temporal_index = index
        return index

    @staticmethod
    def _time_bucket(iso_ts: str, window_hours: int) -> Optional[int]:
        """Convert ISO timestamp to a time bucket number.

        Returns floor(epoch_hours / window_hours), or None if parsing fails.
        """
        try:
            dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
            epoch_hours = dt.timestamp() / 3600
            return int(epoch_hours // window_hours)
        except (ValueError, TypeError, AttributeError):
            return None

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

        Two alignment passes:
        1. Commit-SHA alignment (precise): signals sharing the same originating
           commit are paired. Preferred when overlap >= min_support.
        2. Temporal alignment (supplementary): for cross-family pairs with
           insufficient SHA overlap, bucket signals into time windows and align
           within the same window. Addresses structural sparsity (e.g. git has
           6,708 commits but CI has 58 runs, SHA overlap is only 11).

        Degenerate signals (constant baselines) are pre-filtered.
        Correlations are discounted by confidence weight (sample count).

        Returns list of candidate pattern dicts (not yet stored).
        """
        threshold = self.params["direction_threshold"]
        min_support = self.params["min_support"]
        min_correlation = self.params["min_correlation"]
        min_lift = self.params.get("min_lift", 1.5)
        confidence_full_at = self.params.get("confidence_full_at", 30)
        window_hours = self.params.get("temporal_window_hours", 24)

        commit_index = self._build_commit_index()
        temporal_index = self._build_temporal_index()

        # Pre-filter: exclude degenerate signals
        valid_signals = []
        skipped = 0
        for s in signals:
            dev = s.get("deviation", {})
            if dev.get("degenerate", False) or dev.get("measure") is None:
                skipped += 1
                continue
            valid_signals.append(s)
        if skipped:
            log.info("Co-occurrence: skipped %d degenerate signals (of %d total)",
                     skipped, len(signals))

        # Build per-metric deviation series keyed by commit SHA
        # Key: (engine_id, metric) -> {commit_sha: {deviation, direction, event_ref}}
        metric_by_commit: dict[tuple, dict[str, dict]] = defaultdict(dict)
        # Also build per-metric deviation series keyed by time bucket
        # Key: (engine_id, metric) -> {bucket: {deviation, direction, event_ref}}
        metric_by_bucket: dict[tuple, dict[int, dict]] = defaultdict(dict)

        for s in valid_signals:
            event_ref = s.get("event_ref", "")
            deviation = s["deviation"]["measure"]
            unit = s["deviation"].get("unit", "modified_zscore")
            direction = classify_direction(deviation, threshold, unit)
            key = (s["engine_id"], s["metric"])
            entry = {
                "event_ref": event_ref,
                "direction": direction,
                "deviation": deviation,
            }

            commit_sha = commit_index.get(event_ref)
            if commit_sha:
                metric_by_commit[key][commit_sha] = entry

            # Temporal bucket for supplementary alignment
            ts = temporal_index.get(event_ref)
            if ts:
                bucket = self._time_bucket(ts, window_hours)
                if bucket is not None:
                    # Keep the entry with highest absolute deviation per bucket
                    existing = metric_by_bucket[key].get(bucket)
                    if existing is None or abs(deviation) > abs(existing["deviation"]):
                        metric_by_bucket[key][bucket] = entry

        # Only consider metrics with enough commit observations
        active_metrics_commit = [k for k, v in metric_by_commit.items() if len(v) >= min_support]

        candidates = []
        discovered_pairs = set()  # Track pairs found via commit alignment

        # ── Pass 1: Commit-SHA alignment (precise) ──
        for (k1, k2) in combinations(active_metrics_commit, 2):
            # Skip intra-family correlations
            if k1[0] == k2[0]:
                continue

            commits1 = metric_by_commit[k1]
            commits2 = metric_by_commit[k2]

            # Align by shared commit SHAs
            shared_commits = sorted(set(commits1) & set(commits2))
            n = len(shared_commits)
            if n < min_support:
                continue

            deviations_1 = [commits1[c]["deviation"] for c in shared_commits]
            deviations_2 = [commits2[c]["deviation"] for c in shared_commits]

            # Count co-deviations (both deviate beyond threshold simultaneously)
            co_deviations = 0
            for c in shared_commits:
                d1 = commits1[c]["direction"]
                d2 = commits2[c]["direction"]
                if d1 != "unchanged" and d2 != "unchanged":
                    co_deviations += 1

            if co_deviations < min_support:
                continue

            # Compute Pearson correlation on aligned deviation magnitudes
            correlation = self._pearson(deviations_1, deviations_2)

            # Discount correlation by confidence (min sample count of the two series)
            min_samples = min(len(commits1), len(commits2))
            confidence_weight = min(1.0, min_samples / confidence_full_at)
            effective_correlation = correlation * confidence_weight

            # Acceptance: Pearson correlation OR co-occurrence lift
            accepted_via = None
            lift = 0.0
            if abs(effective_correlation) >= min_correlation:
                accepted_via = "correlation"
            else:
                # Lift-based co-occurrence: do they deviate together more than chance?
                rate_1 = sum(1 for c in shared_commits if commits1[c]["direction"] != "unchanged") / n
                rate_2 = sum(1 for c in shared_commits if commits2[c]["direction"] != "unchanged") / n
                expected_rate = rate_1 * rate_2
                observed_rate = co_deviations / n
                lift = observed_rate / expected_rate if expected_rate > 0 else 0.0
                if lift >= min_lift:
                    accepted_via = "lift"

            if not accepted_via:
                continue

            # Build fingerprint from predominant directions
            aligned_entries_1 = [commits1[c] for c in shared_commits]
            aligned_entries_2 = [commits2[c] for c in shared_commits]
            dir1 = self._predominant_direction(aligned_entries_1, threshold)
            dir2 = self._predominant_direction(aligned_entries_2, threshold)
            components = [
                (k1[0], k1[1], dir1),
                (k2[0], k2[1], dir2),
            ]
            fingerprint = compute_fingerprint(components)

            # Collect signal_refs from both series (aligned commits only)
            signal_refs = [commits1[c]["event_ref"] for c in shared_commits[:10]]
            signal_refs += [commits2[c]["event_ref"] for c in shared_commits[:10]]

            # Build description based on acceptance method
            if accepted_via == "correlation":
                desc = (
                    f"Signals {k1[0]}.{k1[1]} and {k2[0]}.{k2[1]} co-occur "
                    f"with correlation {effective_correlation:.2f} across {co_deviations} "
                    f"commit-aligned observations (of {n} shared commits)."
                )
            else:
                desc = (
                    f"Signals {k1[0]}.{k1[1]} and {k2[0]}.{k2[1]} co-deviate "
                    f"{lift:.1f}x more than expected by chance across {co_deviations} "
                    f"commit-aligned observations (of {n} shared commits, lift={lift:.2f})."
                )

            candidates.append({
                "fingerprint": fingerprint,
                "scope": "local",
                "discovery_method": "statistical",
                "alignment": "commit_sha",
                "pattern_type": "co_occurrence",
                "sources": sorted(set([k1[0], k2[0]])),
                "metrics": sorted([k1[1], k2[1]]),
                "description_statistical": desc,
                "correlation_strength": round(effective_correlation, 4),
                "raw_correlation": round(correlation, 4),
                "confidence_weight": round(confidence_weight, 4),
                "lift": round(lift, 4) if accepted_via == "lift" else None,
                "accepted_via": accepted_via,
                "occurrence_count": co_deviations,
                "signal_refs": signal_refs,
                "first_seen": datetime.utcnow().isoformat() + "Z",
                "last_seen": datetime.utcnow().isoformat() + "Z",
                "confidence_tier": "statistical",
                "confidence_status": "emerging",
            })

            discovered_pairs.add((k1, k2))

        # ── Pass 2: Temporal alignment (supplementary) ──
        # Only for cross-family pairs that weren't found via commit alignment
        active_metrics_temporal = [k for k, v in metric_by_bucket.items() if len(v) >= min_support]

        temporal_count = 0
        for (k1, k2) in combinations(active_metrics_temporal, 2):
            if k1[0] == k2[0]:
                continue
            # Skip pairs already discovered via commit alignment
            if (k1, k2) in discovered_pairs or (k2, k1) in discovered_pairs:
                continue

            buckets1 = metric_by_bucket[k1]
            buckets2 = metric_by_bucket[k2]

            shared_buckets = sorted(set(buckets1) & set(buckets2))
            n = len(shared_buckets)
            if n < min_support:
                continue

            deviations_1 = [buckets1[b]["deviation"] for b in shared_buckets]
            deviations_2 = [buckets2[b]["deviation"] for b in shared_buckets]

            co_deviations = 0
            for b in shared_buckets:
                d1 = buckets1[b]["direction"]
                d2 = buckets2[b]["direction"]
                if d1 != "unchanged" and d2 != "unchanged":
                    co_deviations += 1

            if co_deviations < min_support:
                continue

            correlation = self._pearson(deviations_1, deviations_2)

            min_samples = min(len(buckets1), len(buckets2))
            confidence_weight = min(1.0, min_samples / confidence_full_at)
            effective_correlation = correlation * confidence_weight

            # Acceptance: Pearson correlation OR co-occurrence lift
            accepted_via = None
            lift = 0.0
            if abs(effective_correlation) >= min_correlation:
                accepted_via = "correlation"
            else:
                rate_1 = sum(1 for b in shared_buckets if buckets1[b]["direction"] != "unchanged") / n
                rate_2 = sum(1 for b in shared_buckets if buckets2[b]["direction"] != "unchanged") / n
                expected_rate = rate_1 * rate_2
                observed_rate = co_deviations / n
                lift = observed_rate / expected_rate if expected_rate > 0 else 0.0
                if lift >= min_lift:
                    accepted_via = "lift"

            if not accepted_via:
                continue

            aligned_entries_1 = [buckets1[b] for b in shared_buckets]
            aligned_entries_2 = [buckets2[b] for b in shared_buckets]
            dir1 = self._predominant_direction(aligned_entries_1, threshold)
            dir2 = self._predominant_direction(aligned_entries_2, threshold)
            components = [
                (k1[0], k1[1], dir1),
                (k2[0], k2[1], dir2),
            ]
            fingerprint = compute_fingerprint(components)

            signal_refs = [buckets1[b]["event_ref"] for b in shared_buckets[:10]]
            signal_refs += [buckets2[b]["event_ref"] for b in shared_buckets[:10]]

            if accepted_via == "correlation":
                desc = (
                    f"Signals {k1[0]}.{k1[1]} and {k2[0]}.{k2[1]} co-occur "
                    f"with correlation {effective_correlation:.2f} across {co_deviations} "
                    f"temporally-aligned observations (of {n} shared {window_hours}h windows)."
                )
            else:
                desc = (
                    f"Signals {k1[0]}.{k1[1]} and {k2[0]}.{k2[1]} co-deviate "
                    f"{lift:.1f}x more than expected by chance across {co_deviations} "
                    f"temporally-aligned observations (of {n} shared {window_hours}h windows, lift={lift:.2f})."
                )

            candidates.append({
                "fingerprint": fingerprint,
                "scope": "local",
                "discovery_method": "statistical",
                "alignment": "temporal",
                "pattern_type": "co_occurrence",
                "sources": sorted(set([k1[0], k2[0]])),
                "metrics": sorted([k1[1], k2[1]]),
                "description_statistical": desc,
                "correlation_strength": round(effective_correlation, 4),
                "raw_correlation": round(correlation, 4),
                "confidence_weight": round(confidence_weight, 4),
                "lift": round(lift, 4) if accepted_via == "lift" else None,
                "accepted_via": accepted_via,
                "occurrence_count": co_deviations,
                "signal_refs": signal_refs,
                "first_seen": datetime.utcnow().isoformat() + "Z",
                "last_seen": datetime.utcnow().isoformat() + "Z",
                "confidence_tier": "statistical",
                "confidence_status": "emerging",
            })
            temporal_count += 1

        if temporal_count:
            log.info("Temporal alignment discovered %d additional candidate patterns", temporal_count)

        return candidates

    def _discover_presence_patterns(self, signals: list[dict]) -> list[dict]:
        """Discover patterns where the presence of events from one family
        systematically shifts metric distributions in another family.

        For each non-git family F, compares git metrics between:
          - Treated: commits that have events from family F (e.g. lockfile changed)
          - Control: commits that only have git events (no family F involvement)

        Uses Cohen's d (effect size) to detect meaningful distribution shifts.
        This catches patterns like "dependency-changing commits touch more files"
        that co-occurrence correlation misses.

        Returns list of candidate pattern dicts (not yet stored).
        """
        min_support = self.params["min_support"]
        threshold = self.params["direction_threshold"]
        min_effect_size = self.params.get("min_effect_size", 0.3)

        commit_index = self._build_commit_index()

        # Map each signal to its commit SHA
        # Build: {(engine_id, metric): {commit_sha: deviation_value}}
        metric_deviations: dict[tuple, dict[str, float]] = defaultdict(dict)
        # Track which commits have events from each engine
        commits_by_engine: dict[str, set] = defaultdict(set)

        for s in signals:
            dev = s.get("deviation", {})
            if dev.get("degenerate", False) or dev.get("measure") is None:
                continue
            event_ref = s.get("event_ref", "")
            commit_sha = commit_index.get(event_ref)
            if not commit_sha:
                continue

            engine = s["engine_id"]
            metric = s["metric"]
            deviation = dev["measure"]

            metric_deviations[(engine, metric)][commit_sha] = deviation
            commits_by_engine[engine].add(commit_sha)

        # We need git + at least one non-git family
        git_commits = commits_by_engine.get("git", set())
        if not git_commits:
            return []

        non_git_engines = [e for e in commits_by_engine if e != "git"]
        if not non_git_engines:
            return []

        git_metrics = [(e, m) for (e, m) in metric_deviations if e == "git"]
        candidates = []

        for other_engine in non_git_engines:
            treated_commits = commits_by_engine[other_engine] & git_commits
            control_commits = git_commits - commits_by_engine[other_engine]

            min_control = max(min_support, 30)  # Need decent control group
            if len(treated_commits) < min_support or len(control_commits) < min_control:
                continue

            for git_key in git_metrics:
                git_devs = metric_deviations[git_key]

                treated_vals = [git_devs[c] for c in treated_commits if c in git_devs]
                control_vals = [git_devs[c] for c in control_commits if c in git_devs]

                if len(treated_vals) < min_support or len(control_vals) < min_support:
                    continue

                # Cohen's d effect size
                mean_t = mean(treated_vals)
                mean_c = mean(control_vals)
                std_t = pstdev(treated_vals)
                std_c = pstdev(control_vals)

                # Pooled standard deviation
                nt = len(treated_vals)
                nc = len(control_vals)
                if std_t == 0 and std_c == 0:
                    continue
                pooled_std = ((std_t ** 2 * nt + std_c ** 2 * nc) / (nt + nc)) ** 0.5
                if pooled_std == 0:
                    continue

                effect_size = (mean_t - mean_c) / pooled_std

                if abs(effect_size) < min_effect_size:
                    continue

                # Direction of the effect
                direction = "increased" if effect_size > 0 else "decreased"

                # Build fingerprint
                components = [
                    ("git", git_key[1], direction),
                    (other_engine, "_presence", "increased"),
                ]
                fingerprint = compute_fingerprint(components)

                # Collect signal_refs from treated commits
                signal_refs = []
                for c in sorted(treated_commits)[:20]:
                    for s in signals:
                        if commit_index.get(s.get("event_ref", "")) == c:
                            signal_refs.append(s.get("event_ref", ""))
                            if len(signal_refs) >= 20:
                                break
                    if len(signal_refs) >= 20:
                        break

                desc = (
                    f"When {other_engine} events occur, git.{git_key[1]} is "
                    f"systematically {direction} (effect size d={effect_size:.2f}, "
                    f"treated={nt}, control={nc})."
                )

                candidates.append({
                    "fingerprint": fingerprint,
                    "scope": "local",
                    "discovery_method": "statistical",
                    "alignment": "presence",
                    "pattern_type": "co_occurrence",
                    "sources": sorted(["git", other_engine]),
                    "metrics": sorted([git_key[1], f"{other_engine}_presence"]),
                    "description_statistical": desc,
                    "correlation_strength": round(effect_size, 4),
                    "raw_correlation": round(effect_size, 4),
                    "confidence_weight": min(1.0, min(nt, nc) / self.params.get("confidence_full_at", 30)),
                    "effect_size": round(effect_size, 4),
                    "accepted_via": "presence",
                    "occurrence_count": nt,
                    "signal_refs": signal_refs,
                    "first_seen": datetime.utcnow().isoformat() + "Z",
                    "last_seen": datetime.utcnow().isoformat() + "Z",
                    "confidence_tier": "statistical",
                    "confidence_status": "emerging",
                })

        if candidates:
            log.info("Presence-based discovery found %d candidate patterns", len(candidates))

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
            log.debug("Pearson returned 0.0: constant series (sx=%.4f, sy=%.4f, n=%d)",
                      sx, sy, n)
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
            "You are explaining a recurring code change pattern to a product manager.\n\n"
            f"Statistical finding: {pattern.get('description_statistical', '')}\n\n"
            "Signal explanations:\n"
            + "\n".join(signal_explanations)
            + "\n\n"
            "Describe what this pattern means in ONE plain-English sentence.\n"
            "Write for a non-technical audience — avoid jargon like 'correlation', 'deviation', 'stddev'.\n"
            "Do not add judgment, recommendations, or speculation.\n"
            "Describe only what is happening in practical terms."
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

        # Step 4: Co-occurrence + presence-based discovery (if no batch match)
        if not recognized:
            candidates = self._discover_cooccurrences(signals)
            candidates += self._discover_presence_patterns(signals)

            for candidate in candidates:
                # Check if this fingerprint already exists (any scope — local or community)
                existing = self.kb.get_pattern_by_fingerprint(candidate["fingerprint"])

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
