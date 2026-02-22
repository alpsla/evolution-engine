"""
HTML Report Generator — Produces standalone HTML reports from Phase 5 advisory data.

Usage:
    from evolution.report_generator import generate_report
    html = generate_report(advisory_path)
    Path("report.html").write_text(html)

Or via CLI:
    evo report [path]
    evo report . --output report.html
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from evolution.friendly import (
    risk_level, relative_change, metric_insight, friendly_pattern,
    pattern_risk_assessment, _severity_rank,
)


def _load_adapter_catalog() -> list:
    """Load the adapter catalog from bundled data."""
    catalog_path = Path(__file__).parent / "data" / "adapter_catalog.json"
    if catalog_path.exists():
        return json.loads(catalog_path.read_text())
    return []


def _load_universal_patterns_count() -> int:
    """Load the count of universal patterns from bundled data."""
    patterns_path = Path(__file__).parent / "data" / "universal_patterns.json"
    if patterns_path.exists():
        data = json.loads(patterns_path.read_text())
        return len(data.get("patterns", []))
    return 0


def _detect_remote_url(repo_dir: Path) -> str:
    """Try to detect the remote URL from git config.

    Returns a base URL like 'https://github.com/owner/repo' or empty string.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=str(repo_dir), timeout=5,
        )
        if result.returncode != 0:
            return ""
        url = result.stdout.strip()
        # SSH: git@github.com:owner/repo.git → https://github.com/owner/repo
        m = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", url)
        if m:
            return f"https://{m.group(1)}/{m.group(2)}"
        # HTTPS: https://github.com/owner/repo.git → https://github.com/owner/repo
        m = re.match(r"(https?://[^/]+/.+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
        return ""
    except Exception:
        return ""


def _commit_url(remote_url: str, sha: str) -> str:
    """Build a commit URL that works for both GitHub and GitLab.

    GitLab uses /-/commit/{sha}, GitHub and most others use /commit/{sha}.
    """
    if "gitlab" in remote_url.lower():
        return f"{remote_url}/-/commit/{sha}"
    return f"{remote_url}/commit/{sha}"

FAMILY_LABELS = {
    "git": "Version Control",
    "version_control": "Version Control",
    "ci": "CI / Build",
    "testing": "Testing",
    "coverage": "Coverage",
    "dependency": "Dependencies",
    "schema": "API / Schema",
    "deployment": "Deployment",
    "config": "Configuration",
    "security": "Security",
    "error_tracking": "Error Tracking",
    "monitoring": "Monitoring",
    "quality_gate": "Quality Gate",
    "security_scan": "Security Scan",
    "incidents": "Incidents",
    "work_items": "Work Items",
    "feature_flags": "Feature Flags",
}

METRIC_LABELS = {
    "files_touched": "Files Changed",
    "dispersion": "Change Dispersion",
    "change_locality": "Change Locality",
    "cochange_novelty_ratio": "Co-change Novelty",
    "run_duration": "Build Duration",
    "run_failed": "Build Failure",
    "dependency_count": "Total Dependencies",
    "max_depth": "Dependency Depth",
    "release_cadence_hours": "Release Cadence",
    "is_prerelease": "Pre-release",
    "asset_count": "Release Assets",
}

FAMILY_COLORS = {
    "git": "#3b82f6",
    "version_control": "#3b82f6",
    "ci": "#f59e0b",
    "testing": "#10b981",
    "coverage": "#059669",
    "dependency": "#8b5cf6",
    "schema": "#ec4899",
    "deployment": "#06b6d4",
    "config": "#6366f1",
    "security": "#ef4444",
    "error_tracking": "#dc2626",
    "monitoring": "#7c3aed",
    "quality_gate": "#0891b2",
    "security_scan": "#e11d48",
    "incidents": "#ea580c",
    "work_items": "#4f46e5",
    "feature_flags": "#65a30d",
}

FAMILY_ICONS = {
    "git": "\U0001f4dd",
    "version_control": "\U0001f4dd",
    "ci": "\u2699\ufe0f",
    "testing": "\U0001f9ea",
    "dependency": "\U0001f4e6",
    "schema": "\U0001f4cb",
    "deployment": "\U0001f680",
    "config": "\U0001f527",
    "security": "\U0001f512",
    "coverage": "\U0001f4ca",
    "error_tracking": "\U0001f6a8",
    "monitoring": "\U0001f4c8",
    "quality_gate": "\u2705",
    "security_scan": "\U0001f6e1\ufe0f",
    "incidents": "\U0001f6a8",
    "work_items": "\U0001f4cb",
    "feature_flags": "\U0001f6a9",
}



def generate_report(
    evo_dir: str | Path,
    title: str = None,
    calibration_result: dict = None,
    verification: dict = None,
) -> str:
    """Generate a standalone HTML report from Phase 5 output.

    Args:
        evo_dir: Path to the .evo directory (or calibration run dir).
        title: Optional title override.
        calibration_result: Optional calibration_result.json dict for extra stats.
        verification: Optional diff result from history comparison (--verify).

    Returns:
        Complete HTML string.
    """
    evo_dir = Path(evo_dir)
    advisory_path = evo_dir / "phase5" / "advisory.json"
    evidence_path = evo_dir / "phase5" / "evidence.json"

    if not advisory_path.exists():
        raise FileNotFoundError(f"No advisory found at {advisory_path}")

    advisory = json.loads(advisory_path.read_text())
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}

    scope = advisory.get("scope", "Unknown Repository")
    title = title or f"Evolution Advisory \u2014 {scope}"

    # Auto-load verification data if not passed explicitly
    if verification is None:
        verify_path = evo_dir / "phase5" / "verification.json"
        if verify_path.exists():
            try:
                verification = json.loads(verify_path.read_text())
            except (json.JSONDecodeError, ValueError):
                pass

    # Try to detect git remote for commit links
    repo_dir = evo_dir.parent
    remote_url = _detect_remote_url(repo_dir)

    return _render_html(advisory, evidence, title, calibration_result, remote_url, verification)


def _render_html(advisory, evidence, title, cal=None, remote_url="", verification=None):
    scope = advisory.get("scope", "Unknown")
    summary = advisory.get("summary", {})
    changes = advisory.get("changes", [])
    pattern_matches = advisory.get("pattern_matches", [])
    candidate_patterns = advisory.get("candidate_patterns", [])
    commits = evidence.get("commits", [])
    files_affected = evidence.get("files_affected", [])
    timeline = evidence.get("timeline", [])
    deps_changed = evidence.get("dependencies_changed", [])

    period = advisory.get("period", {})
    period_from = _format_date(period.get("from", ""))
    period_to = _format_date(period.get("to", ""))
    generated = _format_date(advisory.get("generated_at", ""))
    advisory_id = advisory.get("advisory_id", "")
    families_affected = summary.get("families_affected", [])

    # Confidence: use commits count from evidence
    n_commits = len(commits)

    # Total patterns matched = community + repo-specific from advisory
    total_patterns = len(pattern_matches) + len(candidate_patterns)

    cover = _build_cover_page(scope, period_from, period_to, advisory_id, generated)
    exec_summary = _build_executive_summary(summary, families_affected, cal, n_commits, total_patterns)
    verify_html = _build_verification_banner(verification) if verification else ""
    findings_html = _build_key_findings(changes, pattern_matches, candidate_patterns, families_affected)
    # Build commit lookup for per-finding evidence
    commits_by_sha = {}
    for cm in commits:
        sha = cm.get("sha", "")
        if sha:
            commits_by_sha[sha] = cm
    changes_html = _build_changes_section(changes, remote_url, commits_by_sha, commits, deps_changed)
    patterns_html = _build_pattern_section(pattern_matches, candidate_patterns)
    all_patterns = list(pattern_matches) + list(candidate_patterns)
    invest_html = _build_investigation_section(
        scope, period_from, period_to, changes, commits, files_affected, timeline,
        all_patterns,
    )
    adapters_html = _build_adapters_section(families_affected)
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<title>{_esc(title)}</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">\n'
        f'<style>\n{_CSS}\n</style>\n'
        f'{_JS}\n'
        '</head>\n<body>\n'
        f'{cover}\n'
        f'{exec_summary}\n'
        f'{verify_html}\n'
        f'{findings_html}\n'
        f'{changes_html}\n'
        f'{patterns_html}\n'
        f'{invest_html}\n'
        f'{adapters_html}\n'
        '<footer>\n'
        '  <p>Generated by <strong>CodeQual</strong> Evolution Engine</p>\n'
        f'  <p style="margin-top: 0.5em;">Advisory ID: {_esc(advisory_id)} &bull; {generated}</p>\n'
        '</footer>\n'
        '</body>\n</html>'
    )


# ─── Section Builders ───


def _build_cover_page(scope, period_from, period_to, advisory_id, generated):
    return (
        '<div class="cover-page page-break-after">\n'
        '  <svg class="logo" viewBox="0 0 48 56" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
        '    <path d="M24 0C24 0 0 6 0 14V32C0 44 10 54 24 56C38 54 48 44 48 32V14C48 6 24 0 24 0Z" fill="#0A4D4A"/>\n'
        '    <path d="M24 4C24 4 4 9 4 16V31C4 41 12 49 24 51C36 49 44 41 44 31V16C44 9 24 4 24 4Z" fill="none" stroke="#2CA58D" stroke-width="2"/>\n'
        '    <path d="M15 20L10 28L15 36" stroke="#F8F9FA" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>\n'
        '    <path d="M18 28L22 32L30 22" stroke="#2CA58D" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>\n'
        '    <path d="M33 20L38 28L33 36" stroke="#F8F9FA" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>\n'
        '  </svg>\n'
        '  <div class="cover-brand">CodeQual</div>\n'
        '  <h1>Evolution Advisory</h1>\n'
        '  <div class="cover-metadata">\n'
        f'    <p><strong>Project:</strong> {_esc(scope)}</p>\n'
        f'    <p><strong>Period:</strong> {period_from} to {period_to}</p>\n'
        f'    <p><strong>Advisory ID:</strong> <code>{_esc(advisory_id)}</code></p>\n'
        f'    <p><strong>Generated:</strong> {generated}</p>\n'
        '  </div>\n'
        '</div>'
    )


def _build_executive_summary(summary, families_affected, cal=None, n_commits=0, total_patterns=0):
    sig = summary.get("significant_changes", 0)
    n_fam = len(families_affected)
    new_obs = summary.get("new_observations", 0)

    cards = [
        _summary_card(str(sig), "Significant Changes"),
        _summary_card(str(n_fam), "Areas Affected"),
        _summary_card(str(total_patterns), "Patterns Matched"),
        _summary_card(str(new_obs), "New Observations"),
    ]
    if cal:
        events = cal.get("events", 0)
        signals = cal.get("signals", 0)
        if events:
            cards.append(_summary_card(f"{events:,}", "Events Analyzed"))
        if signals:
            cards.append(_summary_card(f"{signals:,}", "Signals Computed"))

    family_items = " ".join(
        FAMILY_ICONS.get(f, "") + " " + FAMILY_LABELS.get(f, f)
        for f in families_affected
    )
    families_html = ""
    if families_affected:
        families_html = (
            '<p class="summary-families">'
            f'<strong>Affected areas:</strong> {family_items}'
            '</p>'
        )

    confidence_html = ""
    if n_commits > 0:
        confidence_html = (
            '<p class="confidence-note">'
            f'Based on {n_commits:,} prior commit{"s" if n_commits != 1 else ""}'
            '</p>'
        )

    return (
        '<section class="executive-summary">\n'
        '  <h2>Executive Summary</h2>\n'
        '  <div class="summary-cards">\n'
        '    ' + '\n    '.join(cards) + '\n'
        '  </div>\n'
        f'  {families_html}\n'
        f'  {confidence_html}\n'
        '</section>'
    )


def _summary_card(value, label):
    return (
        f'<div class="summary-card">'
        f'<div class="summary-value">{value}</div>'
        f'<div class="summary-label">{label}</div>'
        f'</div>'
    )


def _build_verification_banner(verification):
    """Build a before/after comparison banner from --verify data."""
    resolved = verification.get("resolved", [])
    persisting = verification.get("persisting", [])
    new_changes = verification.get("new", [])

    total_before = len(resolved) + len(persisting)
    n_resolved = len(resolved)
    n_improving = sum(1 for p in persisting if p.get("improved"))
    n_not_improving = sum(1 for p in persisting if not p.get("improved"))
    n_new = len(new_changes)

    # Overall status
    if n_resolved == total_before and n_new == 0 and total_before > 0:
        status_class = "verify-all-clear"
        status_icon = "\u2705"
        status_text = "All issues resolved"
    elif n_resolved > 0 or n_improving > 0:
        status_class = "verify-improving"
        status_icon = "\U0001f4c8"
        status_text = "Progress detected"
    else:
        status_class = "verify-no-change"
        status_icon = "\u2194\ufe0f"
        status_text = "No change yet"

    # Build signal rows
    rows = []
    for r in resolved:
        metric = METRIC_LABELS.get(r.get("metric", ""), r.get("metric", ""))
        family = FAMILY_LABELS.get(r.get("family", ""), r.get("family", ""))
        rows.append(
            f'<tr class="verify-resolved"><td>{_esc(family)}</td><td>{_esc(metric)}</td>'
            f'<td colspan="2">Resolved</td><td>\u2705</td></tr>'
        )
    has_transient = False
    has_persistent = False
    has_stabilized = False
    for p in persisting:
        metric = METRIC_LABELS.get(p.get("metric", ""), p.get("metric", ""))
        family = FAMILY_LABELS.get(p.get("family", ""), p.get("family", ""))
        was = p.get("was_deviation", 0)
        now = p.get("now_deviation", 0)
        improved = p.get("improved", False)
        trend_icon = "\U0001f4c9" if improved else "\u2796"
        trend_label = "improving" if improved else "not improving"
        trend_class = "verify-trend-good" if improved else "verify-trend-flat"
        # Detect historical triggers: deviation unchanged means the most deviant
        # commit is an older one that wasn't affected by the recent fix
        if not improved and abs(was) > 0 and abs(was - now) < 0.1:
            latest_dev = p.get("latest_deviation")
            if latest_dev is not None and abs(latest_dev) >= 1.5:
                # Still actively deviating in latest measurement
                trend_label = "still actively deviating"
                trend_class = "verify-trend-warn"
                has_persistent = True
            else:
                # Low latest deviation — but did the value actually return?
                latest_val = p.get("latest_value")
                if _value_near_baseline(latest_val, p.get("normal", {})):
                    trend_label = "returned to normal"
                    has_transient = True
                else:
                    trend_label = "stabilized at new level"
                    trend_class = "verify-trend-stabilized"
                    has_stabilized = True
        # Show actual observed values instead of raw σ numbers
        before_val = _fmt_value(p.get("was_value"))
        after_val = _fmt_value(p.get("current"))
        normal = p.get("normal", {})
        baseline = _fmt_value(normal.get("median", normal.get("mean")))
        rows.append(
            f'<tr><td>{_esc(family)}</td><td>{_esc(metric)}</td>'
            f'<td>{_esc(before_val)}</td>'
            f'<td>{_esc(after_val)}<span class="verify-baseline"> / {_esc(baseline)}</span></td>'
            f'<td class="{trend_class}">{trend_icon} {trend_label}</td></tr>'
        )
    for n in new_changes:
        metric = METRIC_LABELS.get(n.get("metric", ""), n.get("metric", ""))
        family = FAMILY_LABELS.get(n.get("family", ""), n.get("family", ""))
        rows.append(
            f'<tr class="verify-new"><td>{_esc(family)}</td><td>{_esc(metric)}</td>'
            f'<td colspan="2">New</td><td>\u26a0\ufe0f</td></tr>'
        )

    rows_html = "\n".join(rows)

    # Summary chips
    chips = []
    if n_resolved:
        chips.append(f'<span class="verify-chip verify-chip-resolved">\u2705 {n_resolved} resolved</span>')
    if n_improving:
        chips.append(f'<span class="verify-chip verify-chip-improving">\U0001f4c8 {n_improving} improving</span>')
    if n_not_improving:
        chips.append(f'<span class="verify-chip verify-chip-flat">\u2796 {n_not_improving} not improving</span>')
    if n_new:
        chips.append(f'<span class="verify-chip verify-chip-new">\u26a0\ufe0f {n_new} new</span>')

    # Guidance notes for historical triggers
    historical_note = ""
    if has_transient:
        historical_note += (
            '  <div class="verify-note">\n'
            '    <strong>Transient spike:</strong> One-time spike from an older commit. '
            'The metric has since returned to its baseline. Safe to accept.\n'
            '  </div>\n'
        )
    if has_stabilized:
        historical_note += (
            '  <div class="verify-note-stabilized">\n'
            '    <strong>Stabilized drift:</strong> An older commit shifted this metric to a new level '
            'and it stayed there. The statistical model absorbed the change, but the value differs from '
            'the original baseline. Consider whether this shift was intentional.\n'
            '  </div>\n'
        )
    if has_persistent:
        historical_note += (
            '  <div class="verify-note-warn">\n'
            '    <strong>Active deviation:</strong> This metric is still actively deviating in the latest '
            'data. Investigation recommended.\n'
            '  </div>\n'
        )

    return (
        f'<section class="verification-banner {status_class}">\n'
        f'  <div class="verify-header">\n'
        f'    <span class="verify-icon">{status_icon}</span>\n'
        f'    <div>\n'
        f'      <div class="verify-title">Fix Verification: {status_text}</div>\n'
        f'      <div class="verify-subtitle">Comparing against previous analysis</div>\n'
        f'    </div>\n'
        f'  </div>\n'
        f'  <div class="verify-chips">{"".join(chips)}</div>\n'
        f'  <table class="verify-table">\n'
        f'    <thead><tr><th>Area</th><th>Signal</th><th>Before</th><th>After / Normal</th><th>Trend</th></tr></thead>\n'
        f'    <tbody>{rows_html}</tbody>\n'
        f'  </table>\n'
        f'{historical_note}'
        f'</section>'
    )


def _build_key_findings(changes, pattern_matches, candidate_patterns, families_affected):
    """Build a concise narrative summary of all findings."""
    if not changes and not pattern_matches and not candidate_patterns:
        return (
            '<section class="key-findings">\n'
            '  <h2>Key Findings</h2>\n'
            '  <p class="empty">No unusual activity detected. Your project\'s development '
            'patterns are within normal ranges.</p>\n'
            '</section>'
        )

    bullets = []

    # Summarize changes by family
    if changes:
        family_changes = {}
        for c in changes:
            fam = FAMILY_LABELS.get(c.get("family", ""), c.get("family", ""))
            family_changes.setdefault(fam, []).append(c)
        for fam, items in family_changes.items():
            high = [c for c in items if abs(c.get("deviation_stddev", 0)) >= 4.0]
            med = [c for c in items if 2.0 <= abs(c.get("deviation_stddev", 0)) < 4.0]
            if high:
                metrics = ", ".join(
                    METRIC_LABELS.get(c.get("metric", ""), c.get("metric", ""))
                    for c in high
                )
                bullets.append(
                    f'<strong>{_esc(fam)}</strong> showed significant deviations '
                    f'in {_esc(metrics)}.'
                )
            elif med:
                metrics = ", ".join(
                    METRIC_LABELS.get(c.get("metric", ""), c.get("metric", ""))
                    for c in med
                )
                bullets.append(
                    f'<strong>{_esc(fam)}</strong> showed moderate deviations '
                    f'in {_esc(metrics)}.'
                )
            else:
                metrics = ", ".join(
                    METRIC_LABELS.get(c.get("metric", ""), c.get("metric", ""))
                    for c in items
                )
                bullets.append(
                    f'<strong>{_esc(fam)}</strong> showed minor deviations '
                    f'in {_esc(metrics)}.'
                )

    # Summarize patterns
    n_known = len(pattern_matches) if pattern_matches else 0
    n_new = len(candidate_patterns) if candidate_patterns else 0
    if n_known or n_new:
        parts = []
        if n_known:
            parts.append(f'{n_known} known pattern{"s" if n_known != 1 else ""} detected')
        if n_new:
            parts.append(f'{n_new} new pattern{"s" if n_new != 1 else ""} discovered')
        bullets.append(". ".join(parts) + ".")

    items_html = "\n".join(f'    <li>{b}</li>' for b in bullets)
    return (
        '<section class="key-findings">\n'
        '  <h2>Key Findings</h2>\n'
        '  <ul class="findings-list">\n'
        f'{items_html}\n'
        '  </ul>\n'
        '</section>'
    )


def _build_changes_section(changes, remote_url="", commits_by_sha=None,
                           all_commits=None, deps_changed=None):
    if not changes:
        return (
            '<section class="changes-detected page-break-before">\n'
            '  <h2>What Changed in Your Codebase</h2>\n'
            '  <p class="empty">No unusual changes detected.</p>\n'
            '</section>'
        )

    n = len(changes)
    cards = "\n".join(
        _build_change_card(c, idx, remote_url, commits_by_sha or {},
                           all_commits or [], deps_changed or [])
        for idx, c in enumerate(changes)
    )

    filter_buttons = (
        '  <div class="severity-filters no-print">\n'
        '    <button class="btn btn-filter active" onclick="filterChanges(\'all\', this)">All</button>\n'
        '    <button class="btn btn-filter" onclick="filterChanges(\'deviation-high\', this)">Critical</button>\n'
        '    <button class="btn btn-filter" onclick="filterChanges(\'deviation-medium\', this)">Medium</button>\n'
        '    <button class="btn btn-filter" onclick="filterChanges(\'deviation-low\', this)">Low</button>\n'
        '  </div>\n'
    )

    progress_bar = (
        '  <div class="progress-tracker no-print" id="progressTracker">\n'
        f'    <span id="resolvedCount">0</span> of {n} resolved\n'
        '    <div class="progress-bar"><div class="progress-fill" id="progressFill" '
        f'style="width: 0%;" data-total="{n}"></div></div>\n'
        '  </div>\n'
    )

    return (
        '<section class="changes-detected page-break-before">\n'
        '  <h2>What Changed in Your Codebase</h2>\n'
        '  <p style="color: var(--color-text-muted); margin-bottom: 1.5em;">\n'
        f'    We\'ve detected {n} change{"s" if n != 1 else ""} that differ from your project\'s\n'
        '    normal patterns. Each change shows what typically happens versus what we observed this time.\n'
        '  </p>\n'
        f'{progress_bar}'
        f'{filter_buttons}'
        f'  {cards}\n'
        '</section>'
    )


def _build_change_card(c, index=0, remote_url="", commits_by_sha=None,
                       all_commits=None, deps_changed=None):
    family = c.get("family", "")
    metric_key = c.get("metric", "")
    metric_name = METRIC_LABELS.get(metric_key, metric_key)
    family_label = FAMILY_LABELS.get(family, family)
    icon = FAMILY_ICONS.get(family, "")
    current = c.get("current", 0)
    normal = c.get("normal", {})
    median = normal.get("median", normal.get("mean", 0))
    dev = c.get("deviation_stddev", 0)
    dev_class = _deviation_class(dev)
    direction = "above" if dev >= 0 else "below"
    abs_dev = abs(dev)

    anchor_id = f"change-{_esc(family)}-{_esc(metric_key)}"

    normal_w, current_w = _bar_widths(current, median)

    insight_dir = "up" if dev >= 0 else "down"
    insight = metric_insight(metric_key, insight_dir)
    explanation = "<strong>What this means:</strong> "
    if insight:
        explanation += insight
    else:
        explanation += (
            f"{_esc(metric_name)} was {_fmt_num(current)}, "
            f"compared to the typical value of {_fmt_num(median)}."
        )

    mad = normal.get("mad", normal.get("stddev", 0))

    # Only show technical details when there's meaningful statistical data
    tech_html = ""
    if mad and mad > 0:
        tech = (
            f"The {metric_key.replace('_', ' ')} for this change was {_fmt_num(current)}. "
            f"Historically, similar changes had a value of {_fmt_num(median)} "
            f"&plusmn; {_fmt_num(mad)}."
        )
        tech_html = (
            '  <details class="technical-detail">\n'
            '    <summary>Show technical details</summary>\n'
            f'    <p>{tech}</p>\n'
            '  </details>\n'
        )

    # Action buttons: Accept + Fix with AI
    accept_idx = index + 1  # 1-based for CLI
    accept_cmd = f'evo accept . {accept_idx} --reason &quot;Expected behavior&quot;'
    accept_thisrun = f'evo accept . {accept_idx} --scope this-run --reason &quot;Expected behavior&quot;'

    # Build drift prompt for Fix with AI — scoped to this finding's commit
    full_trigger = c.get("trigger_commit", "")
    commit_sha = full_trigger[:8]
    commit_msg = _esc(c.get("commit_message", "").split("\n")[0])
    drift_prompt = (
        f"Development pattern shift detected in {_esc(family_label)}.\\n\\n"
        f"SIGNAL: {_esc(metric_name)} is {abs_dev:.1f}x {direction} the typical baseline "
        f"(observed: {_fmt_num(current)}, typical: {_fmt_num(median)}).\\n"
    )
    if commit_sha:
        drift_prompt += f"TRIGGER COMMIT: {commit_sha} — {commit_msg}\\n"

    # Add per-finding file evidence from the trigger commit
    trigger_files = c.get("trigger_files", [])
    if not trigger_files:
        # Fallback: look up from evidence commits
        commit_data = (commits_by_sha or {}).get(full_trigger, {})
        trigger_files = commit_data.get("files_changed", [])
    if trigger_files:
        drift_prompt += f"\\nFILES CHANGED IN TRIGGER ({len(trigger_files)}):\\n"
        for fp in trigger_files[:15]:
            drift_prompt += f"  - {_esc(fp)}\\n"
        if len(trigger_files) > 15:
            drift_prompt += f"  ... and {len(trigger_files) - 15} more\\n"

    # Add recent commits from evidence (excluding trigger) for broader context
    evidence_commits = all_commits or []
    other_commits = [cm for cm in evidence_commits if cm.get("sha", "") != full_trigger]
    if other_commits:
        drift_prompt += f"\\nRECENT COMMITS ({len(other_commits)} total, showing top 5):\\n"
        for cm in other_commits[:5]:
            cm_sha = cm.get("sha", "")[:8]
            cm_msg = _esc(cm.get("message", "").split("\\n")[0][:60])
            cm_files = len(cm.get("files_changed", []))
            drift_prompt += f"  {cm_sha} — {cm_msg} ({cm_files} files)\\n"
        if len(other_commits) > 5:
            drift_prompt += f"  ... and {len(other_commits) - 5} more commits\\n"

    # Add dependency changes if this finding is in the dependency family
    evidence_deps = deps_changed or []
    if evidence_deps and family in ("dependency", "dep"):
        drift_prompt += f"\\nDEPENDENCIES CHANGED ({len(evidence_deps)}):\\n"
        for dep in evidence_deps[:10]:
            dep_name = _esc(dep.get("name", dep.get("package", "")))
            dep_from = dep.get("from", dep.get("old_version", ""))
            dep_to = dep.get("to", dep.get("new_version", ""))
            if dep_from and dep_to:
                drift_prompt += f"  - {dep_name}: {dep_from} -> {dep_to}\\n"
            else:
                drift_prompt += f"  - {dep_name}\\n"
        if len(evidence_deps) > 10:
            drift_prompt += f"  ... and {len(evidence_deps) - 10} more\\n"

    if commit_sha:
        drift_prompt += (
            "\\nINVESTIGATE:\\n"
            "1. Was this change intentional or did the AI drift from goals?\\n"
            f"2. Review commit {commit_sha} — what specifically caused the deviation?\\n"
            "3. Suggest a course correction (not a bug fix — a realignment).\\n\\n"
            "AFTER FIX:\\n"
            "Run `evo analyze . --verify` to re-analyze and compare against this run.\\n"
            "If the change was intentional, no fix needed — accept it in the report."
        )
    else:
        drift_prompt += (
            "\\nINVESTIGATE:\\n"
            "1. Was this change intentional or did the AI drift from goals?\\n"
            "2. Identify which recent commit introduced this shift.\\n"
            "3. Suggest a course correction (not a bug fix — a realignment).\\n\\n"
            "AFTER FIX:\\n"
            "Run `evo analyze . --verify` to re-analyze and compare against this run.\\n"
            "If the change was intentional, no fix needed — accept it in the report."
        )

    action_buttons = (
        f'  <div class="change-actions no-print" id="actions-{index}">\n'
        f'    <div class="accept-group">\n'
        f'      <button class="btn btn-action btn-accept" onclick="toggleAcceptMenu({index})">Accept &mdash; Expected</button>\n'
        f'      <div class="accept-menu" id="accept-menu-{index}">\n'
        f'        <button onclick="acceptFinding({index}, \'permanent\', \'{accept_cmd}\')">Accept permanently<span class="accept-hint">Never flag this signal again</span></button>\n'
        f'        <button onclick="acceptFinding({index}, \'this-run\', \'{accept_thisrun}\')">Accept for this run only<span class="accept-hint">Dismiss now, flag again next analysis</span></button>\n'
        f'      </div>\n'
        f'    </div>\n'
        f'    <button class="btn btn-action btn-fix" onclick="toggleFixPrompt({index})">Fix with AI</button>\n'
        f'  </div>\n'
        f'  <div class="fix-prompt-panel no-print" id="fix-prompt-{index}">\n'
        f'    <div class="fix-prompt-header">\n'
        f'      <strong>Drift Investigation Prompt</strong>\n'
        f'      <button class="btn btn-copy-sm" onclick="copyFixPrompt({index})">Copy</button>\n'
        f'    </div>\n'
        f'    <pre class="fix-prompt-text" id="fix-prompt-text-{index}">{drift_prompt}</pre>\n'
        f'    <div class="fix-prompt-guide">\n'
        f'      <strong>Use with:</strong>\n'
        f'      <span>Cursor &mdash; paste in chat</span>\n'
        f'      <span>Claude Code &mdash; paste in terminal</span>\n'
        f'      <span>Copilot &mdash; paste in chat panel</span>\n'
        f'    </div>\n'
        f'    <div class="fix-next-steps">\n'
        f'      <strong>After investigation:</strong>\n'
        f'      <ol>\n'
        f'        <li>AI suggests fixes &rarr; apply the changes to your code</li>\n'
        f'        <li>Run <code>evo analyze . --verify</code> to re-analyze and compare against this run</li>\n'
        f'        <li>If the change was intentional, click <strong>Accept</strong> above to dismiss it</li>\n'
        f'      </ol>\n'
        f'    </div>\n'
        f'  </div>\n'
    )

    # Commit attribution line with optional link
    commit_html = ""
    full_sha = c.get("trigger_commit", "")
    if full_sha:
        sha_display = full_sha[:8]
        msg_display = _esc(c.get("commit_message", "").split("\n")[0][:60])
        if remote_url:
            commit_link = _commit_url(remote_url, _esc(full_sha))
            sha_html = f'<a href="{commit_link}" target="_blank" class="commit-link"><code>{sha_display}</code></a>'
        else:
            sha_html = f'<code>{sha_display}</code>'
        commit_html = (
            f'  <div class="commit-attribution">'
            f'Trigger: {sha_html} {msg_display}'
            f'</div>\n'
        )

    # Trend subtitle for historical triggers
    trend_html = ""
    if full_sha and not c.get("is_latest_event", True):
        latest_dev = c.get("latest_deviation")
        if latest_dev is not None:
            if abs(latest_dev) >= 1.5:
                trend_html = f'  <div class="trend-subtitle trend-elevated">\u2192 Still elevated (latest deviation: {abs(latest_dev):.1f}\u03c3)</div>\n'
            else:
                trend_html = f'  <div class="trend-subtitle trend-returning">\u2198 Returned to baseline</div>\n'

    return (
        f'<div class="change-card {dev_class}" id="{anchor_id}">\n'
        '  <div class="change-card-header">\n'
        f'    <span class="family-icon">{icon}</span>\n'
        f'    <div>\n'
        f'      <div class="metric-name">{_esc(metric_name)}</div>\n'
        f'      <div class="family-label">{_esc(family_label)}</div>\n'
        f'    </div>\n'
        '  </div>\n'
        f'  <div class="user-friendly-summary">{explanation}</div>\n'
        '  <div class="bar-chart">\n'
        '    <div class="bar-chart-row">\n'
        '      <div class="bar-label">Typical:</div>\n'
        f'      <div class="bar-container"><div class="bar-fill normal" style="width: {normal_w}%"></div></div>\n'
        f'      <div class="bar-value">{_fmt_num(median)}</div>\n'
        '    </div>\n'
        '    <div class="bar-chart-row">\n'
        '      <div class="bar-label">This Time:</div>\n'
        f'      <div class="bar-container"><div class="bar-fill" style="width: {current_w}%"></div></div>\n'
        f'      <div class="bar-value">{_fmt_num(current)}</div>\n'
        '    </div>\n'
        '  </div>\n'
        f'  <div class="deviation-badge">{abs_dev:.1f}x {direction} typical range</div>\n'
        f'{commit_html}'
        f'{trend_html}'
        f'{action_buttons}'
        f'{tech_html}'
        '</div>'
    )


def _build_pattern_card(p, badge_label):
    """Build a single pattern card with severity badge, impact, and recommendation."""
    sources = ", ".join(FAMILY_LABELS.get(s, s) for s in p.get("sources", []))
    metrics = ", ".join(METRIC_LABELS.get(m, m) for m in p.get("metrics", []))
    desc = friendly_pattern(p)
    risk = pattern_risk_assessment(p)
    severity = risk["severity"]
    sev_display = risk["severity_display"]
    impact = risk["impact"]
    recommendation = risk["recommendation"]

    badge_style = ' style="background: var(--color-warning);"' if badge_label == "Emerging Pattern" else ""

    return (
        f'<div class="pattern-card severity-border-{severity}">\n'
        f'  <span class="badge"{badge_style}>{badge_label}</span>\n'
        f'  <span class="severity-badge severity-{severity}">'
        f'{sev_display["icon"]} {_esc(sev_display["label"])}</span>\n'
        f'  <h3 style="margin-top: 0.5em;">{_esc(sources)}</h3>\n'
        f'  <div class="pattern-meta">{_esc(metrics)}</div>\n'
        + (f'  <p>{_esc(desc)}</p>\n' if desc else '')
        + f'  <div class="pattern-impact"><strong>What this means:</strong> {_esc(impact)}</div>\n'
        f'  <div class="pattern-recommendation"><strong>Recommendation:</strong> {_esc(recommendation)}</div>\n'
        '</div>'
    )


def _build_grouped_pattern_card(patterns, badge_label):
    """Build a single card for multiple patterns sharing the same severity + impact.

    Combines sources and metrics from all patterns, shows each pattern's description
    as a bullet point, but uses the shared impact/recommendation only once.
    """
    risk = pattern_risk_assessment(patterns[0])
    severity = risk["severity"]
    sev_display = risk["severity_display"]
    impact = risk["impact"]
    recommendation = risk["recommendation"]

    badge_style = ' style="background: var(--color-warning);"' if badge_label == "Emerging Pattern" else ""

    # Collect unique sources and metrics across all patterns in the group
    all_sources = []
    all_metrics = []
    descriptions = []
    for p in patterns:
        for s in p.get("sources", []):
            label = FAMILY_LABELS.get(s, s)
            if label not in all_sources:
                all_sources.append(label)
        for m in p.get("metrics", []):
            label = METRIC_LABELS.get(m, m)
            if label not in all_metrics:
                all_metrics.append(label)
        desc = friendly_pattern(p)
        if desc:
            descriptions.append(desc)

    sources_str = ", ".join(all_sources)
    metrics_str = ", ".join(all_metrics)

    # Show each pattern's description as a bullet
    desc_html = ""
    if descriptions:
        items = "\n".join(f'    <li>{_esc(d)}</li>' for d in descriptions)
        desc_html = f'  <ul class="grouped-pattern-list">\n{items}\n  </ul>\n'

    return (
        f'<div class="pattern-card severity-border-{severity}">\n'
        f'  <span class="badge"{badge_style}>{badge_label}</span>\n'
        f'  <span class="severity-badge severity-{severity}">'
        f'{sev_display["icon"]} {_esc(sev_display["label"])}</span>\n'
        f'  <span class="pattern-group-count">{len(patterns)} similar-severity patterns</span>\n'
        f'  <h3 style="margin-top: 0.5em;">{_esc(sources_str)}</h3>\n'
        f'  <div class="pattern-meta">{_esc(metrics_str)}</div>\n'
        f'{desc_html}'
        f'  <div class="pattern-impact"><strong>What this means:</strong> {_esc(impact)}</div>\n'
        f'  <div class="pattern-recommendation"><strong>Recommendation:</strong> {_esc(recommendation)}</div>\n'
        '</div>'
    )


def _grouped_cards(patterns, badge_label):
    """Group patterns by (severity, impact) and render cards.

    Patterns with identical severity+impact text are combined into a single card
    to avoid duplicate 'What this means' content.
    """
    if not patterns:
        return []

    # Group by (severity, impact) tuple
    groups = {}
    for p in patterns:
        risk = pattern_risk_assessment(p)
        key = (risk["severity"], risk["impact"])
        groups.setdefault(key, []).append(p)

    cards = []
    # Iterate groups in the order of the first pattern in each group
    # (patterns are already sorted by severity)
    seen_keys = []
    for p in patterns:
        risk = pattern_risk_assessment(p)
        key = (risk["severity"], risk["impact"])
        if key in seen_keys:
            continue
        seen_keys.append(key)
        group = groups[key]
        if len(group) == 1:
            cards.append(_build_pattern_card(group[0], badge_label))
        else:
            cards.append(_build_grouped_pattern_card(group, badge_label))

    return cards


def _build_pattern_section(matches, candidates):
    if not matches and not candidates:
        return ""

    PATTERN_VISIBLE_LIMIT = 3

    # Assess all patterns to determine overall risk
    all_patterns = list(matches) + list(candidates)
    all_risks = [pattern_risk_assessment(p) for p in all_patterns]
    severity_counts = {}
    highest_severity = "info"
    for r in all_risks:
        sev = r["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if _severity_rank(sev) > _severity_rank(highest_severity):
            highest_severity = sev

    # Sort all patterns by severity (most critical first), unified list
    matches_set = set(id(p) for p in matches)
    all_sorted = sorted(
        all_patterns,
        key=lambda p: _severity_rank(pattern_risk_assessment(p)["severity"]),
        reverse=True,
    )

    all_cards = []
    for p in all_sorted:
        badge = "Known Pattern" if id(p) in matches_set else "New Pattern"
        all_cards.extend(_grouped_cards([p], badge))

    cards_html = _collapsible_pattern_cards(all_cards, "patterns", PATTERN_VISIBLE_LIMIT)

    # Build overall risk banner
    banner_html = _build_pattern_risk_banner(highest_severity, severity_counts, len(all_patterns))

    # User guidance
    guidance = (
        '<div class="pattern-guidance">\n'
        '  <p><strong>What are patterns?</strong> Patterns are recurring correlations between '
        'different areas of your project. When a change in one area (e.g. a deployment) '
        'consistently coincides with unusual behavior in another (e.g. code dispersion), '
        'we flag it so you can decide if it needs attention.</p>\n'
        '  <p><strong>What should you do?</strong> Focus on items marked '
        '<span class="severity-badge severity-critical">\u26a0\ufe0f Action Required</span> or '
        '<span class="severity-badge severity-concern">\U0001f50d Needs Attention</span> first. '
        'These indicate patterns that are most likely to affect code quality, stability, or security. '
        'Items marked <span class="severity-badge severity-watch">\U0001f441\ufe0f Worth Monitoring</span> '
        'don\'t need immediate action but should be reviewed if they persist. '
        '<span class="severity-badge severity-positive">\u2705 Healthy Pattern</span> and '
        '<span class="severity-badge severity-info">\u2139\ufe0f Informational</span> '
        'confirm that things are working as expected.</p>\n'
        '</div>\n'
    )

    return (
        '<section class="patterns page-break-before">\n'
        '  <h2>Patterns</h2>\n'
        f'  {banner_html}\n'
        f'  {guidance}\n'
        f'  {cards_html}\n'
        '</section>'
    )


_OVERALL_RISK_TEXT = {
    "critical": {
        "class": "risk-banner-critical",
        "title": "Immediate Review Required",
        "text": (
            "One or more patterns indicate serious risks that could affect code quality, "
            "stability, or security. Review the items below and address "
            '"Action Required" findings before your next release.'
        ),
    },
    "concern": {
        "class": "risk-banner-concern",
        "title": "Attention Recommended",
        "text": (
            "Some patterns suggest developing issues that could grow into problems "
            "if left unaddressed. Review the items marked "
            '"Needs Attention" and plan follow-up actions.'
        ),
    },
    "watch": {
        "class": "risk-banner-watch",
        "title": "Trends Worth Watching",
        "text": (
            "Several patterns are shifting outside normal ranges. None require immediate action, "
            "but monitoring these trends will help you catch issues early."
        ),
    },
    "info": {
        "class": "risk-banner-info",
        "title": "All Clear",
        "text": (
            "Patterns detected are informational or healthy. No issues require attention at this time."
        ),
    },
    "positive": {
        "class": "risk-banner-positive",
        "title": "Looking Good",
        "text": (
            "All detected patterns are healthy. Your project's development patterns "
            "are working well."
        ),
    },
}


def _build_pattern_risk_banner(highest_severity, severity_counts, total):
    """Build the overall risk assessment banner for the patterns section."""
    config = _OVERALL_RISK_TEXT.get(highest_severity, _OVERALL_RISK_TEXT["info"])

    # Build severity breakdown chips
    chips = []
    for sev in ("critical", "concern", "watch", "info", "positive"):
        count = severity_counts.get(sev, 0)
        if count > 0:
            from evolution.friendly import _SEVERITY_DISPLAY
            display = _SEVERITY_DISPLAY[sev]
            chips.append(
                f'<span class="severity-chip severity-{sev}">'
                f'{display["icon"]} {count} {display["label"]}'
                f'</span>'
            )

    chips_html = " ".join(chips)

    return (
        f'<div class="risk-banner {config["class"]}">\n'
        f'  <div class="risk-banner-title">{config["title"]}</div>\n'
        f'  <p>{config["text"]}</p>\n'
        f'  <div class="risk-banner-chips">{chips_html}</div>\n'
        f'</div>'
    )


def _collapsible_pattern_cards(cards, heading, limit):
    """Wrap pattern cards in a collapsible <details> when there are more than *limit*."""
    if not cards:
        return ""
    if len(cards) <= limit:
        return '\n'.join(cards)
    visible = '\n'.join(cards[:limit])
    hidden = '\n'.join(cards[limit:])
    extra = len(cards) - limit
    return (
        f'{visible}\n'
        f'<details class="pattern-overflow">\n'
        f'  <summary class="toggle-btn">Show {extra} more {heading}</summary>\n'
        f'  {hidden}\n'
        f'</details>'
    )


def _build_investigation_section(scope, period_from, period_to, changes,
                                  commits, files, timeline, patterns=None):
    if not changes:
        return ""

    preview = _build_prompt(
        scope, period_from, period_to, changes, commits, files, timeline,
        patterns=patterns, full=False,
    )
    full = _build_prompt(
        scope, period_from, period_to, changes, commits, files, timeline,
        patterns=patterns, full=True,
    )

    return (
        '<section class="investigation-section page-break-before">\n'
        '  <div class="next-steps-header">\n'
        '    <h2 style="margin: 0;">Next Steps: Investigate with AI</h2>\n'
        '  </div>\n'
        '  <p style="margin-bottom: 1em;">\n'
        '    We\'ve prepared an investigation prompt you can use with your AI assistant\n'
        '    (ChatGPT, Claude, etc.) to dig deeper into these changes.\n'
        '  </p>\n'
        '  <div class="investigation-expectations">\n'
        '    <h4>What to expect from the investigation:</h4>\n'
        '    <ul>\n'
        '      <li><strong>Root cause analysis</strong> \u2014 The AI will identify why these changes deviate from your normal patterns</li>\n'
        '      <li><strong>Risk assessment</strong> \u2014 Which changes need immediate attention vs. monitoring</li>\n'
        '      <li><strong>Actionable fixes</strong> \u2014 Specific code changes, config tweaks, or process adjustments to address the issues</li>\n'
        '      <li><strong>Verification</strong> \u2014 After applying fixes, re-run <code>evo analyze</code> to confirm improvements. '
        'The deviations should decrease and severity levels should drop</li>\n'
        '    </ul>\n'
        '  </div>\n'
        f'  <div class="prompt-preview">{_esc(preview)}</div>\n'
        '  <div class="action-buttons no-print">\n'
        '    <button class="btn btn-primary" onclick="copyPrompt()" id="copyBtn">Copy Prompt to Clipboard</button>\n'
        '    <button class="btn btn-secondary" onclick="savePromptToFile()">Save Prompt to File</button>\n'
        '    <button class="toggle-btn" onclick="togglePrompt()" id="togglePromptBtn">Show Full Prompt</button>\n'
        '  </div>\n'
        f'  <pre class="prompt-full" id="fullPrompt">{_esc(full)}</pre>\n'
        '</section>'
    )


def _build_adapters_section(active_families: list) -> str:
    """Build the 'Expand Your Coverage' section with adapter cards.

    Shows active adapters, available adapters the user could enable,
    and general setup guidance.
    """
    catalog = _load_adapter_catalog()
    universal_count = _load_universal_patterns_count()
    if not catalog:
        return ""

    active_set = set(active_families)
    # Normalize: "git" → "version_control"
    if "git" in active_set:
        active_set.add("version_control")

    active_adapters = [a for a in catalog if a["status"] == "available"
                       and a.get("family") in active_set]
    available_adapters = [a for a in catalog if a["status"] == "available"
                          and a.get("family") not in active_set]
    planned_adapters = [a for a in catalog if a["status"] == "planned"]

    # Active adapter cards
    active_cards = []
    for a in active_adapters:
        icon = FAMILY_ICONS.get(a["family"], "")
        label = FAMILY_LABELS.get(a["family"], a["family"])
        color = FAMILY_COLORS.get(a["family"], "#64748b")
        active_cards.append(
            f'<div class="adapter-card adapter-active">'
            f'<div class="adapter-icon" style="color: {color}">{icon}</div>'
            f'<div class="adapter-name">{_esc(a["name"])}</div>'
            f'<div class="adapter-family">{_esc(label)}</div>'
            f'<div class="adapter-status-badge active">Active</div>'
            f'</div>'
        )

    # Available adapter cards (can be enabled)
    available_cards = []
    for a in available_adapters:
        icon = FAMILY_ICONS.get(a["family"], "")
        label = FAMILY_LABELS.get(a["family"], a["family"])
        color = FAMILY_COLORS.get(a["family"], "#64748b")
        token = a.get("token")
        hint = ""
        if token:
            hint = f'<div class="adapter-hint">Set <code>{_esc(token)}</code></div>'
        elif a["tier"] == 1:
            hint = '<div class="adapter-hint">Auto-detected from files</div>'
        available_cards.append(
            f'<div class="adapter-card adapter-available">'
            f'<div class="adapter-icon" style="color: {color}">{icon}</div>'
            f'<div class="adapter-name">{_esc(a["name"])}</div>'
            f'<div class="adapter-family">{_esc(label)}</div>'
            f'<div class="adapter-desc">{_esc(a["description"])}</div>'
            f'{hint}'
            f'</div>'
        )

    # Planned adapter summary
    planned_families = sorted(set(
        FAMILY_LABELS.get(a["family"], a["family"]) for a in planned_adapters
    ))

    # Build the section
    parts = []
    parts.append('<section class="adapters-section page-break-before">')
    parts.append('  <h2>Expand Your Coverage</h2>')

    # Universal patterns stat
    parts.append(
        '  <div class="adapters-intro">'
        f'    <p>Evolution Engine has <strong>{universal_count} universal patterns</strong> '
        'learned from 58+ open-source repositories. The more signal families you connect, '
        'the more cross-family patterns can be detected.</p>'
        '  </div>'
    )

    # Active adapters
    if active_cards:
        parts.append('  <h3>Currently Active</h3>')
        parts.append('  <div class="adapter-grid">')
        parts.extend(f'    {c}' for c in active_cards)
        parts.append('  </div>')

    # Available adapters
    if available_cards:
        parts.append('  <h3>Available Adapters</h3>')
        parts.append(
            '  <p class="adapters-subtitle">Enable these adapters to unlock additional signal families '
            'and cross-family pattern detection.</p>'
        )
        parts.append('  <div class="adapter-grid">')
        parts.extend(f'    {c}' for c in available_cards)
        parts.append('  </div>')

        # General setup guidance
        parts.append('  <div class="adapter-setup-guide">')
        parts.append('    <h4>How to Connect an Adapter</h4>')
        parts.append('    <ol>')
        parts.append(
            '      <li><strong>Set the environment variable</strong> shown on the adapter card. '
            'For example: <code>export GITHUB_TOKEN=$(gh auth token)</code></li>'
        )
        parts.append(
            '      <li><strong>For file-based adapters</strong> (Testing, Coverage): '
            'generate reports in your project first. '
            'For example, <code>pytest --junitxml=junit.xml</code> or '
            '<code>pytest --cov --cov-report=xml</code></li>'
        )
        parts.append(
            '      <li><strong>Run analysis</strong>: <code>evo analyze .</code> &mdash; '
            'new adapters are detected automatically</li>'
        )
        parts.append(
            '      <li><strong>Verify</strong>: <code>evo sources</code> to confirm '
            'which adapters are active</li>'
        )
        parts.append('    </ol>')
        parts.append('  </div>')

    # Planned adapters teaser
    if planned_families:
        parts.append(
            '  <div class="adapters-planned">'
            f'    <strong>Coming soon:</strong> {", ".join(_esc(f) for f in planned_families)}'
            '  </div>'
        )

    parts.append('</section>')
    return '\n'.join(parts)


# ─── Prompt Builder ───


_BUILD_ARTIFACT_EXTS = {".map", ".d.ts", ".d.ts.map", ".js.map", ".css.map"}


def _is_build_artifact(path: str) -> bool:
    """Return True for generated/build artifact file paths."""
    for ext in _BUILD_ARTIFACT_EXTS:
        if path.endswith(ext):
            return True
    return False


def _build_prompt(scope, period_from, period_to, changes, commits, files,
                  timeline, patterns=None, full=False):
    lines = [
        f"Development drift analysis for {scope} ({period_from} to {period_to}).",
        "",
        "DEVIATIONS FROM BASELINE:",
        "",
    ]

    for c in changes:
        family = FAMILY_LABELS.get(c.get("family", ""), c.get("family", ""))
        metric = METRIC_LABELS.get(c.get("metric", ""), c.get("metric", ""))
        current = c.get("current", 0)
        normal = c.get("normal", {})
        median = normal.get("median", normal.get("mean", 0))
        dev = c.get("deviation_stddev", 0)
        d = "above" if dev >= 0 else "below"
        line = f"- {family} / {metric}: {_fmt_num(current)} (typical: {_fmt_num(median)}, {abs(dev):.1f}x {d})"
        if not full:
            line = f"- {family}: {metric} — {_fmt_num(median)} -> {_fmt_num(current)}"
        lines.append(line)

    if not full:
        lines.append("")
        lines.append('Click "Show Full Prompt" to see the complete investigation prompt with evidence...')
        return "\n".join(lines)

    # Pattern risk context — only actionable patterns (skip healthy/informational)
    if patterns:
        actionable = [
            p for p in patterns
            if _severity_rank(pattern_risk_assessment(p)["severity"]) >= 2  # watch+
        ]
        if actionable:
            sorted_pats = sorted(
                actionable,
                key=lambda p: _severity_rank(pattern_risk_assessment(p)["severity"]),
                reverse=True,
            )
            lines.extend(["", "RISK PATTERNS (actionable only):", ""])

            # Group by (severity, impact), deduplicate descriptions within each group
            groups = {}
            group_order = []
            for p in sorted_pats:
                risk = pattern_risk_assessment(p)
                key = (risk["severity"], risk["impact"])
                if key not in groups:
                    groups[key] = []
                    group_order.append(key)
                groups[key].append(p)

            for key in group_order:
                group = groups[key]
                risk = pattern_risk_assessment(group[0])
                sev_label = risk["severity_display"]["label"]
                # Deduplicate descriptions within group
                seen_descs = []
                for p in group:
                    desc = friendly_pattern(p)
                    if desc and desc not in seen_descs:
                        seen_descs.append(desc)
                if len(seen_descs) == 1:
                    lines.append(f"- [{sev_label}] {seen_descs[0]}")
                    if len(group) > 1:
                        lines.append(f"  ({len(group)} independent confirmations)")
                else:
                    lines.append(f"- [{sev_label}] {len(seen_descs)} patterns:")
                    for d in seen_descs:
                        lines.append(f"    * {d}")
                lines.append(f"  Impact: {risk['impact']}")
                lines.append(f"  Action: {risk['recommendation']}")
                lines.append("")

    # Evidence — commits
    if commits:
        lines.extend(["", f"COMMITS ({len(commits)}):", ""])
        for c in commits[:10]:
            sha = c.get("sha", "")[:8]
            msg = c.get("message", "").split("\n")[0][:80]
            n_files = len(c.get("files_changed", []))
            lines.append(f"  {sha} — {msg} ({n_files} files)")
        if len(commits) > 10:
            lines.append(f"  ... and {len(commits) - 10} more")
        lines.append("")

    # Evidence — source files only (skip build artifacts)
    if files:
        source_files = [f for f in files if not _is_build_artifact(f.get("path", ""))]
        if source_files:
            lines.append(f"SOURCE FILES CHANGED ({len(source_files)}):")
            lines.append("")
            for f in source_files[:20]:
                path = f.get("path", "")
                ct = f.get("change_type", "")
                lines.append(f"  - {path} ({ct})")
            if len(source_files) > 20:
                lines.append(f"  ... and {len(source_files) - 20} more")
            lines.append("")

    lines.extend([
        "TASKS:",
        "",
        "1. ROOT CAUSE: For each deviation, identify the commit(s) that caused it.",
        "   Focus on [Action Required] and [Needs Attention] items first.",
        "",
        "2. FIXES: Provide concrete fixes with file paths and code changes.",
        "   Goal: bring metrics back toward baseline without disrupting velocity.",
        "",
        "3. PRIORITY: Rank fixes by urgency (immediate vs. next sprint).",
        "",
        "4. AFTER FIXING: Run `evo analyze . --verify` to confirm deviations decreased.",
        "   If a change was intentional, accept it: `evo accept . <N>`.",
    ])

    return "\n".join(lines)


# ─── Helpers ───


def _fmt_value(v) -> str:
    """Format a metric value for human-readable display."""
    if v is None:
        return "\u2014"
    if isinstance(v, (int, float)) and float(v) == int(v) and abs(v) < 1e9:
        return f"{int(v):,}"
    if isinstance(v, float):
        if abs(v) >= 100:
            return f"{v:,.0f}"
        return f"{v:.2f}"
    return str(v)


def _value_near_baseline(latest_value, normal_dict: dict,
                         threshold: float = 1.5) -> bool:
    """Check if the latest observed value is close to the global baseline."""
    if latest_value is None or not normal_dict:
        return True  # fallback: assume returned
    median = normal_dict.get("median")
    if median is None:
        return True
    mad = normal_dict.get("mad", 0)
    if mad and mad > 0:
        modified_z = abs(0.6745 * (latest_value - median) / mad)
        return modified_z < threshold
    stddev = normal_dict.get("stddev", 0)
    if stddev and stddev > 0:
        z = abs((latest_value - median) / stddev)
        return z < threshold
    return latest_value == median


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt_num(n) -> str:
    """Format a number for display."""
    if isinstance(n, int):
        return f"{n:,}"
    if isinstance(n, float):
        if abs(n) >= 100:
            return f"{n:,.1f}"
        if abs(n) >= 1:
            return f"{n:.2f}"
        return f"{n:.4f}"
    return str(n)


def _format_date(iso_str: str) -> str:
    """Format ISO date to readable form."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except (ValueError, TypeError):
        return iso_str[:16] if len(iso_str) > 16 else iso_str


def _bar_widths(current, median):
    """Calculate percentage widths for the bar chart (normal_w, current_w)."""
    try:
        abs_c = abs(float(current))
    except (TypeError, ValueError):
        abs_c = 0
    try:
        abs_m = abs(float(median))
    except (TypeError, ValueError):
        abs_m = 0
    mx = max(abs_c, abs_m, 0.001)
    return round(abs_m / mx * 100), round(abs_c / mx * 100)


def _deviation_class(dev):
    """CSS class for a deviation value."""
    a = abs(dev)
    if a >= 4.0:
        return "deviation-high"
    if a >= 2.0:
        return "deviation-medium"
    return "deviation-low"


# ─── CSS ───

_CSS = """:root {
  --color-primary: #0A4D4A;
  --color-primary-light: #0F6B67;
  --color-secondary: #2CA58D;
  --color-accent: #FF6B6B;
  --color-text: #1f2937;
  --color-text-muted: #64748B;
  --color-border: #E2E8F0;
  --color-bg: #FFFFFF;
  --color-bg-subtle: #F8FAFC;
  --color-success: #2CA58D;
  --color-warning: #F59E0B;
  --color-danger: #EF4444;
  --color-info: #06B6D4;
  --color-normal: #94a3b8;
  --color-current: #2CA58D;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 11pt; line-height: 1.6; color: var(--color-text);
  background: var(--color-bg); max-width: 1200px; margin: 0 auto; padding: 2em;
}
h1, h2, h3 { font-weight: 700; color: var(--color-primary); }
h1 { font-size: 28pt; margin-bottom: 0.5em; }
h2 { font-size: 18pt; margin-top: 1.5em; margin-bottom: 0.75em;
  border-bottom: 2px solid var(--color-border); padding-bottom: 0.5em; }
h3 { font-size: 14pt; margin-top: 1em; margin-bottom: 0.5em; }
code, pre { font-family: 'SF Mono', 'Monaco', 'Courier New', monospace; font-size: 10pt; }
code { background: var(--color-bg-subtle); padding: 0.2em 0.4em; border-radius: 4px; }
pre { background: var(--color-bg-subtle); padding: 1em; border-radius: 8px;
  overflow-x: auto; border: 1px solid var(--color-border); }
.logo { width: 48px; height: 56px; margin-bottom: 1em; }
.cover-page { min-height: 80vh; display: flex; flex-direction: column;
  justify-content: center; align-items: center; text-align: center; }
.cover-page h1 { font-size: 42pt; margin-bottom: 0.5em; }
.cover-brand { font-size: 18pt; color: var(--color-secondary); font-weight: 600;
  margin-bottom: 2em; }
.cover-metadata { font-size: 12pt; color: var(--color-text-muted); line-height: 2; }
.cover-metadata p { margin: 0.5em 0; }
.cover-metadata strong { color: var(--color-text); margin-right: 0.5em; }
.executive-summary { margin-top: 2em; }
.summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5em; margin: 1.5em 0; }
.summary-card { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  border-radius: 8px; padding: 1.5em; text-align: center; }
.summary-value { font-size: 32pt; font-weight: 700; color: var(--color-primary);
  margin-bottom: 0.25em; }
.summary-label { font-size: 11pt; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em; }
.summary-families { margin-top: 1em; padding: 1em; background: var(--color-bg-subtle);
  border-radius: 8px; border-left: 4px solid var(--color-secondary); }
.key-findings { margin-top: 1.5em; }
.findings-list { list-style: none; padding: 0; }
.findings-list li { padding: 0.75em 1em; margin-bottom: 0.5em; background: var(--color-bg-subtle);
  border-left: 3px solid var(--color-secondary); border-radius: 0 6px 6px 0; line-height: 1.5; }
.findings-list li strong { color: var(--color-primary); }
.change-card { border: 1px solid var(--color-border); border-left: 4px solid var(--color-secondary);
  padding: 1.5em; margin-bottom: 1.5em; background: var(--color-bg-subtle);
  border-radius: 8px; page-break-inside: avoid; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.change-card.deviation-high { border-left-color: var(--color-danger); }
.change-card.deviation-medium { border-left-color: var(--color-warning); }
.change-card.deviation-low { border-left-color: var(--color-success); }
.change-card-header { display: flex; align-items: center; margin-bottom: 1em; }
.family-icon { font-size: 24pt; margin-right: 0.5em; }
.metric-name { font-size: 14pt; font-weight: 600; color: var(--color-primary); }
.family-label { font-size: 10pt; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em; }
.user-friendly-summary { background: #fff; padding: 1em; border-radius: 6px;
  margin-bottom: 1em; border: 1px solid var(--color-border); }
.user-friendly-summary strong { color: var(--color-primary); }
.bar-chart { margin: 1em 0; }
.bar-chart-row { display: flex; align-items: center; margin-bottom: 0.5em; }
.bar-label { width: 100px; font-size: 10pt; color: var(--color-text-muted);
  text-align: right; padding-right: 1em; }
.bar-container { flex: 1; height: 24px; background: var(--color-border);
  border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--color-current); border-radius: 4px 0 0 4px; }
.bar-fill.normal { background: var(--color-normal); }
.bar-value { margin-left: 1em; font-weight: 600; white-space: nowrap; min-width: 80px; }
.deviation-badge { display: inline-block; background: var(--color-secondary); color: white;
  padding: 0.25em 0.75em; border-radius: 4px; font-size: 9pt; font-weight: 600;
  margin-top: 0.5em; }
.technical-detail { margin-top: 0.5em; padding-top: 0.5em;
  border-top: 1px dashed var(--color-border); font-size: 9pt;
  color: var(--color-text-muted); font-style: italic; }
.technical-detail summary { cursor: pointer; color: var(--color-secondary); font-weight: 500; }
.technical-detail summary:hover { text-decoration: underline; }
.pattern-card { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  border-radius: 8px; padding: 1.5em; margin-bottom: 1.5em; }
.severity-badge { display: inline-block; padding: 0.25em 0.75em; border-radius: 4px;
  font-weight: 600; font-size: 9pt; margin-left: 0.5em; }
.severity-badge.severity-critical { background: #dc2626; color: white; }
.severity-badge.severity-concern { background: #ea580c; color: white; }
.severity-badge.severity-watch { background: #d97706; color: white; }
.severity-badge.severity-info { background: #0284c7; color: white; }
.severity-badge.severity-positive { background: #16a34a; color: white; }
.pattern-impact { background: #fff; padding: 1em; border-radius: 6px;
  margin: 0.75em 0; border: 1px solid var(--color-border); }
.pattern-recommendation { padding: 0.75em 1em; border-radius: 6px;
  background: var(--color-bg-subtle); border-left: 3px solid var(--color-secondary);
  font-size: 10pt; margin-top: 0.5em; }
.severity-border-critical { border-left: 4px solid #dc2626 !important; }
.severity-border-concern { border-left: 4px solid #ea580c !important; }
.severity-border-watch { border-left: 4px solid #d97706 !important; }
.severity-border-info { border-left: 4px solid #0284c7 !important; }
.severity-border-positive { border-left: 4px solid #16a34a !important; }
.risk-banner { padding: 1.5em; border-radius: 8px; margin-bottom: 1.5em; }
.risk-banner-title { font-size: 14pt; font-weight: 700; margin-bottom: 0.5em; }
.risk-banner p { margin-bottom: 0.75em; line-height: 1.6; }
.risk-banner-chips { display: flex; gap: 0.75em; flex-wrap: wrap; margin-top: 0.5em; }
.severity-chip { display: inline-flex; align-items: center; gap: 0.25em; padding: 0.3em 0.75em;
  border-radius: 4px; font-size: 9pt; font-weight: 600; background: rgba(255,255,255,0.7); }
.risk-banner-critical { background: #fef2f2; border: 2px solid #dc2626;
  border-left: 6px solid #dc2626; }
.risk-banner-critical .risk-banner-title { color: #991b1b; }
.risk-banner-concern { background: #fff7ed; border: 2px solid #ea580c;
  border-left: 6px solid #ea580c; }
.risk-banner-concern .risk-banner-title { color: #9a3412; }
.risk-banner-watch { background: #fffbeb; border: 2px solid #d97706;
  border-left: 6px solid #d97706; }
.risk-banner-watch .risk-banner-title { color: #92400e; }
.risk-banner-info { background: #f0f9ff; border: 2px solid #0284c7;
  border-left: 6px solid #0284c7; }
.risk-banner-info .risk-banner-title { color: #075985; }
.risk-banner-positive { background: #f0fdf4; border: 2px solid #16a34a;
  border-left: 6px solid #16a34a; }
.risk-banner-positive .risk-banner-title { color: #166534; }
.pattern-guidance { background: var(--color-bg-subtle); padding: 1.25em 1.5em;
  border-radius: 8px; margin-bottom: 1.5em; border: 1px solid var(--color-border);
  font-size: 10pt; line-height: 1.7; }
.pattern-guidance p { margin-bottom: 0.75em; }
.pattern-guidance p:last-child { margin-bottom: 0; }
.pattern-guidance .severity-badge { font-size: 8pt; vertical-align: middle; }
.investigation-expectations { background: var(--color-bg-subtle); padding: 1.25em 1.5em;
  border-radius: 8px; margin-bottom: 1.5em; border: 1px solid var(--color-border); }
.investigation-expectations h4 { color: var(--color-primary); margin-bottom: 0.75em; }
.investigation-expectations ul { list-style: none; padding: 0; }
.investigation-expectations li { padding: 0.5em 0; padding-left: 1.5em; position: relative;
  line-height: 1.6; }
.investigation-expectations li:before { content: '\\2192'; position: absolute; left: 0;
  color: var(--color-secondary); font-weight: 700; }
.pattern-group-count { display: inline-block; padding: 0.2em 0.6em; border-radius: 4px;
  font-size: 9pt; font-weight: 600; color: var(--color-text-muted);
  background: var(--color-border); margin-left: 0.5em; }
.grouped-pattern-list { list-style: disc; padding-left: 1.5em; margin: 0.5em 0 1em 0;
  font-size: 10pt; line-height: 1.7; }
.grouped-pattern-list li { margin-bottom: 0.3em; }
.pattern-meta { display: flex; gap: 1em; margin: 0.5em 0 1em 0;
  font-size: 10pt; color: var(--color-text-muted); }
.badge { background: var(--color-primary); color: white; padding: 0.25em 0.75em;
  border-radius: 4px; font-weight: 600; text-transform: uppercase; font-size: 9pt; }
.investigation-section { background: #fff; border: 2px solid var(--color-secondary);
  border-radius: 8px; padding: 2em; margin: 2em 0; }
.next-steps-header { display: flex; align-items: center; gap: 0.5em; margin-bottom: 1em; }
.action-buttons { display: flex; gap: 1em; margin: 1em 0; flex-wrap: wrap; }
.btn { padding: 0.75em 1.5em; border-radius: 6px; font-weight: 600; font-size: 10pt;
  cursor: pointer; border: none; transition: all 250ms ease-out; }
.btn-primary { background: var(--color-accent); color: white; }
.btn-primary:hover { background: #FF5252; }
.btn-secondary { background: var(--color-secondary); color: white; }
.btn-secondary:hover { background: var(--color-primary-light); }
.prompt-preview { background: #f8f9fa; border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-secondary); padding: 1em; border-radius: 6px;
  margin: 1em 0; font-size: 9pt; line-height: 1.6; max-height: 200px;
  overflow-y: auto; white-space: pre-wrap; font-family: 'SF Mono', monospace; }
.prompt-full { display: none; background: #f8f9fa; border: 1px solid var(--color-border);
  padding: 1.5em; border-radius: 6px; margin: 1em 0; white-space: pre-wrap;
  font-size: 10pt; line-height: 1.6; font-family: 'SF Mono', monospace; }
.prompt-full.show { display: block; }
.toggle-btn { background: white; border: 1px solid var(--color-secondary);
  color: var(--color-secondary); padding: 0.5em 1em; border-radius: 6px;
  cursor: pointer; font-weight: 600; font-size: 10pt; }
.toggle-btn:hover { background: var(--color-bg-subtle); }
.toggle-btn.active { background: var(--color-secondary); color: white; }
.empty { color: var(--color-text-muted); font-style: italic; text-align: center; padding: 2rem; }
.more { font-size: 9pt; color: var(--color-text-muted); margin-top: 0.5em; font-style: italic; }
.evidence-overflow { display: none; }
.evidence-overflow.show { display: table-row-group; }
div.evidence-overflow { display: none; }
div.evidence-overflow.show { display: block; }
.pattern-overflow { margin-top: 0.5em; }
.pattern-overflow > summary { list-style: none; display: inline-block; margin-top: 0.5em; }
.pattern-overflow > summary::-webkit-details-marker { display: none; }
.severity-filters { display: flex; gap: 0.5em; margin-bottom: 1.5em; flex-wrap: wrap; }
.btn-filter { background: white; border: 1px solid var(--color-border); color: var(--color-text);
  padding: 0.5em 1em; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 10pt;
  transition: all 250ms ease-out; }
.btn-filter:hover { background: var(--color-bg-subtle); border-color: var(--color-secondary); }
.btn-filter.active { background: var(--color-secondary); color: white;
  border-color: var(--color-secondary); }
.change-actions { display: flex; gap: 0.5em; margin-top: 0.75em; align-items: flex-start; }
.btn-action { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  color: var(--color-primary); padding: 0.4em 1em; border-radius: 6px; cursor: pointer;
  font-weight: 600; font-size: 9pt; transition: all 250ms ease-out; }
.btn-action:hover { background: var(--color-secondary); color: white;
  border-color: var(--color-secondary); }
.accept-group { position: relative; }
.accept-menu { display: none; position: absolute; top: 100%; left: 0; margin-top: 4px;
  background: white; border: 1px solid var(--color-border); border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1); z-index: 10; min-width: 200px; }
.accept-menu.show { display: block; }
.accept-menu button { display: block; width: 100%; text-align: left; padding: 0.6em 1em;
  border: none; background: none; cursor: pointer; font-size: 9pt; color: var(--color-text); }
.accept-menu button:hover { background: var(--color-bg-subtle); }
.accept-menu button:first-child { border-radius: 6px 6px 0 0; }
.accept-menu button:last-child { border-radius: 0 0 6px 6px; }
.accept-hint { display: block; font-size: 8pt; color: var(--color-text-muted); font-weight: 400; }
.btn-accept.accepted { background: var(--color-success); color: white;
  border-color: var(--color-success); pointer-events: none; }
.btn-fix { color: var(--color-secondary); }
.fix-prompt-panel { display: none; margin-top: 0.75em; background: var(--color-bg-subtle);
  border: 1px solid var(--color-border); border-radius: 8px; padding: 1em; }
.fix-prompt-panel.show { display: block; }
.fix-prompt-header { display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 0.5em; }
.fix-prompt-text { background: white; border: 1px solid var(--color-border);
  border-radius: 6px; padding: 0.75em; font-size: 9pt; white-space: pre-wrap;
  word-break: break-word; max-height: 200px; overflow-y: auto; margin: 0; }
.btn-copy-sm { background: var(--color-secondary); color: white; border: none;
  padding: 0.3em 0.8em; border-radius: 4px; cursor: pointer; font-size: 8pt;
  font-weight: 600; }
.btn-copy-sm:hover { opacity: 0.85; }
.fix-prompt-guide { margin-top: 0.5em; font-size: 8pt; color: var(--color-text-muted);
  display: flex; gap: 1em; flex-wrap: wrap; }
.fix-prompt-guide span { background: white; padding: 0.2em 0.5em; border-radius: 4px;
  border: 1px solid var(--color-border); }
.fix-next-steps { margin-top: 0.75em; padding: 0.75em 1em; background: white;
  border: 1px solid var(--color-border); border-left: 3px solid var(--color-secondary);
  border-radius: 0 6px 6px 0; font-size: 9pt; }
.fix-next-steps strong { color: var(--color-primary); }
.fix-next-steps ol { margin: 0.4em 0 0 1.25em; line-height: 1.8; }
.fix-next-steps code { font-size: 8pt; }
.progress-tracker { display: flex; align-items: center; gap: 0.75em;
  margin-bottom: 1em; font-size: 10pt; font-weight: 600; color: var(--color-text-muted); }
.progress-bar { flex: 1; max-width: 200px; height: 6px; background: var(--color-border);
  border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--color-success); border-radius: 3px;
  transition: width 300ms ease-out; }
.commit-attribution { font-size: 9pt; color: var(--color-text-muted); margin-top: 0.5em; }
.commit-link { color: var(--color-secondary); text-decoration: none; }
.commit-link:hover { text-decoration: underline; }
.confidence-note { font-size: 9pt; color: var(--color-text-muted); margin-top: 0.5em;
  font-style: italic; }
.change-card.filter-hidden { display: none; }
.ide-link { font-size: 8pt; color: var(--color-secondary); text-decoration: none;
  margin-left: 0.5em; font-weight: 600; }
.ide-link:hover { text-decoration: underline; }
.verification-banner { padding: 1.5em; border-radius: 8px; margin: 1.5em 0; }
.verify-all-clear { background: #f0fdf4; border: 2px solid #16a34a; }
.verify-improving { background: #eff6ff; border: 2px solid #2563eb; }
.verify-no-change { background: #fefce8; border: 2px solid #ca8a04; }
.verify-header { display: flex; align-items: center; gap: 0.75em; margin-bottom: 1em; }
.verify-icon { font-size: 24pt; }
.verify-title { font-size: 14pt; font-weight: 700; color: var(--color-primary); }
.verify-subtitle { font-size: 10pt; color: var(--color-text-muted); }
.verify-chips { display: flex; gap: 0.5em; flex-wrap: wrap; margin-bottom: 1em; }
.verify-chip { display: inline-flex; align-items: center; gap: 0.25em; padding: 0.3em 0.75em;
  border-radius: 4px; font-size: 9pt; font-weight: 600; }
.verify-chip-resolved { background: #dcfce7; color: #166534; }
.verify-chip-improving { background: #dbeafe; color: #1e40af; }
.verify-chip-flat { background: #f5f5f4; color: #57534e; }
.verify-chip-new { background: #fef3c7; color: #92400e; }
.verify-table { width: 100%; border-collapse: collapse; font-size: 10pt; }
.verify-table th { text-align: left; padding: 0.5em 0.75em; font-weight: 600;
  color: var(--color-primary); border-bottom: 2px solid var(--color-border); }
.verify-table td { padding: 0.5em 0.75em; border-bottom: 1px solid var(--color-border); }
.verify-resolved td { color: #166534; }
.verify-trend-good { color: #2563eb; font-weight: 600; }
.verify-trend-flat { color: #78716c; }
.verify-note { margin-top: 1em; padding: 0.75em 1em; background: #f8fafc;
  border-left: 3px solid var(--color-info); font-size: 10pt; color: var(--color-text-muted);
  border-radius: 0 4px 4px 0; line-height: 1.5; }
.verify-trend-warn { color: #dc2626; font-weight: 600; }
.verify-trend-stabilized { color: #dc6803; font-weight: 600; }
.verify-note-stabilized { margin-top: 1em; padding: 0.75em 1em; background: #fffbeb;
  border-left: 3px solid #f59e0b; font-size: 10pt; color: #92400e;
  border-radius: 0 4px 4px 0; line-height: 1.5; }
.verify-note-warn { margin-top: 1em; padding: 0.75em 1em; background: #fef2f2;
  border-left: 3px solid #dc2626; font-size: 10pt; color: #991b1b;
  border-radius: 0 4px 4px 0; line-height: 1.5; }
.trend-subtitle { font-size: 9pt; margin-top: 0.25em; color: #78716c; }
.trend-returning { color: #166534; }
.trend-elevated { color: #dc6803; }
.verify-baseline { color: var(--color-text-muted); font-size: 9pt; }
.verify-new td { color: #92400e; }
.page-break-before { page-break-before: always; }
.page-break-after { page-break-after: always; }
footer { margin-top: 4em; padding-top: 2em; border-top: 1px solid var(--color-border);
  text-align: center; color: var(--color-text-muted); font-size: 9pt; }
footer strong { color: var(--color-secondary); }
/* ─── Adapters Section ─── */
.adapters-section { margin-top: 2em; }
.adapters-intro { padding: 1em 1.5em; background: var(--color-bg-subtle);
  border-left: 4px solid var(--color-secondary); border-radius: 0 8px 8px 0;
  margin-bottom: 1.5em; }
.adapters-intro p { margin: 0; }
.adapters-subtitle { color: var(--color-text-muted); margin-bottom: 1em; }
.adapter-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1em; margin: 1em 0 1.5em; }
.adapter-card { border: 1px solid var(--color-border); border-radius: 8px;
  padding: 1.2em; background: var(--color-bg); position: relative;
  transition: box-shadow 0.2s; }
.adapter-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.adapter-active { border-left: 3px solid var(--color-success); }
.adapter-available { border-left: 3px solid var(--color-info); }
.adapter-icon { font-size: 20pt; margin-bottom: 0.3em; }
.adapter-name { font-weight: 600; font-size: 11pt; color: var(--color-primary); }
.adapter-family { font-size: 9pt; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5em; }
.adapter-desc { font-size: 9pt; color: var(--color-text-muted); line-height: 1.4;
  margin-bottom: 0.5em; }
.adapter-hint { font-size: 9pt; color: var(--color-info); }
.adapter-hint code { font-size: 8.5pt; background: #e0f2fe; color: #0369a1;
  padding: 0.15em 0.4em; border-radius: 3px; }
.adapter-status-badge { font-size: 8pt; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; padding: 0.2em 0.6em; border-radius: 12px;
  position: absolute; top: 1em; right: 1em; }
.adapter-status-badge.active { background: #d1fae5; color: #065f46; }
.adapter-setup-guide { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  border-radius: 8px; padding: 1.5em; margin: 1.5em 0; }
.adapter-setup-guide h4 { margin-top: 0; margin-bottom: 0.75em;
  color: var(--color-primary); font-size: 12pt; }
.adapter-setup-guide ol { padding-left: 1.5em; }
.adapter-setup-guide li { margin-bottom: 0.75em; line-height: 1.5; }
.adapters-planned { padding: 1em 1.5em; background: var(--color-bg-subtle);
  border-radius: 8px; color: var(--color-text-muted); font-size: 10pt;
  margin-top: 1em; }
@media print {
  body { font-size: 10pt; padding: 0; }
  .btn, .toggle-btn, .action-buttons { display: none !important; }
  .prompt-full { display: block !important; }
  details.pattern-overflow > summary { display: none !important; }
  details.pattern-overflow > summary ~ * { display: block !important; }
  details[open] summary ~ * { display: block; }
  .no-print { display: none; }
  .cover-page { min-height: auto; padding: 4em 0; }
}"""

# ─── JS ───

_JS = """<script>
// Clipboard helper — works on file:// URLs where navigator.clipboard is blocked
function _copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  // Fallback for file:// protocol
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch(e) {}
  document.body.removeChild(ta);
  return Promise.resolve();
}
function _flashBtn(btn, label, duration) {
  var orig = btn.textContent;
  btn.textContent = label;
  btn.style.background = 'var(--color-success)';
  btn.style.color = 'white';
  btn.style.borderColor = 'var(--color-success)';
  setTimeout(function() {
    btn.textContent = orig;
    btn.style.background = '';
    btn.style.color = '';
    btn.style.borderColor = '';
  }, duration || 2000);
}
function copyPrompt() {
  var el = document.getElementById('fullPrompt');
  if (!el) return;
  _copyText(el.textContent).then(function() {
    _flashBtn(document.getElementById('copyBtn'), 'Copied!');
  });
}
function savePromptToFile() {
  var el = document.getElementById('fullPrompt');
  if (!el) return;
  var blob = new Blob([el.textContent], { type: 'text/plain' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url; a.download = 'investigation_prompt.txt';
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}
function togglePrompt() {
  var f = document.getElementById('fullPrompt');
  var b = document.getElementById('togglePromptBtn');
  if (!f || !b) return;
  f.classList.toggle('show'); b.classList.toggle('active');
  b.textContent = f.classList.contains('show') ? 'Hide Full Prompt' : 'Show Full Prompt';
}
function toggleTableRows(id, btn) {
  var el = document.getElementById(id);
  if (!el || !btn) return;
  el.classList.toggle('show');
  btn.classList.toggle('active');
  if (el.classList.contains('show')) {
    btn.textContent = 'Collapse';
  } else {
    btn.textContent = btn.getAttribute('data-label') || 'Show all';
  }
}
function copyCommand(btn, cmd) {
  var text = cmd.replace(/&quot;/g, '"');
  _copyText(text).then(function() { _flashBtn(btn, 'Copied!'); });
}
function toggleAcceptMenu(idx) {
  var menu = document.getElementById('accept-menu-' + idx);
  if (!menu) return;
  document.querySelectorAll('.accept-menu.show').forEach(function(m) {
    if (m !== menu) m.classList.remove('show');
  });
  menu.classList.toggle('show');
}
function _markAccepted(idx) {
  var menu = document.getElementById('accept-menu-' + idx);
  if (menu) menu.classList.remove('show');
  var actions = document.getElementById('actions-' + idx);
  if (actions) {
    var btn = actions.querySelector('.btn-accept');
    if (btn) {
      btn.textContent = 'Accepted \u2713';
      btn.classList.add('accepted');
    }
  }
  updateProgress();
}
function _showToast(msg) {
  var existing = document.getElementById('report-toast');
  if (existing) existing.remove();
  var t = document.createElement('div');
  t.id = 'report-toast';
  t.style.cssText = 'position:fixed;bottom:2em;right:2em;background:#0A4D4A;color:white;padding:0.75em 1.5em;border-radius:8px;font-weight:500;z-index:1000;opacity:0;transition:opacity 0.3s;';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function() { t.style.opacity = '1'; }, 10);
  setTimeout(function() { t.style.opacity = '0'; setTimeout(function() { t.remove(); }, 300); }, 2500);
}
function acceptFinding(idx, scope, cmd) {
  var changeIndex = idx + 1;
  fetch('/api/accept', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({index: changeIndex, scope: scope, reason: 'Expected behavior'})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) { _markAccepted(idx); _showToast('Accepted'); })
  .catch(function() {
    var text = cmd.replace(/&quot;/g, '"');
    _copyText(text).then(function() {
      _markAccepted(idx);
      _showToast('Command copied \u2014 paste in terminal to accept');
    });
  });
}
function updateProgress() {
  var total = document.querySelectorAll('.btn-accept').length;
  var resolved = document.querySelectorAll('.btn-accept.accepted').length;
  var counter = document.getElementById('resolvedCount');
  var fill = document.getElementById('progressFill');
  if (counter) counter.textContent = resolved;
  if (fill) fill.style.width = (total > 0 ? (resolved / total * 100) : 0) + '%';
}
function toggleFixPrompt(idx) {
  var panel = document.getElementById('fix-prompt-' + idx);
  if (panel) panel.classList.toggle('show');
}
function copyFixPrompt(idx) {
  var el = document.getElementById('fix-prompt-text-' + idx);
  if (!el) return;
  var text = el.textContent.replace(/\\\\n/g, '\\n');
  _copyText(text).then(function() {
    var btn = el.parentElement.querySelector('.btn-copy-sm');
    if (btn) {
      btn.textContent = 'Copied!';
      setTimeout(function() { btn.textContent = 'Copy'; }, 2000);
    }
  });
}
function filterChanges(level, btn) {
  var cards = document.querySelectorAll('.change-card');
  var buttons = document.querySelectorAll('.btn-filter');
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].classList.remove('active');
  }
  btn.classList.add('active');
  for (var j = 0; j < cards.length; j++) {
    if (level === 'all') {
      cards[j].classList.remove('filter-hidden');
    } else {
      if (cards[j].classList.contains(level)) {
        cards[j].classList.remove('filter-hidden');
      } else {
        cards[j].classList.add('filter-hidden');
      }
    }
  }
}
document.addEventListener('DOMContentLoaded', function() {
  var btns = document.querySelectorAll('button[onclick^="toggleTableRows"]');
  for (var i = 0; i < btns.length; i++) {
    btns[i].setAttribute('data-label', btns[i].textContent);
  }
  // Close accept menus when clicking outside
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.accept-group')) {
      document.querySelectorAll('.accept-menu.show').forEach(function(m) {
        m.classList.remove('show');
      });
    }
  });
  // Mark already-accepted items on page load (server mode only, silent fail on file://)
  fetch('/api/accepted')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var accepted = data.accepted || [];
      var cards = document.querySelectorAll('.change-card');
      cards.forEach(function(card, idx) {
        var id = card.id || '';
        for (var i = 0; i < accepted.length; i++) {
          var key = accepted[i].key || '';
          var parts = key.split(':');
          if (parts.length === 2 && id === 'change-' + parts[0] + '-' + parts[1]) {
            _markAccepted(idx);
            break;
          }
        }
      });
    })
    .catch(function() { /* file:// mode — ignore */ });
});
</script>"""
