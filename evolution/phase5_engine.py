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

from evolution.friendly import risk_level, relative_change, metric_insight, friendly_pattern, pattern_risk_assessment
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


def _dedup_and_limit_patterns(patterns: list[dict], limit: int = 5) -> list[dict]:
    """Deduplicate patterns by (families, metrics, direction) and return top N.

    Groups patterns that share the same family+metric+direction key and
    keeps the one with the highest correlation strength from each group.
    """
    seen = {}
    for p in patterns:
        families = tuple(sorted(p.get("families") or p.get("sources") or []))
        metrics = tuple(sorted(p.get("metrics") or []))
        corr = p.get("correlation") or p.get("correlation_strength") or 0
        direction = "up" if corr >= 0 else "down"
        key = (families, metrics, direction)

        if key not in seen or abs(corr) > abs(
            seen[key].get("correlation") or seen[key].get("correlation_strength") or 0
        ):
            seen[key] = p

    # Sort by severity (critical first), then by absolute correlation as tiebreaker
    _sev_rank = {"positive": 0, "info": 1, "watch": 2, "concern": 3, "critical": 4}
    deduped = sorted(
        seen.values(),
        key=lambda p: (
            _sev_rank.get(pattern_risk_assessment(p)["severity"], 1),
            abs(p.get("correlation") or p.get("correlation_strength") or 0),
        ),
        reverse=True,
    )
    return deduped[:limit]


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

        from evolution.accepted import AcceptedDeviations
        self._accepted_devs = AcceptedDeviations(evo_dir)

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

    def _load_phase4_patterns(self, scope: str = None) -> list[dict]:
        """Load Phase 4 patterns, optionally filtered by scope.

        All non-expired patterns are returned regardless of confidence tier.
        Both community and locally-discovered patterns are treated as known
        once they pass validation and security scanning.
        """
        from evolution.knowledge_store import SQLiteKnowledgeStore
        db_path = self.phase4_path / "knowledge.db"
        if not db_path.exists():
            return []
        kb = SQLiteKnowledgeStore(db_path)
        patterns = kb.list_patterns(scope=scope)
        kb.close()
        return patterns


    # ─────────────────── 1. Significance Filter ───────────────────

    def _filter_significant(self, signals: list[dict]) -> list[dict]:
        """Select signals with deviation above the significance threshold.

        Per PHASE_5_DESIGN.md §3.1:
        - deviation exceeds ±threshold stddev
        - confidence is at least accumulating
        Skips degenerate signals (constant baselines) and None measures.
        Also filters: deprecated metrics, CI runner noise (deviation > 100K).
        """
        significant = []
        for s in signals:
            dev_info = s.get("deviation", {})
            if dev_info.get("degenerate", False):
                continue
            measure = dev_info.get("measure")
            if measure is None:
                continue
            # Skip deprecated metrics
            metric = s.get("metric_name", "")
            if metric == "direct_count":
                continue
            # Skip CI runner noise (extreme duration deviations are infrastructure, not code)
            if metric == "run_duration" and abs(measure) > 100000:
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
                    "support_count": ka.get("support_count", 0),
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
                    "repo_count": p.get("repo_count", 0),
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

    def _format_change(self, signal: dict, explanations: dict,
                       all_events: dict = None) -> dict:
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

        # Commit attribution — trace back to the triggering event
        trigger_commit = ""
        commit_message = ""
        observed_at = ""
        trigger_files = []
        if all_events and event_ref:
            event = all_events.get(event_ref, {})
            payload = event.get("payload", {})
            observed_at = Phase4Engine._extract_event_timestamp(event)

            if event.get("source_type") == "git":
                trigger_commit = payload.get("commit_hash", "")
                commit_message = payload.get("message", "")
                trigger_files = payload.get("files", [])
            else:
                trigger = payload.get("trigger", {})
                trigger_commit = trigger.get("commit_sha", "")
                commit_message = trigger.get("commit_message", "")

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
            "trigger_commit": trigger_commit,
            "commit_message": commit_message,
            "observed_at": observed_at,
            "trigger_files": trigger_files,
        }

    def _append_change_lines(self, lines: list, change: dict, indent: str = "") -> None:
        """Append formatted lines for a single change entry."""
        family_label = FAMILY_LABELS.get(change["family"], change["family"])
        metric_label = METRIC_LABELS.get(change["metric"], change["metric"])
        normal = change["normal"]
        current = change["current"]
        dev = change["deviation_stddev"]

        # Get the best baseline median
        median = normal["median"] if normal.get("mad", 0) > 0 else normal["mean"]

        # Risk label
        rl = risk_level(dev)
        risk_tag = f"  [{rl['label']}]"

        lines.append(f"{indent}{family_label} / {metric_label}{risk_tag}")

        # Natural-language comparison
        change_str = relative_change(current, median)
        lines.append(f"{indent}   {change_str.capitalize()} (now {self._fmt_value(change['metric'], current)})")

        # Insight
        direction = "up" if dev > 0 else "down"
        insight = metric_insight(change["metric"], direction)
        if insight:
            lines.append(f"{indent}   \u2192 {insight}")

    @staticmethod
    def _fmt_value(metric: str, value) -> str:
        """Format a metric value for display."""
        if metric in ("skip_rate", "fixable_ratio", "is_prerelease", "run_failed"):
            return f"{value:.1%}" if isinstance(value, (int, float)) and value <= 1.01 else f"{value:.4g}"
        if isinstance(value, float) and value < 1:
            return f"{value:.2f}"
        if isinstance(value, float):
            return f"{value:.4g}"
        return str(value)

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

        families_str = " and ".join(
            FAMILY_LABELS.get(f, f) for f in summary["families_affected"]
        )
        accepted_count = summary.get("accepted_changes", 0)
        if accepted_count:
            accepted_metrics = summary.get("accepted_metrics", [])
            accepted_str = ", ".join(accepted_metrics[:3])
            if len(accepted_metrics) > 3:
                accepted_str += f" +{len(accepted_metrics) - 3} more"
            lines.append(
                f"{summary['significant_changes']} significant changes detected "
                f"across {families_str} ({accepted_count} accepted — filtered: {accepted_str})."
            )
        else:
            lines.append(
                f"{summary['significant_changes']} significant changes detected "
                f"across {families_str}."
            )
        if n_groups and n_groups < summary["significant_changes"]:
            lines.append(f"(Grouped into {n_groups} trigger events)")
        lines.append("")

        # Render by event group if available, else flat changes
        if event_groups:
            for gi, group in enumerate(event_groups, 1):
                if group["signal_count"] > 1:
                    gfamilies_str = ", ".join(
                        FAMILY_LABELS.get(f, f) for f in group["families"]
                    )
                    lines.append(f"Event {gi} ({group['signal_count']} signals across {gfamilies_str}):")
                    for change in group["changes"]:
                        self._append_change_lines(lines, change, indent="  ")
                else:
                    self._append_change_lines(lines, group["primary"], indent="")
                lines.append("")
        else:
            for change in advisory["changes"]:
                self._append_change_lines(lines, change, indent="")
                lines.append("")

        # Known patterns (from KB, top 5)
        if advisory.get("pattern_matches"):
            shown = _dedup_and_limit_patterns(advisory["pattern_matches"])
            total = len(advisory["pattern_matches"])
            lines.append(f"KNOWN PATTERNS ({len(shown)} of {total})")
            lines.append("")
            for pm in shown:
                desc = friendly_pattern(pm)
                lines.append(f"  {desc}")
                lines.append("")

        # New patterns (discovered locally, top 5)
        if advisory.get("candidate_patterns"):
            shown = _dedup_and_limit_patterns(advisory["candidate_patterns"])
            total = len(advisory["candidate_patterns"])
            lines.append(f"NEW PATTERNS ({len(shown)} of {total})")
            lines.append("")
            for cp in shown:
                desc = friendly_pattern(cp)
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
        lines.append(f"{n} unusual change{'s' if n != 1 else ''} detected:")
        lines.append("")

        for i, change in enumerate(advisory["changes"], 1):
            metric_label = METRIC_LABELS.get(change["metric"], change["metric"])
            current = change["current"]
            normal_info = change["normal"]
            median = normal_info["median"] if normal_info.get("mad", 0) > 0 else normal_info["mean"]
            dev = change["deviation_stddev"]
            rl = risk_level(dev)

            change_str = relative_change(current, median)
            lines.append(f"{i}. {metric_label}: {change_str} [{rl['label']}]")

            direction = "up" if dev > 0 else "down"
            insight = metric_insight(change["metric"], direction)
            if insight:
                lines.append(f"   \u2192 {insight}")

        if advisory.get("pattern_matches"):
            shown = _dedup_and_limit_patterns(advisory["pattern_matches"], limit=3)
            lines.append("")
            for pm in shown:
                desc = friendly_pattern(pm)
                lines.append(f"Pattern: {desc}")

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
            commit_info = ""
            if c.get("trigger_commit"):
                sha_short = c["trigger_commit"][:8]
                msg = c.get("commit_message", "")
                # Use first line of commit message
                msg_line = msg.split("\n")[0] if msg else ""
                commit_info = f" [commit {sha_short}: {msg_line}]" if msg_line else f" [commit {sha_short}]"
            changes_text.append(
                f"- {family_label} / {metric_label}: normally {c['normal']['mean']:.4g}, "
                f"now {c['current']:.4g} ({abs(c['deviation_stddev']):.1f} stddev deviation)"
                f"{commit_info}"
            )

        evidence = advisory.get("evidence", {})
        evidence_text = []

        if evidence.get("commits"):
            evidence_text.append("COMMITS:")
            for commit in evidence["commits"][:10]:
                files = ", ".join(commit.get("files_changed", [])[:5])
                evidence_text.append(
                    f"  {commit['sha'][:8]} — {commit.get('message', '').split(chr(10))[0][:80]} "
                    f"(files: {files})"
                )

        if evidence.get("tests_impacted"):
            evidence_text.append("TESTS AFFECTED:")
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
            f"Development pattern shift detected in {scope} during "
            f"{period['from'][:10]} to {period['to'][:10]}.\n\n"
            f"DRIFT SIGNALS:\n"
            + "\n".join(changes_text)
            + "\n\n"
            + "\n".join(evidence_text)
            + "\n\n"
            "Investigate this drift:\n"
            "1. Which commit(s) introduced the pattern shift?\n"
            "2. Was this change intentional (new feature, refactor) or unintentional (AI drift, accidental complexity)?\n"
            "3. If unintentional, what is the minimal course correction?\n"
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

        Delegates to the shared diff_advisories() in evolution.history.
        """
        from evolution.history import diff_advisories
        return diff_advisories(before, after)

    def _format_verification_summary(self, before: dict, after: dict,
                                      diff: dict) -> str:
        """Format a human-readable verification report."""
        lines = []
        lines.append(f"Fix Verification Report — {after.get('scope', 'unknown')}")
        lines.append(f"Comparing: {before.get('advisory_id', '?')[:8]} \u2192 "
                      f"{after.get('advisory_id', '?')[:8]}")
        lines.append("")

        total_before = len(before.get("changes", []))
        resolved_count = len(diff["resolved"])
        new_count = len(diff["new"])

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
                lines.append(f"  \u2705 {family} / {metric} \u2014 back to normal")
            lines.append("")

        # Persisting
        if diff["persisting"]:
            lines.append("STILL UNUSUAL:")
            for p in diff["persisting"]:
                family = FAMILY_LABELS.get(p["family"], p["family"])
                metric = METRIC_LABELS.get(p["metric"], p["metric"])
                rl = risk_level(p["now_deviation"])
                trend = "improving" if p["improved"] else "not improving"
                lines.append(f"  \u26a0\ufe0f  {family} / {metric} \u2014 "
                             f"still {rl['description'].lower()} ({trend})")
            lines.append("")

        # New
        if diff["new"]:
            lines.append("NEW OBSERVATIONS:")
            for n in diff["new"]:
                family = FAMILY_LABELS.get(n["family"], n["family"])
                metric = METRIC_LABELS.get(n["metric"], n["metric"])
                rl = risk_level(n["deviation_stddev"])
                lines.append(f"  \U0001f535 {family} / {metric} \u2014 "
                             f"{rl['description'].lower()} (new)")
            lines.append("")

        # Regressions
        if diff["regressions"]:
            lines.append("REGRESSIONS:")
            for r in diff["regressions"]:
                family = FAMILY_LABELS.get(r["family"], r["family"])
                metric = METRIC_LABELS.get(r["metric"], r["metric"])
                rl = risk_level(r["deviation_stddev"])
                lines.append(f"  \U0001f534 {family} / {metric} \u2014 "
                             f"{rl['description'].lower()} (was normal before)")
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

    def _get_commit_list(self, all_events: dict) -> list[str]:
        """Extract ordered commit SHAs from events for range checking."""
        commits = []
        for eid, event in all_events.items():
            sha = None
            payload = event.get("payload", {})
            if event.get("source_type") == "git":
                sha = payload.get("commit_hash", "")
            else:
                trigger = payload.get("trigger", {})
                sha = trigger.get("commit_sha", "")
            if sha:
                commits.append((event.get("observed_at", ""), sha))
        # Sort by timestamp (oldest first)
        commits.sort(key=lambda x: x[0])
        return [sha for _, sha in commits]

    # ─────────────────── Latest Deviation Enrichment ───────────────────

    def _enrich_with_latest_deviation(self, changes: list[dict],
                                       all_signals: list[dict],
                                       all_events: dict) -> None:
        """Annotate each change with the latest signal's deviation for that metric.

        This lets downstream renderers distinguish transient historical triggers
        (metric returned to normal) from persistent ones (metric still elevated).

        Sets on each change:
          - latest_deviation: deviation measure from the most recent signal
          - latest_value: observed value from the most recent signal
          - latest_event_ref: event_ref of the most recent signal
          - is_latest_event: True if the change's trigger IS the latest event
        """
        for change in changes:
            family = change.get("family", "")
            metric = change.get("metric", "")

            # Find all signals matching this family+metric
            matching = [
                s for s in all_signals
                if s.get("engine_id") == family and s.get("metric") == metric
            ]
            if not matching:
                continue

            # Find the one with the latest event timestamp
            latest_signal = None
            latest_ts = ""
            for s in matching:
                ref = s.get("event_ref", "")
                event = all_events.get(ref)
                if not event:
                    continue
                ts = Phase4Engine._extract_event_timestamp(event) or ""
                if ts > latest_ts:
                    latest_ts = ts
                    latest_signal = s

            if latest_signal is None:
                continue

            dev = latest_signal.get("deviation", {}).get("measure")
            if dev is None:
                continue

            latest_ref = latest_signal.get("event_ref", "")
            change["latest_deviation"] = round(dev, 2)
            change["latest_value"] = latest_signal.get("observed")
            change["latest_event_ref"] = latest_ref
            change["is_latest_event"] = (change.get("event_ref", "") == latest_ref)

    # ─────────────────── Main Execution ───────────────────

    def run(self, scope: str = "evolution-engine") -> dict:
        """Execute the full Phase 5 pipeline.

        Returns the complete advisory report dict.
        """
        now = datetime.utcnow().isoformat() + "Z"

        # Clean up expired this-run acceptances
        self._accepted_devs.cleanup_expired(current_advisory_id="")

        # Load all data
        all_signals = self._load_signals()
        explanations = self._load_explanations()
        all_events = self._load_events()
        knowledge = self._load_phase4_knowledge()
        community_patterns = self._load_phase4_patterns(scope="community")
        local_patterns = self._load_phase4_patterns(scope="local")
        # Merge: all validated patterns (community + local) are "known"
        all_known_patterns = community_patterns + local_patterns

        if not all_signals:
            return {"status": "no_signals", "advisory": None}

        # Step 1: Significance filter
        significant = self._filter_significant(all_signals)

        if not significant:
            return {"status": "no_significant_changes", "advisory": None}

        # Step 2: Evidence collection
        evidence = self._collect_evidence(significant, all_events)

        # Step 3: Pattern matching
        # Known: promoted knowledge + all validated patterns (community + local)
        pattern_matches = self._match_patterns(significant, knowledge)
        known_matches = self._match_candidate_patterns(significant, all_known_patterns)
        pattern_matches.extend(known_matches)
        # Candidate patterns: none — all validated patterns are now "known"
        candidate_patterns = []

        # Step 4: Compile advisory
        # Build change list (with commit attribution)
        changes = [self._format_change(s, explanations, all_events) for s in significant]

        # Determine period from significant signal events only (not full history)
        sig_event_refs = {s.get("event_ref", "") for s in significant} - {""}
        sig_timestamps = [
            Phase4Engine._extract_event_timestamp(all_events[ref])
            for ref in sig_event_refs
            if ref in all_events and Phase4Engine._extract_event_timestamp(all_events[ref])
        ]
        period_from = min(sig_timestamps) if sig_timestamps else now
        period_to = max(sig_timestamps) if sig_timestamps else now

        # Deduplicate changes by family+metric (keep highest deviation)
        seen_changes = {}
        for c in changes:
            key = f"{c['family']}:{c['metric']}"
            if key not in seen_changes or abs(c["deviation_stddev"]) > abs(seen_changes[key]["deviation_stddev"]):
                seen_changes[key] = c
        changes = sorted(seen_changes.values(), key=lambda c: abs(c["deviation_stddev"]), reverse=True)

        # Enrich with latest deviation for historical trigger trend detection
        self._enrich_with_latest_deviation(changes, all_signals, all_events)

        # Filter out accepted deviations (scope-aware)
        commit_list = self._get_commit_list(all_events)
        filtered_changes = []
        accepted_changes = []
        for c in changes:
            commit_sha = c.get("trigger_commit", "")
            event_date = c.get("observed_at", "")
            if self._accepted_devs.is_accepted_in_context(
                c["family"], c["metric"],
                commit_sha=commit_sha,
                event_date=event_date,
                commit_list=commit_list,
            ):
                accepted_changes.append(c)
                continue
            filtered_changes.append(c)
        changes = filtered_changes

        if not changes:
            return {"status": "no_significant_changes", "advisory": None,
                    "accepted_count": len(accepted_changes)}

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
                "accepted_changes": len(accepted_changes),
                "accepted_metrics": [f"{c['family']}/{c['metric']}" for c in accepted_changes],
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

        # Compute overall advisory status rollup
        from evolution.friendly import advisory_status as _compute_status
        advisory["status"] = _compute_status(advisory)

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
