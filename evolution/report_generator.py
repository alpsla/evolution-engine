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
from datetime import datetime
from pathlib import Path

from evolution.friendly import (
    risk_level, relative_change, metric_insight, friendly_pattern,
    pattern_risk_assessment, _severity_rank,
)

FAMILY_LABELS = {
    "git": "Version Control",
    "version_control": "Version Control",
    "ci": "CI / Build",
    "testing": "Testing",
    "dependency": "Dependencies",
    "schema": "API / Schema",
    "deployment": "Deployment",
    "config": "Configuration",
    "security": "Security",
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
    "ci": "#f59e0b",
    "testing": "#10b981",
    "dependency": "#8b5cf6",
    "schema": "#ec4899",
    "deployment": "#06b6d4",
    "config": "#6366f1",
    "security": "#ef4444",
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
}


def generate_report(
    evo_dir: str | Path,
    title: str = None,
    calibration_result: dict = None,
) -> str:
    """Generate a standalone HTML report from Phase 5 output.

    Args:
        evo_dir: Path to the .evo directory (or calibration run dir).
        title: Optional title override.
        calibration_result: Optional calibration_result.json dict for extra stats.

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

    return _render_html(advisory, evidence, title, calibration_result)


def _render_html(advisory, evidence, title, cal=None):
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

    cover = _build_cover_page(scope, period_from, period_to, advisory_id, generated)
    exec_summary = _build_executive_summary(summary, families_affected, cal)
    findings_html = _build_key_findings(changes, pattern_matches, candidate_patterns, families_affected)
    changes_html = _build_changes_section(changes)
    patterns_html = _build_pattern_section(pattern_matches, candidate_patterns)
    all_patterns = list(pattern_matches) + list(candidate_patterns)
    invest_html = _build_investigation_section(
        scope, period_from, period_to, changes, commits, files_affected, timeline,
        all_patterns,
    )
    evidence_html = _build_evidence_section(
        commits, files_affected, deps_changed, timeline, evidence,
    )

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
        f'{findings_html}\n'
        f'{changes_html}\n'
        f'{patterns_html}\n'
        f'{invest_html}\n'
        f'{evidence_html}\n'
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


def _build_executive_summary(summary, families_affected, cal=None):
    sig = summary.get("significant_changes", 0)
    n_fam = len(families_affected)
    patterns = summary.get("known_patterns_matched", 0)
    new_obs = summary.get("new_observations", summary.get("candidate_patterns_matched", 0))

    cards = [
        _summary_card(str(sig), "Significant Changes"),
        _summary_card(str(n_fam), "Areas Affected"),
        _summary_card(str(patterns), "Known Patterns"),
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

    return (
        '<section class="executive-summary">\n'
        '  <h2>Executive Summary</h2>\n'
        '  <div class="summary-cards">\n'
        '    ' + '\n    '.join(cards) + '\n'
        '  </div>\n'
        f'  {families_html}\n'
        '</section>'
    )


def _summary_card(value, label):
    return (
        f'<div class="summary-card">'
        f'<div class="summary-value">{value}</div>'
        f'<div class="summary-label">{label}</div>'
        f'</div>'
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
    if pattern_matches:
        n = len(pattern_matches)
        bullets.append(
            f'{n} known pattern{"s" if n != 1 else ""} matched, '
            'indicating previously observed cross-signal correlations.'
        )
    if candidate_patterns:
        n = len(candidate_patterns)
        bullets.append(
            f'{n} emerging pattern{"s" if n != 1 else ""} detected '
            'that may become recurring if observed again.'
        )

    items_html = "\n".join(f'    <li>{b}</li>' for b in bullets)
    return (
        '<section class="key-findings">\n'
        '  <h2>Key Findings</h2>\n'
        '  <ul class="findings-list">\n'
        f'{items_html}\n'
        '  </ul>\n'
        '</section>'
    )


def _build_changes_section(changes):
    if not changes:
        return (
            '<section class="changes-detected page-break-before">\n'
            '  <h2>What Changed in Your Codebase</h2>\n'
            '  <p class="empty">No unusual changes detected.</p>\n'
            '</section>'
        )

    n = len(changes)
    cards = "\n".join(_build_change_card(c) for c in changes)
    return (
        '<section class="changes-detected page-break-before">\n'
        '  <h2>What Changed in Your Codebase</h2>\n'
        '  <p style="color: var(--color-text-muted); margin-bottom: 1.5em;">\n'
        f'    We\'ve detected {n} change{"s" if n != 1 else ""} that differ from your project\'s\n'
        '    normal patterns. Each change shows what typically happens versus what we observed this time.\n'
        '  </p>\n'
        f'  {cards}\n'
        '</section>'
    )


def _build_change_card(c):
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

    return (
        f'<div class="change-card {dev_class}">\n'
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
        f'  <span class="pattern-group-count">{len(patterns)} related patterns</span>\n'
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

    # Sort patterns by severity (most critical first)
    sorted_matches = sorted(
        matches,
        key=lambda p: _severity_rank(pattern_risk_assessment(p)["severity"]),
        reverse=True,
    )
    sorted_candidates = sorted(
        candidates,
        key=lambda p: _severity_rank(pattern_risk_assessment(p)["severity"]),
        reverse=True,
    )

    known_cards = _grouped_cards(sorted_matches, "Known Pattern")
    emerging_cards = _grouped_cards(sorted_candidates, "Emerging Pattern")

    known_html = _collapsible_pattern_cards(known_cards, "Known Patterns", PATTERN_VISIBLE_LIMIT)
    emerging_html = _collapsible_pattern_cards(emerging_cards, "Emerging Patterns", PATTERN_VISIBLE_LIMIT)

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
        '  <h2>Recurring Patterns</h2>\n'
        f'  {banner_html}\n'
        f'  {guidance}\n'
        f'  {known_html}\n'
        f'  {emerging_html}\n'
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


def _build_evidence_section(commits, files, deps, timeline, evidence_raw):
    has_evidence = bool(commits or files or deps or timeline)
    if not has_evidence:
        return (
            '<section class="evidence-section page-break-before">\n'
            '  <h2>Evidence Package</h2>\n'
            '  <p class="empty">No evidence collected.</p>\n'
            '</section>'
        )

    counts = []
    if commits:
        counts.append(f'<div class="evidence-item">Commits <span class="count">{len(commits)}</span></div>')
    if files:
        counts.append(f'<div class="evidence-item">Files Changed <span class="count">{len(files)}</span></div>')
    if deps:
        counts.append(f'<div class="evidence-item">Dependencies <span class="count">{len(deps)}</span></div>')
    if timeline:
        counts.append(f'<div class="evidence-item">Timeline Events <span class="count">{len(timeline)}</span></div>')

    evidence_export = {
        "advisory_ref": evidence_raw.get("advisory_ref", ""),
        "commits": commits[:20],
        "files_affected": files[:50],
        "dependencies_changed": deps,
        "timeline": timeline[:50],
    }
    evidence_json = json.dumps(evidence_export).replace("</", "<\\/")

    details = []
    details.append(_build_commits_table(commits))
    details.append(_build_files_table(files))
    details.append(_build_deps_table(deps))
    details.append(_build_timeline(timeline))
    details_html = "\n".join(d for d in details if d)

    return (
        f'<script type="application/json" id="evidenceData">{evidence_json}</script>\n'
        '<section class="evidence-section page-break-before">\n'
        '  <h2>Evidence Package</h2>\n'
        '  <div class="evidence-summary">\n'
        '    <h4>What\'s Included</h4>\n'
        '    <p>We\'ve collected detailed evidence to support the analysis above.</p>\n'
        '    <div class="evidence-included-list">\n'
        '      ' + '\n      '.join(counts) + '\n'
        '    </div>\n'
        '    <div class="action-buttons no-print">\n'
        '      <button class="btn btn-secondary" onclick="saveEvidenceToFile()">Export Evidence (JSON)</button>\n'
        '      <button class="toggle-btn" onclick="toggleEvidence()" id="toggleEvidenceBtn">Show Details</button>\n'
        '    </div>\n'
        '  </div>\n'
        '  <div class="evidence-details" id="evidenceDetails">\n'
        f'    {details_html}\n'
        '  </div>\n'
        '</section>'
    )


def _build_commits_table(commits):
    if not commits:
        return ""
    LIMIT = 20
    visible_rows = []
    hidden_rows = []
    for i, c in enumerate(commits):
        sha = c.get("sha", "")[:8]
        msg = c.get("message", "").split("\n")[0][:80]
        author = c.get("author", {}).get("name", "")
        ts = _format_date(c.get("timestamp", ""))
        row = (
            f'<tr><td><code>{_esc(sha)}</code></td>'
            f'<td>{_esc(msg)}</td>'
            f'<td>{_esc(author)}</td>'
            f'<td>{ts}</td></tr>'
        )
        if i < LIMIT:
            visible_rows.append(row)
        else:
            hidden_rows.append(row)
    toggle = ""
    if hidden_rows:
        total = len(commits)
        toggle = (
            f'<button class="toggle-btn" onclick="toggleTableRows(\'commits-overflow\', this)">'
            f'Show all {total} items</button>'
        )
    return (
        '<h3>Commits Involved</h3>\n'
        '<table class="evidence-table">\n'
        '  <thead><tr><th>SHA</th><th>Message</th><th>Author</th><th>Date</th></tr></thead>\n'
        '  <tbody>' + ''.join(visible_rows)
        + '</tbody>\n'
        + (f'  <tbody class="evidence-overflow" id="commits-overflow">{"".join(hidden_rows)}</tbody>\n'
           if hidden_rows else '')
        + '</table>\n'
        + toggle
    )


def _build_files_table(files):
    if not files:
        return ""
    LIMIT = 30
    visible_rows = []
    hidden_rows = []
    for i, f in enumerate(files):
        path = f.get("path", "")
        change_type = f.get("change_type", "")
        first_seen = f.get("first_seen_in", "")[:8]
        row = (
            f'<tr><td><code>{_esc(path)}</code></td>'
            f'<td>{_esc(change_type.title())}</td>'
            f'<td><code>{_esc(first_seen)}</code></td></tr>'
        )
        if i < LIMIT:
            visible_rows.append(row)
        else:
            hidden_rows.append(row)
    toggle = ""
    if hidden_rows:
        total = len(files)
        toggle = (
            f'<button class="toggle-btn" onclick="toggleTableRows(\'files-overflow\', this)">'
            f'Show all {total} items</button>'
        )
    return (
        '<h3>Files Affected</h3>\n'
        '<table class="evidence-table">\n'
        '  <thead><tr><th>Path</th><th>Change Type</th><th>First Seen In</th></tr></thead>\n'
        '  <tbody>' + ''.join(visible_rows)
        + '</tbody>\n'
        + (f'  <tbody class="evidence-overflow" id="files-overflow">{"".join(hidden_rows)}</tbody>\n'
           if hidden_rows else '')
        + '</table>\n'
        + toggle
    )


def _build_deps_table(deps):
    if not deps:
        return ""
    rows = []
    for d in deps[:20]:
        name = d.get("name", "")
        ver_from = d.get("version_from", "")
        ver_to = d.get("version_to", "")
        rows.append(
            f'<tr><td><code>{_esc(name)}</code></td>'
            f'<td>{_esc(ver_from)}</td>'
            f'<td>{_esc(ver_to)}</td></tr>'
        )
    return (
        '<h3>Dependencies Changed</h3>\n'
        '<table class="evidence-table">\n'
        '  <thead><tr><th>Package</th><th>From</th><th>To</th></tr></thead>\n'
        '  <tbody>' + ''.join(rows) + '</tbody>\n'
        '</table>'
    )


def _build_timeline(timeline):
    if not timeline:
        return ""
    LIMIT = 30
    visible_items = []
    hidden_items = []
    for i, entry in enumerate(timeline):
        family = entry.get("family", "")
        text = entry.get("event_text", entry.get("event", ""))
        ts = _format_date(entry.get("timestamp", ""))
        label = FAMILY_LABELS.get(family, family)
        item = (
            '<div class="timeline-event">\n'
            f'  <div class="timeline-time">{ts}</div>\n'
            f'  <div class="timeline-content"><strong>{_esc(label)}:</strong> {_esc(text)}</div>\n'
            '</div>'
        )
        if i < LIMIT:
            visible_items.append(item)
        else:
            hidden_items.append(item)
    toggle = ""
    hidden_html = ""
    if hidden_items:
        total = len(timeline)
        hidden_html = (
            f'<div class="evidence-overflow" id="timeline-overflow">\n'
            '  ' + '\n  '.join(hidden_items) + '\n'
            '</div>'
        )
        toggle = (
            f'<button class="toggle-btn" onclick="toggleTableRows(\'timeline-overflow\', this)">'
            f'Show all {total} items</button>'
        )
    return (
        '<h3>Timeline of Events</h3>\n'
        '<div class="timeline">\n'
        '  ' + '\n  '.join(visible_items) + '\n'
        + hidden_html
        + '</div>\n'
        + toggle
    )


# ─── Prompt Builder ───


def _build_prompt(scope, period_from, period_to, changes, commits, files,
                  timeline, patterns=None, full=False):
    lines = [
        f"Here is a structural analysis of {scope} from {period_from} to {period_to}.",
        "",
        "CHANGES DETECTED:",
        "",
    ]

    for c in changes:
        family = FAMILY_LABELS.get(c.get("family", ""), c.get("family", ""))
        metric = METRIC_LABELS.get(c.get("metric", ""), c.get("metric", ""))
        current = c.get("current", 0)
        normal = c.get("normal", {})
        median = normal.get("median", normal.get("mean", 0))
        line = f"- {family}: {metric} changed from {_fmt_num(median)} to {_fmt_num(current)}"
        if full:
            dev = c.get("deviation_stddev", 0)
            d = "above" if dev >= 0 else "below"
            line += f" ({abs(dev):.1f}x {d} normal)"
        lines.append(line)

    if not full:
        lines.append("")
        lines.append('Click "Show Full Prompt" to see the complete investigation prompt with all commits and files...')
        return "\n".join(lines)

    # Pattern risk context (sorted by severity, most critical first, grouped by impact)
    if patterns:
        sorted_pats = sorted(
            patterns,
            key=lambda p: _severity_rank(pattern_risk_assessment(p)["severity"]),
            reverse=True,
        )
        lines.extend(["", "RISK ASSESSMENT FROM RECURRING PATTERNS:", ""])

        # Group patterns by (severity, impact) to avoid duplicate content
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
            if len(group) == 1:
                desc = friendly_pattern(group[0])
                lines.append(f"- [{sev_label}] {desc}")
            else:
                descs = [friendly_pattern(p) for p in group]
                lines.append(f"- [{sev_label}] {len(group)} related patterns:")
                for d in descs:
                    lines.append(f"    * {d}")
            lines.append(f"  Impact: {risk['impact']}")
            lines.append(f"  Recommendation: {risk['recommendation']}")
            lines.append("")

    lines.extend([
        "",
        "EVIDENCE SUMMARY:",
        f"- {len(commits)} commits involved",
        f"- {len(files)} files affected",
        f"- {len(timeline)} timeline events",
        "",
    ])

    if commits:
        lines.append("TOP COMMITS:")
        lines.append("")
        for c in commits[:10]:
            sha = c.get("sha", "")[:8]
            msg = c.get("message", "").split("\n")[0][:80]
            author = c.get("author", {}).get("name", "")
            n_files = len(c.get("files_changed", []))
            lines.append(f"{sha} \u2014 {msg}")
            lines.append(f"  Author: {author}")
            lines.append(f"  Files: {n_files}")
            lines.append("")

    if files:
        lines.append("TOP FILES CHANGED:")
        lines.append("")
        for f in files[:20]:
            path = f.get("path", "")
            ct = f.get("change_type", "")
            lines.append(f"- {path} ({ct})")
        lines.append("")

    lines.extend([
        "INVESTIGATION TASKS:",
        "",
        "1. ROOT CAUSE: Identify the most likely cause of each flagged change. Focus on",
        "   items marked [Action Required] or [Needs Attention] first.",
        "",
        "2. IMPACT ANALYSIS: For each issue, explain what could go wrong if left",
        "   unaddressed. Be specific about the affected components and users.",
        "",
        "3. PROPOSED FIXES: Provide concrete, actionable fixes for each issue:",
        "   - Specific code changes (file paths, function names, what to change)",
        "   - Configuration adjustments if applicable",
        "   - Process changes (e.g. PR size limits, review checklists)",
        "",
        "4. PRIORITY ORDER: Rank the fixes by urgency. What should be done immediately",
        "   vs. what can wait for the next sprint?",
        "",
        "5. VERIFICATION: After applying each fix, the team should re-run the analysis",
        "   (using `evo analyze`) to confirm that:",
        "   - The deviation levels have decreased",
        "   - The severity ratings have improved (e.g. from 'Needs Attention' to 'Informational')",
        "   - No new issues were introduced by the fix",
        "",
        "Please provide specific, actionable recommendations with file paths and code",
        "examples where possible. The goal is to bring these metrics back within normal",
        "ranges while maintaining development velocity.",
    ])

    return "\n".join(lines)


# ─── Helpers ───


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
.evidence-section { margin-top: 2em; }
.evidence-summary { background: var(--color-bg-subtle); padding: 1.5em; border-radius: 8px;
  border-left: 4px solid var(--color-info); margin-bottom: 1.5em; }
.evidence-summary h4 { color: var(--color-primary); margin-bottom: 0.5em; }
.evidence-included-list { display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1em; margin: 1em 0; }
.evidence-item { display: flex; align-items: center; gap: 0.5em; font-size: 10pt; }
.evidence-item .count { font-weight: 700; color: var(--color-secondary); }
.evidence-details { display: none; margin-top: 1em; }
.evidence-details.show { display: block; }
.evidence-table { width: 100%; border-collapse: collapse; margin: 1em 0; font-size: 10pt; }
.evidence-table thead { background: var(--color-bg-subtle);
  border-bottom: 2px solid var(--color-border); }
.evidence-table th { text-align: left; padding: 0.75em 1em; font-weight: 600;
  color: var(--color-primary); }
.evidence-table td { padding: 0.75em 1em; border-bottom: 1px solid var(--color-border);
  vertical-align: top; }
.evidence-table tr:last-child td { border-bottom: none; }
.evidence-table code { background: var(--color-bg-subtle); padding: 0.2em 0.4em;
  border-radius: 3px; font-size: 9pt; }
.timeline { margin: 1em 0; }
.timeline-event { display: flex; gap: 1em; padding: 0.75em 0;
  border-left: 2px solid var(--color-border); padding-left: 1em; margin-left: 1em;
  position: relative; }
.timeline-event:before { content: ''; position: absolute; left: -6px; top: 1em;
  width: 10px; height: 10px; background: var(--color-secondary); border-radius: 50%; }
.timeline-time { min-width: 120px; font-size: 10pt; color: var(--color-text-muted); }
.timeline-content { flex: 1; font-size: 10pt; }
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
.page-break-before { page-break-before: always; }
.page-break-after { page-break-after: always; }
footer { margin-top: 4em; padding-top: 2em; border-top: 1px solid var(--color-border);
  text-align: center; color: var(--color-text-muted); font-size: 9pt; }
footer strong { color: var(--color-secondary); }
@media print {
  body { font-size: 10pt; padding: 0; }
  .btn, .toggle-btn, .action-buttons { display: none !important; }
  .prompt-full { display: block !important; }
  .evidence-details { display: block !important; }
  .evidence-overflow { display: table-row-group !important; }
  div.evidence-overflow { display: block !important; }
  details.pattern-overflow > summary { display: none !important; }
  details.pattern-overflow > summary ~ * { display: block !important; }
  details[open] summary ~ * { display: block; }
  .no-print { display: none; }
  .cover-page { min-height: auto; padding: 4em 0; }
}"""

# ─── JS ───

_JS = """<script>
function copyPrompt() {
  var el = document.getElementById('fullPrompt');
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(function() {
    var btn = document.getElementById('copyBtn');
    var orig = btn.textContent;
    btn.textContent = 'Copied!';
    btn.style.background = 'var(--color-success)';
    setTimeout(function() { btn.textContent = orig; btn.style.background = ''; }, 2000);
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
function saveEvidenceToFile() {
  var el = document.getElementById('evidenceData');
  if (!el) return;
  var data = JSON.parse(el.textContent);
  var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url; a.download = 'evidence_package.json';
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}
function toggleEvidence() {
  var d = document.getElementById('evidenceDetails');
  var b = document.getElementById('toggleEvidenceBtn');
  if (!d || !b) return;
  d.classList.toggle('show'); b.classList.toggle('active');
  b.textContent = d.classList.contains('show') ? 'Hide Details' : 'Show Details';
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
document.addEventListener('DOMContentLoaded', function() {
  var btns = document.querySelectorAll('button[onclick^="toggleTableRows"]');
  for (var i = 0; i < btns.length; i++) {
    btns[i].setAttribute('data-label', btns[i].textContent);
  }
});
</script>"""
