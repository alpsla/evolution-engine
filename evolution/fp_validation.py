"""
False Positive Validation — Classify advisory items on unseen repos.

Analyzes advisory changes from repos NOT in the universal pattern training set
and classifies each as:
  - TP (true positive): genuinely unusual AND actionable
  - EP (expected positive): genuinely unusual but expected for context (large release, etc.)
  - FP (false positive): deviation is structural or spurious

Heuristics are conservative — borderline cases are classified as TP.

Usage:
    from evolution.fp_validation import validate_fp_rate
    report = validate_fp_rate(calibration_dir=".calibration/runs")
    print(report.summary())
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("evo.fp_validation")


@dataclass
class ChangeClassification:
    """Classification of a single advisory change."""
    repo: str
    family: str
    metric: str
    deviation: float
    current: float
    median: Optional[float]
    label: str          # "TP", "EP", "FP"
    reason: str         # why this classification
    pattern_matched: bool = False


@dataclass
class FPReport:
    """False positive validation report."""
    repos_analyzed: int = 0
    total_changes: int = 0
    classifications: list = field(default_factory=list)

    @property
    def tp_count(self) -> int:
        return sum(1 for c in self.classifications if c.label == "TP")

    @property
    def ep_count(self) -> int:
        return sum(1 for c in self.classifications if c.label == "EP")

    @property
    def fp_count(self) -> int:
        return sum(1 for c in self.classifications if c.label == "FP")

    @property
    def fp_rate(self) -> float:
        if not self.total_changes:
            return 0.0
        return self.fp_count / self.total_changes

    @property
    def actionable_rate(self) -> float:
        """Rate of items that are actionable (TP only)."""
        if not self.total_changes:
            return 0.0
        return self.tp_count / self.total_changes

    def summary(self) -> str:
        lines = [
            "FP Validation Report",
            "=" * 40,
            f"Repos analyzed:  {self.repos_analyzed}",
            f"Total changes:   {self.total_changes}",
            "",
            f"True Positives:     {self.tp_count:3d} ({self._pct(self.tp_count)})",
            f"Expected Positives: {self.ep_count:3d} ({self._pct(self.ep_count)})",
            f"False Positives:    {self.fp_count:3d} ({self._pct(self.fp_count)})",
            "",
            f"FP Rate:         {self.fp_rate:.1%}",
            f"Actionable Rate: {self.actionable_rate:.1%}",
            "",
        ]

        # Per-metric breakdown
        from collections import Counter
        metric_labels = {}
        for c in self.classifications:
            key = (c.family, c.metric)
            metric_labels.setdefault(key, Counter())[c.label] += 1

        lines.append("Per-metric breakdown:")
        lines.append(f"  {'Family/Metric':<35s} {'TP':>4s} {'EP':>4s} {'FP':>4s}")
        lines.append(f"  {'-'*35} {'-'*4} {'-'*4} {'-'*4}")
        for (fam, met), counts in sorted(metric_labels.items()):
            lines.append(
                f"  {fam}/{met:<30s} {counts.get('TP',0):4d} "
                f"{counts.get('EP',0):4d} {counts.get('FP',0):4d}"
            )

        # FP details
        fps = [c for c in self.classifications if c.label == "FP"]
        if fps:
            lines.append("")
            lines.append("FP Details:")
            for c in fps:
                lines.append(f"  {c.repo}: {c.family}/{c.metric} "
                             f"(dev={c.deviation:+.1f}) — {c.reason}")

        return "\n".join(lines)

    def _pct(self, count: int) -> str:
        if not self.total_changes:
            return "0%"
        return f"{count/self.total_changes:.0%}"

    def to_dict(self) -> dict:
        return {
            "repos_analyzed": self.repos_analyzed,
            "total_changes": self.total_changes,
            "tp_count": self.tp_count,
            "ep_count": self.ep_count,
            "fp_count": self.fp_count,
            "fp_rate": round(self.fp_rate, 4),
            "actionable_rate": round(self.actionable_rate, 4),
            "classifications": [
                {
                    "repo": c.repo,
                    "family": c.family,
                    "metric": c.metric,
                    "deviation": c.deviation,
                    "current": c.current,
                    "median": c.median,
                    "label": c.label,
                    "reason": c.reason,
                    "pattern_matched": c.pattern_matched,
                }
                for c in self.classifications
            ],
        }


def validate_fp_rate(
    calibration_dir: str | Path = ".calibration/runs",
    universal_patterns_path: str | Path = None,
    max_repos: int = 0,
) -> FPReport:
    """Run FP validation on unseen repos.

    Args:
        calibration_dir: Directory containing calibration runs.
        universal_patterns_path: Path to universal_patterns.json (auto-detected if None).
        max_repos: Limit number of repos to analyze (0 = all).

    Returns:
        FPReport with classifications and summary statistics.
    """
    cal_dir = Path(calibration_dir)

    # Load pattern-contributing repos to exclude them
    if universal_patterns_path is None:
        universal_patterns_path = Path(__file__).parent / "data" / "universal_patterns.json"
    pattern_repos = _get_pattern_repos(universal_patterns_path)

    report = FPReport()

    # Find unseen repos with advisories
    repos = []
    for d in sorted(cal_dir.iterdir()):
        if not d.is_dir() or d.name in pattern_repos:
            continue
        adv_path = d / "phase5" / "advisory.json"
        if adv_path.exists():
            repos.append(d)

    if max_repos > 0:
        repos = repos[:max_repos]

    for repo_dir in repos:
        adv_path = repo_dir / "phase5" / "advisory.json"
        try:
            advisory = json.loads(adv_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        report.repos_analyzed += 1
        changes = advisory.get("changes", [])
        patterns = advisory.get("pattern_matches", [])
        has_patterns = len(patterns) > 0

        for change in changes:
            report.total_changes += 1
            classification = _classify_change(
                repo=repo_dir.name,
                change=change,
                has_patterns=has_patterns,
            )
            report.classifications.append(classification)

    return report


def _classify_change(repo: str, change: dict, has_patterns: bool) -> ChangeClassification:
    """Classify a single advisory change as TP, EP, or FP.

    Heuristic rules (conservative — borderline = TP):

    FP conditions:
    - CI run_duration with deviation > 100K (runner variability, not code issue)
    - Metric with median=None and only 1-2 data points (cold-start noise)
    - direct_count metric (removed/deprecated)

    EP conditions:
    - files_touched > 500 with deviation > 1000 (massive merge/release commit)
    - change_locality = 1.0 with files_touched > 100 (expected for large refactors)
    - cochange_novelty_ratio = 0.0 with files_touched > 100 (novel combo expected for large changes)

    TP conditions (everything else):
    - Pattern-matched changes are always TP
    - Moderate deviations (2-50) on any metric
    - Dependency count changes
    - CI failures
    """
    family = change.get("family", "?")
    metric = change.get("metric", "?")
    deviation = change.get("deviation_stddev", 0)
    current = change.get("current", 0)
    normal = change.get("normal", {})
    median = normal.get("median")

    base = dict(
        repo=repo, family=family, metric=metric,
        deviation=deviation, current=current if isinstance(current, (int, float)) else 0,
        median=median, pattern_matched=has_patterns,
    )

    # ── FP Rules ──

    # Deprecated metric
    if metric == "direct_count":
        return ChangeClassification(**base, label="FP",
                                    reason="deprecated metric (direct_count)")

    # CI run_duration with extreme deviation — likely runner variability
    if metric == "run_duration" and abs(deviation) > 100000:
        return ChangeClassification(**base, label="FP",
                                    reason=f"CI runner variability (dev={deviation:.0f})")

    # Cold-start: median is None (insufficient baseline data)
    if median is None:
        return ChangeClassification(**base, label="FP",
                                    reason="cold-start (no established baseline)")

    # ── EP Rules ──

    current_num = current if isinstance(current, (int, float)) else 0

    # Massive merge/release commit with extreme files_touched
    if metric == "files_touched" and current_num > 500 and abs(deviation) > 1000:
        return ChangeClassification(**base, label="EP",
                                    reason=f"large merge/release commit ({current_num} files)")

    # change_locality at ceiling for large changes
    if metric == "change_locality" and abs(deviation) > 100 and current_num > 500:
        return ChangeClassification(**base, label="EP",
                                    reason="locality ceiling for large change")

    # cochange_novelty at floor for large changes (all combos are novel in big PRs)
    if metric == "cochange_novelty_ratio" and current_num == 0 and abs(deviation) > 100:
        # Check sibling files_touched to see if this is a large change
        return ChangeClassification(**base, label="EP",
                                    reason="novel combos expected in large cross-cutting change")

    # Release cadence with large deviation but reasonable values (seasonal variation)
    if metric == "release_cadence_hours" and abs(deviation) > 15:
        return ChangeClassification(**base, label="EP",
                                    reason="release cadence seasonal variation")

    # ── TP (default) ──

    reason = "genuine deviation"
    if has_patterns:
        reason = "pattern-matched deviation"
    elif abs(deviation) >= 6:
        reason = "critical deviation"
    elif abs(deviation) >= 4:
        reason = "high deviation"
    elif abs(deviation) >= 2:
        reason = "medium deviation"

    return ChangeClassification(**base, label="TP", reason=reason)


def _get_pattern_repos(path: Path) -> set[str]:
    """Get set of repos that contributed to universal patterns."""
    if not path.exists():
        return set()
    data = json.loads(path.read_text())
    repos = set()
    for p in data.get("patterns", []):
        for r in p.get("repos_observed", []):
            repos.add(r)
    return repos


def baseline_norms(calibration_dir: str | Path = ".calibration/runs") -> dict:
    """Compute per-family baseline norms across all calibrated repos.

    Returns dict of {family: {metric: {median, mad, iqr, sample_count}}}.
    """
    cal_dir = Path(calibration_dir)
    from collections import defaultdict
    values = defaultdict(lambda: defaultdict(list))

    for d in cal_dir.iterdir():
        if not d.is_dir():
            continue
        adv_path = d / "phase5" / "advisory.json"
        if not adv_path.exists():
            continue
        try:
            advisory = json.loads(adv_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        for change in advisory.get("changes", []):
            family = change.get("family", "?")
            metric = change.get("metric", "?")
            normal = change.get("normal", {})
            median = normal.get("median")
            if median is not None:
                values[family][metric].append(median)

    # Compute cross-repo norms
    norms = {}
    for family in sorted(values):
        norms[family] = {}
        for metric in sorted(values[family]):
            medians = values[family][metric]
            if not medians:
                continue
            medians.sort()
            n = len(medians)
            mid = n // 2
            med_of_medians = medians[mid] if n % 2 else (medians[mid-1] + medians[mid]) / 2
            norms[family][metric] = {
                "median_of_medians": round(med_of_medians, 4),
                "repos_with_data": n,
                "range": [round(medians[0], 4), round(medians[-1], 4)],
            }
    return norms
