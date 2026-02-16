"""
PM-friendly formatting helpers for Evolution Engine.

Translates engineering metrics (MAD deviations, correlations, dispersion values)
into plain English with risk framing that product managers can understand.

Used by Phase 3 (explanations), Phase 5 (advisory), and the HTML report generator.
"""

# ─── Risk Levels ───

_RISK_TIERS = [
    # (min_abs_deviation, label, description, color)
    (6.0, "Critical", "Extremely unusual", "#991b1b"),
    (4.0, "High", "Significantly unusual", "#ef4444"),
    (2.0, "Medium", "Notably different", "#f59e0b"),
    (1.0, "Low", "Slightly unusual", "#22c55e"),
]

_RISK_NONE = {"label": "Normal", "description": "Within normal range", "color": "#6b7280"}


def risk_level(deviation: float) -> dict:
    """Map absolute deviation magnitude to a risk tier.

    Returns dict with label, description, color.
    """
    abs_dev = abs(deviation)
    for min_dev, label, description, color in _RISK_TIERS:
        if abs_dev >= min_dev:
            return {"label": label, "description": description, "color": color}
    if abs_dev >= 1.0:
        return {"label": "Low", "description": "Slightly unusual", "color": "#22c55e"}
    return dict(_RISK_NONE)


# ─── Relative Change ───

def relative_change(observed, baseline_median) -> str:
    """Natural-language comparison of observed vs baseline.

    Examples:
        relative_change(12, 4) → "about 3x more than usual (typically around 4)"
        relative_change(2, 10) → "about 5x less than usual (typically around 10)"
        relative_change(5, 4)  → "slightly more than usual (typically around 4)"
    """
    if baseline_median is None or baseline_median == 0:
        if observed == 0:
            return "at the usual level"
        return f"{_fmt(observed)} (no established baseline yet)"

    ratio = observed / baseline_median
    typical = f"typically around {_fmt(baseline_median)}"

    if 0.85 <= ratio <= 1.2:
        return f"about the same as usual ({typical})"
    elif ratio > 1.2:
        if ratio >= 100:
            return f"significantly above baseline ({typical})"
        elif ratio >= 2:
            return f"about {_fmt_ratio(ratio)}x more than usual ({typical})"
        else:
            return f"slightly more than usual ({typical})"
    else:
        if observed == 0:
            return f"dropped to zero ({typical})"
        inverse = baseline_median / observed
        if inverse >= 100:
            return f"significantly below baseline ({typical})"
        elif inverse >= 2:
            return f"about {_fmt_ratio(inverse)}x less than usual ({typical})"
        else:
            return f"slightly less than usual ({typical})"


def _fmt(value) -> str:
    """Format a number for display in natural language."""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value) and abs(value) < 10000:
            return str(int(value))
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 1:
            return f"{value:.1f}"
        return f"{value:.2f}"
    return str(value)


def _fmt_ratio(ratio: float) -> str:
    """Format a ratio like 3x or 2.5x."""
    if ratio == int(ratio):
        return str(int(ratio))
    return f"{ratio:.1f}"


# ─── Metric Insights ───

_METRIC_INSIGHTS = {
    # Git metrics
    ("files_touched", "up"): "More files changed than usual in this commit.",
    ("files_touched", "down"): "Fewer files changed than usual in this commit.",
    ("dispersion", "up"): "Changes spread across unrelated areas of the codebase.",
    ("dispersion", "down"): "Changes concentrated in related areas of the codebase.",
    ("change_locality", "up"): "The changed files frequently change together, suggesting a focused modification.",
    ("change_locality", "down"): "The changed files don't usually change together, suggesting a cross-cutting modification.",
    ("cochange_novelty_ratio", "up"): "Many file pairings in this change haven't been seen together before.",
    ("cochange_novelty_ratio", "down"): "This change follows well-established patterns of file co-changes.",

    # CI metrics
    ("run_duration", "up"): "Build took longer than usual.",
    ("run_duration", "down"): "Build completed faster than usual.",
    ("run_failed", "up"): "Build failed.",
    ("run_failed", "down"): "Build is passing again.",

    # Testing metrics
    ("total_tests", "up"): "More tests are running than usual.",
    ("total_tests", "down"): "Fewer tests are running than usual.",
    ("suite_duration", "up"): "The test suite is running slower than usual.",
    ("suite_duration", "down"): "The test suite is completing faster than usual.",
    ("skip_rate", "up"): "More tests are being skipped than usual.",
    ("skip_rate", "down"): "Fewer tests are being skipped than usual.",

    # Dependency metrics
    ("dependency_count", "up"): "Dependency count increased.",
    ("dependency_count", "down"): "Dependency count decreased.",
    ("max_depth", "up"): "Dependency tree is deeper than usual.",
    ("max_depth", "down"): "Dependency tree is shallower than usual.",

    # Schema metrics
    ("endpoint_count", "up"): "More API endpoints than before.",
    ("endpoint_count", "down"): "Fewer API endpoints than before.",
    ("type_count", "up"): "More types in the API schema.",
    ("type_count", "down"): "Fewer types in the API schema.",
    ("field_count", "up"): "More fields in the API schema.",
    ("field_count", "down"): "Fewer fields in the API schema.",
    ("schema_churn", "up"): "API schema changed more than usual.",
    ("schema_churn", "down"): "API schema is stable.",

    # Deployment metrics
    ("release_cadence_hours", "up"): "Longer time between releases than usual.",
    ("release_cadence_hours", "down"): "Shorter time between releases than usual.",
    ("is_prerelease", "up"): "This is a pre-release.",
    ("is_prerelease", "down"): "This is a stable release.",
    ("asset_count", "up"): "More release assets than usual.",
    ("asset_count", "down"): "Fewer release assets than usual.",

    # Config metrics
    ("resource_count", "up"): "More managed resources than before.",
    ("resource_count", "down"): "Fewer managed resources than before.",
    ("resource_type_count", "up"): "More resource types than before.",
    ("resource_type_count", "down"): "Fewer resource types than before.",
    ("config_churn", "up"): "Configuration changed more than usual.",
    ("config_churn", "down"): "Configuration is stable.",

    # Security metrics
    ("vulnerability_count", "up"): "More vulnerabilities detected.",
    ("vulnerability_count", "down"): "Fewer vulnerabilities detected.",
    ("critical_count", "up"): "Critical vulnerabilities detected.",
    ("critical_count", "down"): "Fewer critical vulnerabilities detected.",
    ("fixable_ratio", "up"): "A higher proportion of vulnerabilities have available fixes.",
    ("fixable_ratio", "down"): "Fewer vulnerabilities have available fixes.",
}


def metric_insight(metric: str, direction: str) -> str:
    """One-sentence 'what this means' for a metric+direction.

    Args:
        metric: The metric name (e.g. "files_touched").
        direction: "up" or "down" (based on deviation sign).

    Returns:
        Human-readable insight string, or empty string if unknown.
    """
    return _METRIC_INSIGHTS.get((metric, direction), "")


# ─── Friendly Patterns ───

_FRIENDLY_FAMILY = {
    "git": "code changes", "version_control": "code changes",
    "ci": "CI builds", "testing": "test runs",
    "dependency": "dependency changes", "schema": "API changes",
    "deployment": "deployments", "config": "config changes",
    "security": "security scans",
}

_FRIENDLY_METRIC = {
    "files_touched": "file count",
    "dispersion": "code spread",
    "change_locality": "change focus",
    "cochange_novelty_ratio": "novelty of file pairings",
    "run_duration": "build time",
    "run_failed": "build failure rate",
    "dependency_count": "dependency count",
    "max_depth": "dependency depth",
    "release_cadence_hours": "release frequency",
    "is_prerelease": "pre-release rate",
    "asset_count": "release artifact count",
}


def friendly_pattern(pattern: dict) -> str:
    """Generate a PM-friendly pattern description from structured fields.

    Produces clean, non-technical descriptions that don't reveal
    internal methodology (effect sizes, treated/control groups, etc.).
    """
    families = pattern.get("families") or pattern.get("sources") or []
    metrics = pattern.get("metrics") or []
    corr = pattern.get("correlation") or pattern.get("correlation_strength") or 0
    seen_count = pattern.get("repo_count", 0)

    prefix = ""
    if seen_count > 1:
        prefix = f"Observed across {seen_count} projects: "
    elif seen_count == 1:
        prefix = "Observed in 1 project: "

    # Build from structured fields
    if families and metrics:
        family_names = [_FRIENDLY_FAMILY.get(f, f) for f in families]
        metric_names = [_FRIENDLY_METRIC.get(m, m.replace("_", " ")) for m in metrics
                        if not m.endswith("_presence")]

        if not metric_names:
            metric_names = [_FRIENDLY_METRIC.get(m, m.replace("_", " ")) for m in metrics]

        direction = "increase" if corr >= 0 else "decrease"
        metric_verb = "tend" if len(metric_names) > 1 else "tends"

        if len(families) == 1:
            trigger = family_names[0]
            outcome = " and ".join(metric_names)
            verb = "occur" if trigger.endswith("s") else "occurs"
            return (
                f"{prefix}when {trigger} {verb}, "
                f"{outcome} {metric_verb} to {direction}."
            )
        else:
            area_str = " and ".join(family_names)
            metric_str = " and ".join(metric_names)
            movement = "move together" if corr >= 0 else "move in opposite directions"
            return (
                f"{prefix}when {area_str} happen together, "
                f"{metric_str} {metric_verb} to {movement}."
            )

    # Absolute fallback: if no structured fields, strip stats from raw desc
    desc = pattern.get("description") or ""
    if desc:
        desc = _sanitize_description(desc)
        return f"{prefix}{desc}" if prefix else desc

    return ""


def _sanitize_description(desc: str) -> str:
    """Strip internal statistical details from a raw pattern description."""
    import re
    # Remove "(effect size d=..., treated=..., control=...)"
    desc = re.sub(r'\s*\(effect size[^)]*\)', '', desc)
    # Remove "(of N shared 24h windows)" or "(of N shared commits)"
    desc = re.sub(r'\s*\(of \d+ shared[^)]*\)', '', desc)
    # Remove "lift=..." fragments
    desc = re.sub(r',?\s*lift=[\d.]+', '', desc)
    # Replace "co-occur with correlation X.XX across N ..." with cleaner text
    desc = re.sub(
        r'co-occur with correlation -?[\d.]+ across \d+ [\w-]+ observations',
        'tend to change together',
        desc,
    )
    # Replace "co-deviate X.Xx more than expected by chance across N ..."
    desc = re.sub(
        r'co-deviate [\d.]+x more than expected by chance across \d+ [\w-]+ observations',
        'tend to deviate together more than expected',
        desc,
    )
    # Replace internal metric names (family.metric) with friendly names
    desc = re.sub(
        r'(?:git|ci|dependency|deployment|testing|schema|config|security)\.'
        r'(\w+)',
        lambda m: _FRIENDLY_METRIC.get(m.group(1), m.group(1).replace("_", " ")),
        desc,
    )
    # Clean up "Signals X and Y" → "X and Y"
    desc = re.sub(r'^Signals\s+', '', desc)
    return desc.strip().rstrip('.')


# ─── Pattern Risk Assessment ───

# Maps (metric, correlation_direction) to (severity, impact, recommendation)
# severity: "positive", "info", "watch", "concern", "critical"
_PATTERN_RISK = {
    # Dispersion patterns
    ("dispersion", "up"): (
        "watch",
        "Changes are spreading across unrelated parts of the codebase. This makes reviews harder and increases the chance of unexpected side effects.",
        "Review recent PRs for scope creep. Consider breaking large changes into focused commits.",
    ),
    ("dispersion", "down"): (
        "positive",
        "Changes are staying focused in related areas. This is a healthy development pattern that makes code review more effective.",
        "No action needed. This is a positive trend.",
    ),
    # Files touched
    ("files_touched", "up"): (
        "watch",
        "Commits are touching more files than usual, increasing review burden and risk of regressions.",
        "Monitor PR sizes. If this persists, investigate whether large refactors need better decomposition.",
    ),
    ("files_touched", "down"): (
        "positive",
        "Changes are smaller than usual. Smaller changes are easier to review and less risky.",
        "No action needed.",
    ),
    # Co-change novelty
    ("cochange_novelty_ratio", "up"): (
        "concern",
        "Files that don't normally change together are being modified in the same commits. This indicates novel, untested interactions that may introduce bugs.",
        "Investigate which files are being combined unexpectedly. Prioritize testing these changes.",
    ),
    ("cochange_novelty_ratio", "down"): (
        "positive",
        "Changes follow well-established file co-change patterns. The code paths being modified have been tested together before.",
        "No action needed. This indicates stable, predictable development.",
    ),
    # Change locality
    ("change_locality", "up"): (
        "info",
        "Changed files frequently change together, suggesting focused modifications to tightly-coupled components.",
        "No immediate action. Monitor if tight coupling becomes a maintenance concern.",
    ),
    ("change_locality", "down"): (
        "watch",
        "Changes span files that don't normally change together, suggesting cross-cutting concerns that may be harder to test.",
        "Review whether these cross-cutting changes have adequate test coverage.",
    ),
    # Build duration
    ("run_duration", "up"): (
        "watch",
        "Builds are taking longer. Slower CI feedback loops reduce developer productivity and delay catching issues.",
        "Profile the build pipeline to identify bottlenecks. Check for newly added expensive tests or build steps.",
    ),
    ("run_duration", "down"): (
        "info",
        "Builds are running faster than usual. Verify this isn't due to skipped tests or simplified steps.",
        "Confirm test coverage hasn't decreased alongside faster builds.",
    ),
    # Build failures
    ("run_failed", "up"): (
        "critical",
        "Build failures are increasing. Broken builds block the team and indicate instability.",
        "Investigate immediately. Check recent changes for breaking commits and flaky tests.",
    ),
    ("run_failed", "down"): (
        "positive",
        "Build stability is improving. Fewer failures means better developer experience.",
        "No action needed. This is a positive trend.",
    ),
    # Dependencies
    ("dependency_count", "up"): (
        "watch",
        "The dependency count is growing, expanding the supply-chain attack surface and potential for version conflicts.",
        "Audit new dependencies for necessity, maintenance status, and known vulnerabilities.",
    ),
    ("dependency_count", "down"): (
        "positive",
        "Dependencies are being reduced, shrinking the attack surface and simplifying maintenance.",
        "No action needed. Verify removed dependencies weren't still needed.",
    ),
    # Release cadence
    ("release_cadence_hours", "up"): (
        "watch",
        "Time between releases is increasing. This could indicate a bottleneck in the release process or accumulating risk in larger releases.",
        "Check if process changes or staffing issues are delaying releases.",
    ),
    ("release_cadence_hours", "down"): (
        "info",
        "Releases are happening more frequently. Faster releases reduce batch size risk but may skip review steps.",
        "Verify that quality gates (testing, review) are still being applied to faster releases.",
    ),
}

# Severity display properties
_SEVERITY_DISPLAY = {
    "critical": {"label": "Action Required", "color": "#dc2626", "icon": "\u26a0\ufe0f"},
    "concern": {"label": "Needs Attention", "color": "#ea580c", "icon": "\U0001f50d"},
    "watch": {"label": "Worth Monitoring", "color": "#d97706", "icon": "\U0001f441\ufe0f"},
    "info": {"label": "Informational", "color": "#0284c7", "icon": "\u2139\ufe0f"},
    "positive": {"label": "Healthy Pattern", "color": "#16a34a", "icon": "\u2705"},
}


def pattern_risk_assessment(pattern: dict) -> dict:
    """Assess a pattern's risk, impact, and recommendation.

    Args:
        pattern: Dict with sources, metrics, correlation/correlation_strength,
                 description, etc.

    Returns:
        Dict with severity, severity_display, impact, recommendation.
        severity is one of: critical, concern, watch, info, positive.
    """
    metrics = pattern.get("metrics") or []
    corr = pattern.get("correlation") or pattern.get("correlation_strength") or 0

    # Try each metric in the pattern to find a risk mapping
    best = None
    for m in metrics:
        # Skip presence metrics (they indicate triggers, not outcomes)
        if m.endswith("_presence"):
            continue
        direction = "up" if corr >= 0 else "down"
        key = (m, direction)
        if key in _PATTERN_RISK:
            candidate = _PATTERN_RISK[key]
            # Pick the highest severity
            if best is None or _severity_rank(candidate[0]) > _severity_rank(best[0]):
                best = candidate

    if best is None:
        # Fallback: assess by correlation strength
        abs_corr = abs(corr)
        if abs_corr >= 0.7:
            severity = "watch"
            impact = "A strong statistical correlation exists between these signals. Changes in one area predictably affect the other."
            recommendation = "Monitor this relationship. If one signal degrades, check the correlated area."
        elif abs_corr >= 0.3:
            severity = "info"
            impact = "A moderate correlation exists between these signals, suggesting they tend to move together."
            recommendation = "Be aware of this relationship when making changes in either area."
        else:
            severity = "info"
            impact = "A weak but recurring correlation exists between these signals."
            recommendation = "No action needed. This is a background trend to be aware of."

        return {
            "severity": severity,
            "severity_display": _SEVERITY_DISPLAY[severity],
            "impact": impact,
            "recommendation": recommendation,
        }

    severity, impact, recommendation = best
    return {
        "severity": severity,
        "severity_display": _SEVERITY_DISPLAY[severity],
        "impact": impact,
        "recommendation": recommendation,
    }


def _severity_rank(severity: str) -> int:
    """Numeric rank for comparing severity levels."""
    return {"positive": 0, "info": 1, "watch": 2, "concern": 3, "critical": 4}.get(severity, 1)


# ─── Advisory Status Rollup ───

_ADVISORY_STATUS = {
    "action_required": {"level": "action_required", "icon": "\u26a0\ufe0f", "label": "Action Required"},
    "needs_attention": {"level": "needs_attention", "icon": "\U0001f50d", "label": "Needs Attention"},
    "worth_monitoring": {"level": "worth_monitoring", "icon": "\U0001f441\ufe0f", "label": "Worth Monitoring"},
    "all_clear": {"level": "all_clear", "icon": "\u2705", "label": "All Clear"},
}

# Numeric rank for threshold comparison: higher = more severe
_STATUS_RANK = {
    "all_clear": 0,
    "worth_monitoring": 1,
    "needs_attention": 2,
    "action_required": 3,
}


def advisory_status(advisory: dict) -> dict:
    """Compute overall advisory status from findings.

    Maps the highest individual deviation to one of four levels:
      - action_required: any Critical or High finding (deviation >= 4.0)
      - needs_attention: any Medium finding (deviation >= 2.0)
      - worth_monitoring: any Low finding (deviation >= 1.0)
      - all_clear: no significant deviations

    Returns dict with level, icon, label.
    """
    changes = advisory.get("changes", [])
    if not changes:
        return dict(_ADVISORY_STATUS["all_clear"])

    deviations = [abs(c.get("deviation_stddev", 0)) for c in changes]
    max_deviation = max(deviations) if deviations else 0

    if max_deviation >= 4.0:
        return dict(_ADVISORY_STATUS["action_required"])
    elif max_deviation >= 2.0:
        return dict(_ADVISORY_STATUS["needs_attention"])
    elif max_deviation >= 1.0:
        return dict(_ADVISORY_STATUS["worth_monitoring"])
    else:
        return dict(_ADVISORY_STATUS["all_clear"])


def status_meets_threshold(status_level: str, min_severity: str) -> bool:
    """Check if an advisory status level meets a notification threshold.

    Args:
        status_level: The advisory status (e.g. "action_required").
        min_severity: The configured threshold (e.g. "concern").

    Threshold mapping:
      - "critical" → only action_required
      - "concern"  → action_required + needs_attention (default)
      - "watch"    → action_required + needs_attention + worth_monitoring
      - "info"     → everything

    Returns True if the status is severe enough to trigger notification.
    """
    threshold_map = {
        "critical": "action_required",
        "concern": "needs_attention",
        "watch": "worth_monitoring",
        "info": "all_clear",
    }
    min_level = threshold_map.get(min_severity, "needs_attention")
    return _STATUS_RANK.get(status_level, 0) >= _STATUS_RANK.get(min_level, 0)
