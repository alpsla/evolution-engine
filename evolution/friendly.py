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
        if ratio >= 2:
            return f"about {_fmt_ratio(ratio)}x more than usual ({typical})"
        else:
            return f"slightly more than usual ({typical})"
    else:
        if observed == 0:
            return f"dropped to zero ({typical})"
        inverse = baseline_median / observed
        if inverse >= 2:
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
    ("files_touched", "up"): "Larger changes tend to need more review time and carry more risk of unintended side effects.",
    ("files_touched", "down"): "Smaller changes are generally lower risk and easier to review.",
    ("dispersion", "up"): "Changes spread across unrelated areas are harder to review and more likely to cause unexpected interactions.",
    ("dispersion", "down"): "Changes are concentrated in related areas, which is usually easier to reason about.",
    ("change_locality", "up"): "The changed files frequently change together, suggesting a focused modification.",
    ("change_locality", "down"): "The changed files don't usually change together, which may signal a cross-cutting concern.",
    ("cochange_novelty_ratio", "up"): "Many file pairings in this change haven't been seen together before, suggesting a novel modification.",
    ("cochange_novelty_ratio", "down"): "This change follows well-established patterns of file co-changes.",

    # CI metrics
    ("run_duration", "up"): "Longer builds may indicate added complexity or resource-heavy tests.",
    ("run_duration", "down"): "Faster builds could indicate removed tests or simplified build steps.",
    ("run_failed", "up"): "A build failure needs attention before merging.",
    ("run_failed", "down"): "Build is passing again.",

    # Testing metrics
    ("total_tests", "up"): "More tests are running, which could indicate expanded coverage.",
    ("total_tests", "down"): "Fewer tests are running, which could indicate removed or skipped tests.",
    ("suite_duration", "up"): "The test suite is running slower than usual.",
    ("suite_duration", "down"): "The test suite is completing faster than usual.",
    ("skip_rate", "up"): "More tests are being skipped, which may mask failures.",
    ("skip_rate", "down"): "Fewer tests are being skipped than usual.",

    # Dependency metrics
    ("dependency_count", "up"): "More dependencies increase the surface area for supply-chain issues.",
    ("dependency_count", "down"): "Fewer dependencies reduces the supply-chain attack surface.",
    ("max_depth", "up"): "Deeper dependency trees make it harder to track transitive vulnerabilities.",
    ("max_depth", "down"): "A shallower dependency tree is easier to audit and maintain.",

    # Schema metrics
    ("endpoint_count", "up"): "More API endpoints expand the public interface that needs to be maintained.",
    ("endpoint_count", "down"): "Removing endpoints may break existing consumers.",
    ("type_count", "up"): "More types in the API schema add complexity for consumers.",
    ("type_count", "down"): "Fewer types may simplify the API but could break existing integrations.",
    ("field_count", "up"): "More fields expand the API surface area.",
    ("field_count", "down"): "Fewer fields may break consumers that depend on removed fields.",
    ("schema_churn", "up"): "High schema churn can destabilize API consumers.",
    ("schema_churn", "down"): "Low schema churn indicates a stable API.",

    # Deployment metrics
    ("release_cadence_hours", "up"): "Longer time between releases — this may indicate a process bottleneck.",
    ("release_cadence_hours", "down"): "Faster-than-usual releases may skip normal review processes.",
    ("is_prerelease", "up"): "This is a pre-release, which typically gets less production testing.",
    ("is_prerelease", "down"): "This is a stable release.",
    ("asset_count", "up"): "More release assets than usual.",
    ("asset_count", "down"): "Fewer release assets than usual — some expected artifacts may be missing.",

    # Config metrics
    ("resource_count", "up"): "More managed resources increase infrastructure complexity.",
    ("resource_count", "down"): "Fewer resources may indicate decommissioning.",
    ("resource_type_count", "up"): "More resource types increase operational complexity.",
    ("resource_type_count", "down"): "Fewer resource types simplifies operations.",
    ("config_churn", "up"): "High configuration churn increases the risk of misconfigurations.",
    ("config_churn", "down"): "Low configuration churn indicates stable infrastructure.",

    # Security metrics
    ("vulnerability_count", "up"): "More vulnerabilities detected — review and prioritize fixes.",
    ("vulnerability_count", "down"): "Fewer vulnerabilities is a positive trend.",
    ("critical_count", "up"): "Critical vulnerabilities require immediate attention.",
    ("critical_count", "down"): "Fewer critical vulnerabilities is a positive trend.",
    ("fixable_ratio", "up"): "A higher proportion of vulnerabilities have available fixes.",
    ("fixable_ratio", "down"): "Fewer vulnerabilities have available fixes — manual remediation may be needed.",
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

def friendly_pattern(pattern: dict) -> str:
    """Rewrite a pattern description into PM-friendly language.

    Input pattern dict should have: description, support_count or occurrence_count,
    families, metrics, correlation.
    """
    desc = pattern.get("description") or ""
    seen_count = pattern.get("support_count") or pattern.get("seen_count") or pattern.get("occurrence_count") or 0

    if desc:
        prefix = f"Seen in {seen_count} project{'s' if seen_count != 1 else ''}: " if seen_count > 0 else ""
        return f"{prefix}{desc}"

    # Fallback: build from families and metrics
    families = pattern.get("families") or pattern.get("sources") or []
    metrics = pattern.get("metrics") or []
    if families and metrics:
        family_str = " and ".join(families)
        metric_str = ", ".join(metrics)
        prefix = f"Seen in {seen_count} project{'s' if seen_count != 1 else ''}: " if seen_count > 0 else ""
        return f"{prefix}changes involving {family_str} tend to show unusual {metric_str}."

    return desc
