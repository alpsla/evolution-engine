"""
PR Comment Formatter — Generate GitHub PR comments from EE advisory.

Produces markdown suitable for posting as a PR comment via `gh pr comment`
or the GitHub API. Supports both initial analysis and verification diffs.

Usage:
    from evolution.pr_comment import format_pr_comment, format_verification_comment
    comment = format_pr_comment(advisory, investigation=None)
    update = format_verification_comment(verification, previous_comment_id=None)
"""

import json
from pathlib import Path
from typing import Optional

from evolution.friendly import metric_insight, risk_level


# ─── Risk Badge Emojis ───

_RISK_BADGES = {
    "Critical": "\U0001f534",  # red circle
    "High": "\U0001f7e0",      # orange circle
    "Medium": "\U0001f7e1",    # yellow circle
    "Low": "\U0001f7e2",       # green circle
    "Normal": "\u26aa",        # white circle
}


def format_pr_comment(
    advisory: dict,
    investigation: Optional[dict] = None,
    repo_name: str = None,
) -> str:
    """Format a Phase 5 advisory as a GitHub PR comment.

    Args:
        advisory: Phase 5 advisory dict (from advisory.json).
        investigation: Optional investigation report dict.
        repo_name: Repository name for the header.

    Returns:
        Markdown string suitable for `gh pr comment`.
    """
    scope = advisory.get("scope", repo_name or "repository")
    summary = advisory.get("summary", {})
    changes = advisory.get("changes", [])
    patterns = advisory.get("pattern_matches", [])
    candidates = advisory.get("candidate_patterns", [])

    significant = summary.get("significant_changes", len(changes))

    if significant == 0:
        return (
            "## Evolution Engine Analysis\n\n"
            "\u2705 **All clear** — no significant deviations detected.\n\n"
            "<sub>Powered by [Evolution Engine](https://github.com/evolution-engine/evolution-engine)</sub>"
        )

    # Header with summary
    risk_counts = _count_risks(changes)
    risk_summary = ", ".join(
        f"{count} {label}" for label, count in risk_counts.items() if count > 0
    )

    lines = [
        "## Evolution Engine Analysis",
        "",
        f"**{significant} unusual change(s) detected** [{risk_summary}]",
        "",
    ]

    # Changes table
    lines.append("| Risk | Family | Metric | Now | Usual | Change |")
    lines.append("|:----:|--------|--------|----:|------:|--------|")

    for c in sorted(changes, key=lambda x: abs(x.get("deviation_stddev", 0)), reverse=True):
        risk = risk_level(c.get("deviation_stddev", 0))
        badge = _RISK_BADGES.get(risk["label"], "\u26aa")
        family = c.get("family", "?")
        metric = c.get("metric", "?")
        current = _fmt(c.get("current", 0))
        normal = _fmt(c.get("normal", {}).get("median", c.get("normal", {}).get("mean", 0)))
        desc = c.get("description", "")
        # Truncate description for table
        if len(desc) > 60:
            desc = desc[:57] + "..."
        lines.append(
            f"| {badge} {risk['label']} | {family} | {metric} | {current} | {normal} | {desc} |"
        )

    lines.append("")

    # Pattern matches
    if patterns or candidates:
        lines.append("<details>")
        lines.append(f"<summary><strong>Patterns ({len(patterns)} known, {len(candidates)} candidate)</strong></summary>")
        lines.append("")

        if patterns:
            for p in patterns[:5]:
                desc = p.get("description", "")[:200]
                sources = ", ".join(p.get("sources", []))
                lines.append(f"- **[{sources}]** {desc}")

        if candidates:
            lines.append("")
            for p in candidates[:5]:
                desc = p.get("description", "")[:200]
                families = ", ".join(p.get("families", []))
                lines.append(f"- *[{families}]* {desc}")

        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Investigation summary (if available)
    if investigation and investigation.get("success"):
        lines.append("<details>")
        lines.append("<summary><strong>AI Investigation</strong></summary>")
        lines.append("")
        # Truncate investigation text for PR comment
        inv_text = investigation.get("report", "")
        if len(inv_text) > 3000:
            inv_text = inv_text[:3000] + "\n\n*... truncated. See full report in `.evo/investigation/`*"
        lines.append(inv_text)
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Footer
    families = summary.get("families_affected", [])
    lines.append(
        f"<sub>Families: {', '.join(families)} | "
        f"Powered by [Evolution Engine](https://github.com/evolution-engine/evolution-engine)</sub>"
    )

    return "\n".join(lines)


def format_verification_comment(
    verification: dict,
    previous_changes: int = 0,
) -> str:
    """Format a verification result as a PR comment update.

    Args:
        verification: Verification dict from Phase 5 verify().
        previous_changes: Number of changes in the original advisory.

    Returns:
        Markdown string for updating the PR comment.
    """
    v = verification.get("verification", verification)
    summary = v.get("summary", {})

    resolved = summary.get("resolved", 0)
    persisting = summary.get("persisting", 0)
    new_issues = summary.get("new", 0)
    regressions = summary.get("regressions", 0)
    total_before = summary.get("total_before", previous_changes)
    rate = summary.get("resolution_rate", 0)

    # Header
    if persisting == 0 and new_issues == 0 and regressions == 0:
        status = "\u2705 **All clear** — all issues resolved!"
    elif regressions > 0:
        status = f"\u26a0\ufe0f **{resolved} of {total_before} resolved, {regressions} regression(s)**"
    elif resolved > 0:
        status = f"\U0001f504 **{resolved} of {total_before} resolved** ({rate:.0%})"
    else:
        status = f"\u26a0\ufe0f **No changes resolved yet**"

    lines = [
        "## Evolution Engine — Verification Update",
        "",
        status,
        "",
    ]

    # Resolved items
    resolved_items = v.get("resolved", [])
    if resolved_items:
        lines.append("**Resolved:**")
        for item in resolved_items:
            lines.append(f"- \u2705 {item.get('family', '?')} / {item.get('metric', '?')} — back to normal")
        lines.append("")

    # Persisting items
    persisting_items = v.get("persisting", [])
    if persisting_items:
        lines.append("**Still flagged:**")
        for item in persisting_items:
            trend = "\u2193 improving" if item.get("improved") else "\u2192 no change"
            lines.append(f"- \u26a0\ufe0f {item.get('family', '?')} / {item.get('metric', '?')} — {trend}")
        lines.append("")

    # New issues
    new_items = v.get("new", [])
    if new_items:
        lines.append("**New observations:**")
        for item in new_items:
            lines.append(f"- \U0001f535 {item.get('family', '?')} / {item.get('metric', '?')}")
        lines.append("")

    # Regressions
    regression_items = v.get("regressions", [])
    if regression_items:
        lines.append("**Regressions:**")
        for item in regression_items:
            lines.append(f"- \U0001f534 {item.get('family', '?')} / {item.get('metric', '?')} — was normal before")
        lines.append("")

    lines.append(
        f"<sub>Resolution rate: {rate:.0%} | "
        f"Powered by [Evolution Engine](https://github.com/evolution-engine/evolution-engine)</sub>"
    )

    return "\n".join(lines)


def _count_risks(changes: list) -> dict:
    """Count changes by risk level."""
    counts = {}
    for c in changes:
        risk = risk_level(c.get("deviation_stddev", 0))
        label = risk["label"]
        counts[label] = counts.get(label, 0) + 1
    return counts


def _fmt(value) -> str:
    """Format a number for display."""
    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:.0f}"
        elif abs(value) >= 10:
            return f"{value:.1f}"
        else:
            return f"{value:.2f}"
    return str(value)
