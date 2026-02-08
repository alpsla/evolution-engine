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
    "job_count": "Job Count",
    "failure_rate": "Failure Rate",
    "total_tests": "Test Count",
    "skip_rate": "Skip Rate",
    "suite_duration": "Suite Duration",
    "dependency_count": "Total Dependencies",
    "direct_count": "Direct Dependencies",
    "max_depth": "Dependency Depth",
    "endpoint_count": "API Endpoints",
    "type_count": "API Types",
    "field_count": "API Fields",
    "schema_churn": "Schema Churn",
    "deploy_duration": "Deploy Duration",
    "is_rollback": "Rollback",
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
        """Load Phase 3 explanations indexed by signal_ref and engine:metric."""
        path = self.phase3_path / "explanations.json"
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            explanations = json.load(f)
        by_key = {}
        for e in explanations:
            ref = e.get("signal_ref")
            if ref:
                by_key[ref] = e
            key = f"{e.get('engine_id')}:{e.get('details', {}).get('metric', '')}"
            if key not in by_key:
                by_key[key] = e
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
        """
        significant = []
        for s in signals:
            dev = abs(s["deviation"]["measure"])
            if dev >= self.significance_threshold:
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
            observed_at = event.get("observed_at", "")

            # Timeline entry
            metric_label = METRIC_LABELS.get(signal["metric"], signal["metric"])
            dev = signal["deviation"]["measure"]
            direction = "above" if dev > 0 else "below"
            timeline.append({
                "timestamp": observed_at,
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
                        "timestamp": observed_at,
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
                            "timestamp": observed_at,
                            "family": "security",
                            "event": f"Vulnerability {finding.get('id', 'unknown')}: "
                                     f"{finding.get('severity', '')} in {finding.get('package', '')}",
                        })

        # Sort timeline chronologically
        timeline.sort(key=lambda t: t.get("timestamp", ""))

        # Cap lists for readability
        return {
            "commits": commits[:20],
            "files_affected": files_affected[:50],
            "tests_impacted": tests_impacted[:30],
            "dependencies_changed": deps_changed[:30],
            "timeline": timeline[:50],
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

    # ─────────────────── 4. Formatters ───────────────────

    def _format_change(self, signal: dict, explanations: dict) -> dict:
        """Format a single significant signal as a change entry."""
        dev = signal["deviation"]["measure"]
        baseline = signal["baseline"]

        # Get Phase 3 explanation
        explanation = ""
        exp = explanations.get(signal.get("event_ref", ""))
        if not exp:
            exp = explanations.get(f"{signal['engine_id']}:{signal['metric']}")
        if exp:
            explanation = exp.get("summary", "")

        return {
            "family": signal["engine_id"],
            "metric": signal["metric"],
            "normal": {
                "mean": round(baseline["mean"], 4),
                "stddev": round(baseline["stddev"], 4),
            },
            "current": signal["observed"],
            "deviation_stddev": round(dev, 2),
            "description": explanation,
        }

    def _format_human_summary(self, advisory: dict) -> str:
        """Render advisory as human-readable 'normal vs now' summary.

        Per PHASE_5_DESIGN.md §4.
        """
        lines = []
        lines.append(f"Evolution Advisory — {advisory['scope']}")
        lines.append(f"Period: {advisory['period']['from'][:10]} to {advisory['period']['to'][:10]}")
        lines.append("")

        summary = advisory["summary"]
        lines.append(f"{summary['significant_changes']} significant changes detected "
                     f"across {', '.join(summary['families_affected'])}.")
        lines.append("")

        # Changes with normal vs now
        for i, change in enumerate(advisory["changes"], 1):
            family_label = FAMILY_LABELS.get(change["family"], change["family"])
            metric_label = METRIC_LABELS.get(change["metric"], change["metric"])
            normal_mean = change["normal"]["mean"]
            normal_std = change["normal"]["stddev"]
            current = change["current"]
            dev = change["deviation_stddev"]
            direction = "above" if dev > 0 else "below"

            lines.append(f"{i}. {family_label} / {metric_label}")

            # Format based on whether it's a rate/ratio or a count
            if change["metric"] in ("failure_rate", "skip_rate", "fixable_ratio"):
                normal_str = f"{normal_mean:.1%}"
                current_str = f"{current:.1%}"
            elif isinstance(current, float) and current < 1:
                normal_str = f"{normal_mean:.2f}"
                current_str = f"{current:.2f}"
            else:
                normal_str = f"{normal_mean:.1f}"
                current_str = f"{current:.4g}"

            lines.append(f"   Normally: {normal_str} +/- {normal_std:.2f}")
            lines.append(f"   Now:      {current_str}  ({abs(dev):.1f}x stddev {direction} normal)")

            # Visual bar
            if normal_mean > 0 and isinstance(current, (int, float)):
                ratio = current / normal_mean if normal_mean else 1
                bar_normal = int(min(20, 20))
                bar_current = int(min(20, 20 * ratio))
                lines.append(f"   Normal: {'█' * bar_normal}")
                lines.append(f"   Now:    {'█' * min(bar_current, 40)}"
                             + (f"  <- {ratio:.1f}x" if ratio > 1.2 or ratio < 0.8 else ""))

            lines.append("")

        # Pattern matches
        if advisory.get("pattern_matches"):
            lines.append("PATTERN RECOGNITION")
            lines.append("")
            for pm in advisory["pattern_matches"]:
                lines.append(f"  These changes match a known pattern (seen {pm['seen_count']} times):")
                lines.append(f"  {pm['description']}")
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
            normal = change["normal"]["mean"]
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

        if not all_signals:
            return {"status": "no_signals", "advisory": None}

        # Step 1: Significance filter
        significant = self._filter_significant(all_signals)

        if not significant:
            return {"status": "no_significant_changes", "advisory": None}

        # Step 2: Evidence collection
        evidence = self._collect_evidence(significant, all_events)

        # Step 3: Pattern matching
        pattern_matches = self._match_patterns(significant, knowledge)

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
                "new_observations": len(changes) - len(pattern_matches),
            },
            "changes": changes,
            "pattern_matches": pattern_matches,
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
