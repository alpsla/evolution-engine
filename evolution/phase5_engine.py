"""
Phase 5 Engine — Advisory & Evidence Layer

Compiles current signals, pattern context, and historical knowledge
into user-facing advisories with specific evidence for investigation.

Pipeline:
  1. Significance Filter — select signals above threshold
  2. Evidence Collector — trace signals → Phase 1 events → artifacts
  3. Pattern Matcher — query Phase 4 KB for known patterns
  4. Formatter — render for JSON, human summary, chat, investigation prompt

Conforms to PHASE_5_CONTRACT.md and PHASE_5_DESIGN.md.
"""

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from evolution.phase4_engine import (
    Phase4Engine,
    signals_to_components,
    compute_fingerprint,
)

# Signal files from Phase 2
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

# Family display names
FAMILY_LABELS = {
    "git": "Version Control",
    "ci": "CI / Build",
    "testing": "Testing",
    "dependency": "Dependencies",
    "schema": "API / Schema",
    "deployment": "Deployment",
    "config": "Configuration",
    "security": "Security",
}

# Metric human-readable names
METRIC_LABELS = {
    "files_touched": "Files Changed",
    "dispersion": "Change Dispersion",
    "change_locality": "Change Locality",
    "cochange_novelty_ratio": "Co-change Novelty",
    "run_duration": "Build Duration",
    "run_failed": "Build Failure",
    "total_tests": "Test Count",
    "skip_rate": "Skip Rate",
    "suite_duration": "Suite Duration",
    "dependency_count": "Total Dependencies",
    "max_depth": "Dependency Depth",
    "endpoint_count": "API Endpoints",
    "type_count": "API Types",
    "field_count": "API Fields",
    "schema_churn": "Schema Churn",
    "release_cadence_hours": "Release Cadence",
    "is_prerelease": "Pre-release",
    "asset_count": "Release Assets",
    "resource_count": "Resources",
    "resource_type_count": "Resource Types",
    "config_churn": "Config Churn",
    "vulnerability_count": "Vulnerabilities",
    "critical_count": "Critical Vulnerabilities",
    "fixable_ratio": "Fixable Ratio",
}


def _content_hash(data) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


class Phase5Engine:
    """Phase 5: Advisory & Evidence Layer."""

    def __init__(self, evo_dir: Path, significance_threshold: float = 1.5):
        self.evo_dir = evo_dir
        self.phase1_path = evo_dir / "events"
        self.phase2_path = evo_dir / "phase2"
        self.phase3_path = evo_dir / "phase3"
        self.phase4_path = evo_dir / "phase4"
        self.output_path = evo_dir / "phase5"
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.significance_threshold = significance_threshold

    # ─────────────────── Data Loading ───────────────────

    def _load_signals(self) -> list[dict]:
        """Load all Phase 2 signals."""
        all_signals = []
        for family, filename in SIGNAL_FILES.items():
            path = self.phase2_path / filename
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    all_signals.extend(json.load(f))
        return all_signals

    def _load_explanations(self) -> dict:
        """Load Phase 3 explanations indexed by compound key (event_ref:engine:metric).

        Primary lookup: {event_ref}:{engine_id}:{metric} — unique per signal.
        Fallback lookup: {engine_id}:{metric} — last explanation for that metric.
        """
        path = self.phase3_path / "explanations.json"
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            explanations = json.load(f)
        by_key = {}
        for e in explanations:
            ref = e.get("signal_ref", "")
            engine = e.get("engine_id", "")
            metric = e.get("details", {}).get("metric", "")
            # Primary: compound key (unique per signal)
            if ref and engine and metric:
                by_key[f"{ref}:{engine}:{metric}"] = e
            # Fallback: engine:metric (for last-resort lookup)
            fallback = f"{engine}:{metric}"
            if fallback not in by_key:
                by_key[fallback] = e
        return by_key

    def _load_events(self) -> dict:
        """Load Phase 1 events indexed by event_id."""
        events = {}
        if not self.phase1_path.exists():
            return events
        for p in self.phase1_path.glob("*.json"):
            with open(p, "r", encoding="utf-8") as f:
                ev = json.load(f)
            events[ev.get("event_id", p.stem)] = ev
        return events

    def _load_phase4_knowledge(self) -> list[dict]:
        """Load Phase 4 knowledge artifacts."""
        from evolution.knowledge_store import SQLiteKnowledgeStore
        db_path = self.phase4_path / "knowledge.db"
        if not db_path.exists():
            return []
        kb = SQLiteKnowledgeStore(db_path)
        knowledge = kb.list_knowledge(scope="local")
        kb.close()
        return knowledge

    def _load_phase4_patterns(self) -> list[dict]:
        """Load Phase 4 candidate patterns."""
        from evolution.knowledge_store import SQLiteKnowledgeStore
        db_path = self.phase4_path / "knowledge.db"
        if not db_path.exists():
            return []
        kb = SQLiteKnowledgeStore(db_path)
        patterns = kb.list_patterns()
        kb.close()
        return patterns

    # ─────────────────── 1. Significance Filter ───────────────────

    def _filter_significant(self, signals: list[dict]) -> list[dict]:
        """Select signals with deviation above the significance threshold.

        Per PHASE_5_DESIGN.md §3.1:
        - deviation exceeds ±threshold stddev
        - confidence is at least accumulating
        Skips degenerate signals (constant baselines) and None measures.
        """
        significant = []
        for s in signals:
            dev_info = s.get("deviation", {})
            if dev_info.get("degenerate", False):
                continue
            measure = dev_info.get("measure")
            if measure is None:
                continue
            if abs(measure) >= self.significance_threshold:
                significant.append(s)
        return significant

    # ─────────────────── 2. Evidence Collector ───────────────────

    def _collect_evidence(self, significant_signals: list[dict],
                          all_events: dict) -> dict:
        """Trace significant signals back to Phase 1 events and extract artifacts.

        Returns the Evidence Package shape from PHASE_5_CONTRACT.md §5.
        """
        commits = []
        files_affected = []
        tests_impacted = []
        deps_changed = []
        timeline = []
        seen_commits = set()
        seen_files = set()

        for signal in significant_signals:
            event_ref = signal.get("event_ref", "")
            event = all_events.get(event_ref)
            if not event:
                continue

            family = event.get("source_family", event.get("source_type", "unknown"))
            payload = event.get("payload", {})
            event_time = Phase4Engine._extract_event_timestamp(event)

            # Timeline entry
            metric_label = METRIC_LABELS.get(signal["metric"], signal["metric"])
            dev = signal["deviation"]["measure"]
            direction = "above" if dev > 0 else "below"
            timeline.append({
                "timestamp": event_time,
                "family": family,
                "event": f"{metric_label}: {signal['observed']:.4g} ({abs(dev):.1f} stddev {direction} normal)",
            })

            # Family-specific evidence extraction
            if family == "version_control":
                sha = event.get("attestation", {}).get("commit_hash", "")
                if sha and sha not in seen_commits:
                    seen_commits.add(sha)
                    commits.append({
                        "sha": sha,
                        "message": payload.get("message", ""),
                        "author": payload.get("author", ""),
                        "timestamp": event_time,
                        "files_changed": payload.get("files", []),
                    })
                    for f in payload.get("files", []):
                        if f not in seen_files:
                            seen_files.add(f)
                            files_affected.append({
                                "path": f,
                                "change_type": "modified",
                                "first_seen_in": sha,
                            })

            elif family == "testing":
                summary = payload.get("summary", {})
                cases = payload.get("cases", [])
                for case in cases:
                    if case.get("status") in ("failed", "errored"):
                        tests_impacted.append({
                            "name": case.get("name", "unknown"),
                            "status_before": "passed",
                            "status_now": case.get("status", "failed"),
                            "since_commit": payload.get("trigger", {}).get("commit_sha", ""),
                        })

            elif family == "dependency":
                deps = payload.get("dependencies", [])
                for dep in deps:
                    if dep.get("direct", False):
                        deps_changed.append({
                            "name": dep.get("name", ""),
                            "change": "present",
                            "version": dep.get("version", ""),
                        })

            elif family == "security":
                findings = payload.get("findings", [])
                for finding in findings:
                    if finding.get("severity") in ("critical", "high"):
                        timeline.append({
                            "timestamp": event_time,
                            "family": "security",
                            "event": f"Vulnerability {finding.get('id', 'unknown')}: "
                                     f"{finding.get('severity', '')} in {finding.get('package', '')}",
                        })

        # Sort timeline chronologically
        timeline.sort(key=lambda t: t.get("timestamp", ""))

        # Deduplicate timeline: keep first occurrence per (family, event_text)
        seen_timeline = set()
        deduped_timeline = []
        for t in timeline:
            key = (t["family"], t["event"])
            if key not in seen_timeline:
                seen_timeline.add(key)
                deduped_timeline.append(t)

        # Cap lists for readability
        return {
            "commits": commits[:20],
            "files_affected": files_affected[:50],
            "tests_impacted": tests_impacted[:30],
            "dependencies_changed": deps_changed[:30],
            "timeline": deduped_timeline[:50],
        }

    # ─────────────────── 3. Pattern Matcher ───────────────────

    def _match_patterns(self, significant_signals: list[dict],
                        knowledge: list[dict]) -> list[dict]:
        """Match current signal fingerprint against Phase 4 knowledge artifacts."""
        if not knowledge or not significant_signals:
            return []

        # Build current fingerprint components
        components = signals_to_components(significant_signals, threshold=1.0)
        if not components:
            return []

        # Check each knowledge artifact for overlap
        matches = []
        current_families = set(c[0] for c in components)
        current_metrics = set(c[1] for c in components)

        for ka in knowledge:
            ka_sources = set(ka.get("sources", []))
            ka_metrics = set(ka.get("metrics", []))

            # Match if the knowledge artifact's sources and metrics overlap
            # with the current significant signals
            source_overlap = ka_sources & current_families
            metric_overlap = ka_metrics & current_metrics

            if source_overlap and metric_overlap:
                matches.append({
                    "knowledge_id": ka.get("knowledge_id", ""),
                    "pattern_type": ka.get("pattern_type", ""),
                    "confidence": "approved",
                    "seen_count": ka.get("support_count", 0),
                    "sources": ka.get("sources", []),
                    "metrics": ka.get("metrics", []),
                    "description": (
                        ka.get("description_semantic")
                        or ka.get("description_statistical", "")
                    ),
                })

        return matches

    # ─────────────────── 3b. Candidate Pattern Matcher ───────────────────

    def _match_candidate_patterns(self, significant_signals: list[dict],
                                   patterns: list[dict]) -> list[dict]:
        """Match current signals against Phase 4 candidate patterns (not yet promoted).

        Same overlap logic as _match_patterns() but for raw correlation patterns.
        """
        if not patterns or not significant_signals:
            return []

        components = signals_to_components(significant_signals, threshold=1.0)
        if not components:
            return []

        current_families = set(c[0] for c in components)
        current_metrics = set(c[1] for c in components)

        matches = []
        for p in patterns:
            p_families = set(p.get("sources", []))
            p_metrics = set(p.get("metrics", []))

            if p_families & current_families and p_metrics & current_metrics:
                matches.append({
                    "pattern_id": p.get("pattern_id", p.get("fingerprint", "")),
                    "correlation": p.get("correlation_strength", 0),
                    "families": sorted(p_families & current_families),
                    "metrics": sorted(p_metrics & current_metrics),
                    "description": (
                        p.get("description_semantic")
                        or p.get("description_statistical", "")
                    ),
                    "support_count": p.get("occurrence_count", 0),
                })

        return matches

    # ─────────────────── 3c. Event Grouping ───────────────────

    def _group_by_trigger_event(self, changes: list[dict]) -> list[dict]:
        """Group changes that share the same trigger event (event_ref).

        A single large commit can trigger signals across multiple families.
        Grouping shows them as one event with sub-metrics instead of N
        independent anomalies.

        Returns list of event groups, each with:
          - event_ref: the shared event reference
          - primary: the change with highest deviation
          - families: list of families involved
          - changes: all changes in this group
          - signal_count: number of signals
        """
        groups = defaultdict(list)
        ungrouped = []

        for change in changes:
            ref = change.get("event_ref", "")
            if ref:
                groups[ref].append(change)
            else:
                ungrouped.append(change)

        result = []
        for event_ref, group_changes in groups.items():
            # Sort by absolute deviation descending
            group_changes.sort(key=lambda c: abs(c["deviation_stddev"]), reverse=True)
            primary = group_changes[0]
            families = sorted(set(c["family"] for c in group_changes))
            result.append({
                "event_ref": event_ref,
                "primary": primary,
                "families": families,
                "changes": group_changes,
                "signal_count": len(group_changes),
            })

        # Sort groups by primary deviation
        result.sort(key=lambda g: abs(g["primary"]["deviation_stddev"]), reverse=True)

        # Append ungrouped as singleton groups
        for change in ungrouped:
            result.append({
                "event_ref": None,
                "primary": change,
                "families": [change["family"]],
                "changes": [change],
                "signal_count": 1,
            })

        return result

    # ─────────────────── 4. Formatters ───────────────────

    def _format_change(self, signal: dict, explanations: dict) -> dict:
        """Format a single significant signal as a change entry."""
        dev = signal["deviation"]["measure"]
        baseline = signal["baseline"]
        event_ref = signal.get("event_ref", "")
        engine_id = signal["engine_id"]
        metric = signal["metric"]

        # Get Phase 3 explanation via compound key (event_ref:engine:metric)
        explanation = ""
        exp = explanations.get(f"{event_ref}:{engine_id}:{metric}")
        if not exp:
            exp = explanations.get(f"{engine_id}:{metric}")
        if exp:
            explanation = exp.get("summary", "")

        return {
            "family": engine_id,
            "metric": metric,
            "normal": {
                "mean": round(baseline["mean"], 4),
                "stddev": round(baseline["stddev"], 4),
                "median": round(baseline.get("median", baseline["mean"]), 4),
                "mad": round(baseline.get("mad", 0), 4),
            },
            "current": signal["observed"],
            "deviation_stddev": round(dev, 2),
            "deviation_unit": signal["deviation"].get("unit", "modified_zscore"),
            "description": explanation,
            "event_ref": event_ref,
        }

    def _append_change_lines(self, lines: list, change: dict, indent: str = "") -> None:
        """Append formatted lines for a single change entry."""
        family_label = FAMILY_LABELS.get(change["family"], change["family"])
        metric_label = METRIC_LABELS.get(change["metric"], change["metric"])
        normal = change["normal"]
        current = change["current"]
        dev = change["deviation_stddev"]
        unit = change.get("deviation_unit", "modified_zscore")
        direction = "above" if dev > 0 else "below"

        lines.append(f"{indent}{family_label} / {metric_label}")

        # Use median/MAD when available, fall back to mean/stddev
        if normal.get("mad", 0) > 0:
            normal_str = f"{normal['median']:.4g}"
            spread_str = f"MAD {normal['mad']:.2f}"
        else:
            normal_str = f"{normal['mean']:.4g}"
            spread_str = f"+/- {normal['stddev']:.2f}"

        # Format current value
        if change["metric"] in ("skip_rate", "fixable_ratio", "is_prerelease", "run_failed"):
            current_str = f"{current:.1%}" if current < 1.01 else f"{current:.4g}"
        elif isinstance(current, float) and current < 1:
            current_str = f"{current:.2f}"
        else:
            current_str = f"{current:.4g}"

        unit_label = {"modified_zscore": "MAD", "iqr_normalized": "IQR", "degenerate": "deg"}.get(unit, "std")
        lines.append(f"{indent}   Normally: {normal_str} ({spread_str})")
        lines.append(f"{indent}   Now:      {current_str}  ({abs(dev):.1f} {unit_label} {direction} normal)")

    def _format_human_summary(self, advisory: dict) -> str:
        """Render advisory as human-readable 'normal vs now' summary.

        Per PHASE_5_DESIGN.md §4.
        """
        lines = []
        lines.append(f"Evolution Advisory — {advisory['scope']}")
        lines.append(f"Period: {advisory['period']['from'][:10]} to {advisory['period']['to'][:10]}")
        lines.append("")

        summary = advisory["summary"]
        event_groups = advisory.get("event_groups", [])
        n_groups = len(event_groups)

        lines.append(f"{summary['significant_changes']} significant changes detected "
                     f"across {', '.join(summary['families_affected'])}.")
        if n_groups and n_groups < summary["significant_changes"]:
            lines.append(f"(Grouped into {n_groups} trigger events)")
        lines.append("")

        # Render by event group if available, else flat changes
        if event_groups:
            for gi, group in enumerate(event_groups, 1):
                if group["signal_count"] > 1:
                    families_str = ", ".join(
                        FAMILY_LABELS.get(f, f) for f in group["families"]
                    )
                    lines.append(f"Event {gi} ({group['signal_count']} signals across {families_str}):")
                    for change in group["changes"]:
                        self._append_change_lines(lines, change, indent="  ")
                else:
                    self._append_change_lines(lines, group["primary"], indent="")
                lines.append("")
        else:
            for change in advisory["changes"]:
                self._append_change_lines(lines, change, indent="")
                lines.append("")

        # Pattern matches
        if advisory.get("pattern_matches"):
            lines.append("PATTERN RECOGNITION")
            lines.append("")
            for pm in advisory["pattern_matches"]:
                lines.append(f"  These changes match a known pattern (seen {pm['seen_count']} times):")
                lines.append(f"  {pm['description']}")
                lines.append("")

        # Candidate patterns
        if advisory.get("candidate_patterns"):
            lines.append("CANDIDATE PATTERNS (not yet promoted)")
            lines.append("")
            for cp in advisory["candidate_patterns"]:
                r = cp.get("correlation", 0)
                families_str = ", ".join(cp.get("families", []))
                desc = cp.get("description", "")
                lines.append(f"  r={r:.2f} across {families_str}")
                if desc:
                    lines.append(f"  {desc}")
                lines.append("")

        # Evidence summary
        evidence = advisory.get("evidence", {})
        parts = []
        if evidence.get("commits"):
            parts.append(f"{len(evidence['commits'])} commits")
        if evidence.get("files_affected"):
            parts.append(f"{len(evidence['files_affected'])} files")
        if evidence.get("tests_impacted"):
            parts.append(f"{len(evidence['tests_impacted'])} failing tests")
        if evidence.get("dependencies_changed"):
            parts.append(f"{len(evidence['dependencies_changed'])} dependencies")
        if parts:
            lines.append(f"Evidence: {', '.join(parts)}")

        return "\n".join(lines)

    def _format_chat(self, advisory: dict) -> str:
        """Render advisory for chat platforms (Telegram, Slack, Discord).

        Per PHASE_5_DESIGN.md §6.
        """
        lines = []
        lines.append(f"Evolution Report — {advisory['scope']}")
        lines.append("")

        n = advisory["summary"]["significant_changes"]
        lines.append(f"{n} thing{'s' if n != 1 else ''} look{'s' if n == 1 else ''} "
                     f"different from your system's normal behavior:")
        lines.append("")

        for i, change in enumerate(advisory["changes"], 1):
            family_label = FAMILY_LABELS.get(change["family"], change["family"])
            metric_label = METRIC_LABELS.get(change["metric"], change["metric"])
            current = change["current"]
            normal_info = change["normal"]
            normal = normal_info["median"] if normal_info.get("mad", 0) > 0 else normal_info["mean"]
            dev = abs(change["deviation_stddev"])

            if change["metric"] in ("failure_rate", "skip_rate", "fixable_ratio"):
                lines.append(f"{i}. {family_label}: {metric_label} "
                             f"{normal:.1%} -> {current:.1%} ({dev:.1f}x stddev)")
            elif isinstance(current, float) and current < 1:
                lines.append(f"{i}. {family_label}: {metric_label} "
                             f"{normal:.2f} -> {current:.2f} ({dev:.1f}x stddev)")
            else:
                lines.append(f"{i}. {family_label}: {metric_label} "
                             f"{normal:.1f} -> {current:.4g} ({dev:.1f}x stddev)")

        if advisory.get("pattern_matches"):
            lines.append("")
            for pm in advisory["pattern_matches"]:
                lines.append(f"This matches a known pattern seen {pm['seen_count']} times:")
                lines.append(f'"{pm["description"]}"')

        evidence = advisory.get("evidence", {})
        parts = []
        if evidence.get("commits"):
            parts.append(f"{len(evidence['commits'])} commits")
        if evidence.get("tests_impacted"):
            parts.append(f"{len(evidence['tests_impacted'])} failing tests")
        if evidence.get("dependencies_changed"):
            parts.append(f"{len(evidence['dependencies_changed'])} deps")
        if parts:
            lines.append("")
            lines.append(f"Evidence: {', '.join(parts)}")

        return "\n".join(lines)

    def _format_investigation_prompt(self, advisory: dict) -> str:
        """Generate a pre-built investigation prompt for AI assistants.

        Per PHASE_5_DESIGN.md §5.3.
        """
        period = advisory["period"]
        scope = advisory["scope"]

        changes_text = []
        for c in advisory["changes"]:
            family_label = FAMILY_LABELS.get(c["family"], c["family"])
            metric_label = METRIC_LABELS.get(c["metric"], c["metric"])
            changes_text.append(
                f"- {family_label} / {metric_label}: normally {c['normal']['mean']:.4g}, "
                f"now {c['current']:.4g} ({abs(c['deviation_stddev']):.1f} stddev deviation)"
            )

        evidence = advisory.get("evidence", {})
        evidence_text = []

        if evidence.get("commits"):
            evidence_text.append("COMMITS:")
            for commit in evidence["commits"][:10]:
                files = ", ".join(commit.get("files_changed", [])[:5])
                evidence_text.append(
                    f"  {commit['sha'][:8]} — {commit.get('message', '')[:80]} "
                    f"(files: {files})"
                )

        if evidence.get("tests_impacted"):
            evidence_text.append("FAILING TESTS:")
            for test in evidence["tests_impacted"][:10]:
                evidence_text.append(f"  {test['name']} — {test['status_now']}")

        if evidence.get("dependencies_changed"):
            evidence_text.append("DEPENDENCIES:")
            for dep in evidence["dependencies_changed"][:10]:
                evidence_text.append(f"  {dep['name']} {dep['version']} ({dep['change']})")

        if evidence.get("timeline"):
            evidence_text.append("TIMELINE:")
            for t in evidence["timeline"][:15]:
                evidence_text.append(f"  {t['timestamp'][:16]} [{t['family']}] {t['event']}")

        prompt = (
            f"Here is a structural analysis of {scope} over the period "
            f"{period['from'][:10]} to {period['to'][:10]}.\n\n"
            f"CHANGES DETECTED:\n"
            + "\n".join(changes_text)
            + "\n\n"
            + "\n".join(evidence_text)
            + "\n\n"
            "Based on this evidence:\n"
            "1. What is the most likely root cause of the observed changes?\n"
            "2. Which specific files should be reviewed first?\n"
            "3. Are there any dependency or configuration changes that may explain the test failures?\n"
        )

        return prompt

    # ─────────────────── 5. Fix Verification (Advisory Diff) ───────────────────

    def _load_previous_advisory(self, advisory_path: Path) -> dict:
        """Load a previous advisory JSON for comparison."""
        with open(advisory_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _diff_advisories(self, before: dict, after: dict) -> dict:
        """
        Compare two advisories and classify each change.

        Returns a verification report with:
          - resolved: changes that returned to normal
          - persisting: changes still flagged
          - new: changes not present in the original advisory
          - regression: metrics that were normal before but now deviate
        """
        # Index "before" changes by family:metric
        before_changes = {}
        for c in before.get("changes", []):
            key = f"{c['family']}:{c['metric']}"
            before_changes[key] = c

        # Index "after" changes by family:metric
        after_changes = {}
        for c in after.get("changes", []):
            key = f"{c['family']}:{c['metric']}"
            after_changes[key] = c

        resolved = []
        persisting = []
        new_changes = []
        regressions = []

        # Check what was flagged before
        for key, before_change in before_changes.items():
            if key in after_changes:
                after_change = after_changes[key]
                # Still flagged — check if it improved
                before_dev = abs(before_change["deviation_stddev"])
                after_dev = abs(after_change["deviation_stddev"])
                improvement = before_dev - after_dev

                persisting.append({
                    **after_change,
                    "was_deviation": before_change["deviation_stddev"],
                    "now_deviation": after_change["deviation_stddev"],
                    "improvement": round(improvement, 2),
                    "improved": improvement > 0,
                })
            else:
                # No longer flagged — resolved!
                resolved.append({
                    **before_change,
                    "was_deviation": before_change["deviation_stddev"],
                    "resolution": "returned_to_normal",
                })

        # Check for new changes not in the original
        for key, after_change in after_changes.items():
            if key not in before_changes:
                new_changes.append({
                    **after_change,
                    "classification": "new_observation",
                })

        # Detect regressions: metrics that were normal before but
        # now deviate in the opposite direction or newly appear
        for nc in new_changes:
            # If this metric existed in the before advisory's period
            # but was within normal range, it's a regression
            nc["classification"] = "regression" if any(
                nc["family"] == bc["family"] for bc in before.get("changes", [])
            ) else "new_observation"
            if nc["classification"] == "regression":
                regressions.append(nc)

        return {
            "resolved": resolved,
            "persisting": persisting,
            "new": [n for n in new_changes if n["classification"] != "regression"],
            "regressions": regressions,
        }

    def _format_verification_summary(self, before: dict, after: dict,
                                      diff: dict) -> str:
        """Format a human-readable verification report."""
        lines = []
        lines.append(f"Fix Verification Report — {after.get('scope', 'unknown')}")
        lines.append(f"Comparing: {before.get('advisory_id', '?')[:8]} → "
                      f"{after.get('advisory_id', '?')[:8]}")
        lines.append("")

        total_before = len(before.get("changes", []))
        resolved_count = len(diff["resolved"])
        persisting_count = len(diff["persisting"])
        new_count = len(diff["new"])
        regression_count = len(diff["regressions"])

        # Summary line
        if resolved_count == total_before and new_count == 0:
            lines.append("ALL ISSUES RESOLVED. No new issues detected.")
        elif resolved_count > 0:
            lines.append(f"{resolved_count} of {total_before} flagged changes resolved.")
        else:
            lines.append(f"No changes resolved ({total_before} still active).")

        lines.append("")

        # Resolved
        if diff["resolved"]:
            lines.append("RESOLVED:")
            for r in diff["resolved"]:
                family = FAMILY_LABELS.get(r["family"], r["family"])
                metric = METRIC_LABELS.get(r["metric"], r["metric"])
                lines.append(f"  ✅ {family} / {metric} — was {abs(r['was_deviation']):.1f}x "
                             f"stddev, now within normal range")
            lines.append("")

        # Persisting
        if diff["persisting"]:
            lines.append("PERSISTING:")
            for p in diff["persisting"]:
                family = FAMILY_LABELS.get(p["family"], p["family"])
                metric = METRIC_LABELS.get(p["metric"], p["metric"])
                direction = "improved" if p["improved"] else "unchanged/worsened"
                lines.append(f"  ⚠️  {family} / {metric} — was {abs(p['was_deviation']):.1f}x, "
                             f"now {abs(p['now_deviation']):.1f}x stddev ({direction})")
            lines.append("")

        # New
        if diff["new"]:
            lines.append("NEW OBSERVATIONS:")
            for n in diff["new"]:
                family = FAMILY_LABELS.get(n["family"], n["family"])
                metric = METRIC_LABELS.get(n["metric"], n["metric"])
                lines.append(f"  🔵 {family} / {metric} — "
                             f"{abs(n['deviation_stddev']):.1f}x stddev "
                             f"(not present in previous advisory)")
            lines.append("")

        # Regressions
        if diff["regressions"]:
            lines.append("REGRESSIONS:")
            for r in diff["regressions"]:
                family = FAMILY_LABELS.get(r["family"], r["family"])
                metric = METRIC_LABELS.get(r["metric"], r["metric"])
                lines.append(f"  🔴 {family} / {metric} — "
                             f"{abs(r['deviation_stddev']):.1f}x stddev "
                             f"(was normal before, now deviating)")
            lines.append("")

        # Score
        if total_before > 0:
            resolution_rate = resolved_count / total_before * 100
            lines.append(f"Resolution rate: {resolution_rate:.0f}% "
                         f"({resolved_count}/{total_before})")

        return "\n".join(lines)

    def verify(self, scope: str, previous_advisory_path: str) -> dict:
        """
        Run Phase 5 and compare against a previous advisory.

        This is the Fix Verification Loop:
        1. Re-run the full pipeline to get current state
        2. Load the previous advisory
        3. Diff: resolved / persisting / new / regression
        4. Generate verification report

        Args:
            scope: Repository scope name
            previous_advisory_path: Path to the previous advisory.json

        Returns:
            dict with verification report, current advisory, and diff
        """
        # Step 1: Run current advisory
        current_result = self.run(scope=scope)
        if current_result["status"] != "complete":
            return {
                "status": "no_current_data",
                "message": "Current pipeline produced no significant changes.",
                "verification": {
                    "resolved": [],
                    "persisting": [],
                    "new": [],
                    "regressions": [],
                },
            }

        current_advisory = current_result["advisory"]

        # Step 2: Load previous advisory
        prev_path = Path(previous_advisory_path)
        if not prev_path.exists():
            return {
                "status": "no_previous_advisory",
                "message": f"Previous advisory not found: {previous_advisory_path}",
                "advisory": current_advisory,
            }

        previous_advisory = self._load_previous_advisory(prev_path)

        # Step 3: Diff
        diff = self._diff_advisories(previous_advisory, current_advisory)

        # Step 4: Format verification report
        verification_text = self._format_verification_summary(
            previous_advisory, current_advisory, diff
        )

        # Step 5: Save verification outputs
        verification_data = {
            "verification_id": _content_hash({
                "before": previous_advisory.get("advisory_id"),
                "after": current_advisory.get("advisory_id"),
            }),
            "before_advisory_id": previous_advisory.get("advisory_id"),
            "after_advisory_id": current_advisory.get("advisory_id"),
            "scope": scope,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "summary": {
                "total_before": len(previous_advisory.get("changes", [])),
                "resolved": len(diff["resolved"]),
                "persisting": len(diff["persisting"]),
                "new": len(diff["new"]),
                "regressions": len(diff["regressions"]),
                "resolution_rate": (
                    len(diff["resolved"]) / len(previous_advisory.get("changes", []))
                    if previous_advisory.get("changes") else 0
                ),
            },
            "resolved": diff["resolved"],
            "persisting": diff["persisting"],
            "new": diff["new"],
            "regressions": diff["regressions"],
        }

        with open(self.output_path / "verification.json", "w", encoding="utf-8") as f:
            json.dump(verification_data, f, indent=2)
        with open(self.output_path / "verification.txt", "w", encoding="utf-8") as f:
            f.write(verification_text)

        return {
            "status": "verified",
            "advisory": current_advisory,
            "verification": verification_data,
            "verification_text": verification_text,
            "formats": {
                **current_result.get("formats", {}),
                "verification_json": str(self.output_path / "verification.json"),
                "verification_text": str(self.output_path / "verification.txt"),
            },
        }

    # ─────────────────── Main Execution ───────────────────

    def run(self, scope: str = "evolution-engine") -> dict:
        """Execute the full Phase 5 pipeline.

        Returns the complete advisory report dict.
        """
        now = datetime.utcnow().isoformat() + "Z"

        # Load all data
        all_signals = self._load_signals()
        explanations = self._load_explanations()
        all_events = self._load_events()
        knowledge = self._load_phase4_knowledge()
        patterns = self._load_phase4_patterns()

        if not all_signals:
            return {"status": "no_signals", "advisory": None}

        # Step 1: Significance filter
        significant = self._filter_significant(all_signals)

        if not significant:
            return {"status": "no_significant_changes", "advisory": None}

        # Step 2: Evidence collection
        evidence = self._collect_evidence(significant, all_events)

        # Step 3: Pattern matching (promoted knowledge + candidates)
        pattern_matches = self._match_patterns(significant, knowledge)
        candidate_patterns = self._match_candidate_patterns(significant, patterns)

        # Step 4: Compile advisory
        # Determine period from events
        timestamps = [e.get("observed_at", "") for e in all_events.values() if e.get("observed_at")]
        period_from = min(timestamps) if timestamps else now
        period_to = max(timestamps) if timestamps else now

        # Build change list
        changes = [self._format_change(s, explanations) for s in significant]

        # Deduplicate changes by family+metric (keep highest deviation)
        seen_changes = {}
        for c in changes:
            key = f"{c['family']}:{c['metric']}"
            if key not in seen_changes or abs(c["deviation_stddev"]) > abs(seen_changes[key]["deviation_stddev"]):
                seen_changes[key] = c
        changes = sorted(seen_changes.values(), key=lambda c: abs(c["deviation_stddev"]), reverse=True)

        # Families affected
        families_affected = sorted(set(c["family"] for c in changes))

        # Event grouping — cluster signals by trigger event
        event_groups = self._group_by_trigger_event(changes)

        # Build evidence package
        evidence_package = {
            "evidence_id": _content_hash(evidence),
            "advisory_ref": None,  # Will be set after advisory_id is computed
            **evidence,
        }

        # Build advisory
        advisory = {
            "advisory_id": None,
            "scope": scope,
            "generated_at": now,
            "period": {"from": period_from, "to": period_to},
            "summary": {
                "significant_changes": len(changes),
                "families_affected": families_affected,
                "known_patterns_matched": len(pattern_matches),
                "candidate_patterns_matched": len(candidate_patterns),
                "event_groups": len(event_groups),
                "new_observations": max(0, len(changes) - len(pattern_matches) - len(candidate_patterns)),
            },
            "changes": changes,
            "event_groups": event_groups,
            "pattern_matches": pattern_matches,
            "candidate_patterns": candidate_patterns,
            "evidence": evidence_package,
        }

        advisory["advisory_id"] = _content_hash({
            "scope": scope, "period": advisory["period"],
            "changes_count": len(changes),
        })
        evidence_package["advisory_ref"] = advisory["advisory_id"]

        # Generate formatted outputs
        human_summary = self._format_human_summary(advisory)
        chat_format = self._format_chat(advisory)
        investigation_prompt = self._format_investigation_prompt(advisory)

        # Save all outputs
        with open(self.output_path / "advisory.json", "w", encoding="utf-8") as f:
            json.dump(advisory, f, indent=2)
        with open(self.output_path / "evidence.json", "w", encoding="utf-8") as f:
            json.dump(evidence_package, f, indent=2)
        with open(self.output_path / "summary.txt", "w", encoding="utf-8") as f:
            f.write(human_summary)
        with open(self.output_path / "chat.txt", "w", encoding="utf-8") as f:
            f.write(chat_format)
        with open(self.output_path / "investigation_prompt.txt", "w", encoding="utf-8") as f:
            f.write(investigation_prompt)

        return {
            "status": "complete",
            "advisory": advisory,
            "formats": {
                "json": str(self.output_path / "advisory.json"),
                "human": str(self.output_path / "summary.txt"),
                "chat": str(self.output_path / "chat.txt"),
                "investigation": str(self.output_path / "investigation_prompt.txt"),
            },
            "human_summary": human_summary,
            "chat_format": chat_format,
            "investigation_prompt": investigation_prompt,
        }
