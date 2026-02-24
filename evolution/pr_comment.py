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

# Families that EE can detect from git alone (no token needed)
_BUILTIN_FAMILIES = {"git", "dependency"}

# Human-friendly display names for source families
_FAMILY_DISPLAY = {
    "git": "Git",
    "version_control": "Git",
    "ci": "CI",
    "deployment": "Deployments",
    "dependency": "Dependencies",
    "testing": "Testing",
    "coverage": "Coverage",
    "error_tracking": "Error Tracking",
    "monitoring": "Monitoring",
    "security_scan": "Security",
    "quality_gate": "Quality Gates",
    "incidents": "Incidents",
}


def format_pr_comment(
    advisory: dict,
    investigation: Optional[dict] = None,
    repo_name: str = None,
    sources_info: Optional[dict] = None,
    investigation_prompt: Optional[str] = None,
    report_url: Optional[str] = None,
    ci_provider: Optional[str] = None,
) -> str:
    """Format a Phase 5 advisory as a PR/MR comment.

    Args:
        advisory: Phase 5 advisory dict (from advisory.json).
        investigation: Optional investigation report dict.
        repo_name: Repository name for the header.
        sources_info: Optional dict from `evo sources --json` with connected/detected info.
        investigation_prompt: Optional copyable prompt for AI investigation.
        report_url: Optional URL to the HTML report artifact.
        ci_provider: CI platform — "github", "gitlab", or None (defaults to GitHub behavior).

    Returns:
        Markdown string suitable for `gh pr comment` or GitLab MR note.
    """
    scope = advisory.get("scope", repo_name or "repository")
    summary = advisory.get("summary", {})
    changes = advisory.get("changes", [])
    patterns = advisory.get("pattern_matches", [])
    candidates = advisory.get("candidate_patterns", [])

    significant = summary.get("significant_changes", len(changes))

    if significant == 0:
        lines = ["## Evolution Engine Analysis", ""]
        if sources_info:
            lines.extend(_format_sources_section(sources_info, ci_provider=ci_provider))
        lines.append("\u2705 **All clear** — no significant deviations detected.")
        lines.append("")
        lines.append(
            "<sub>Powered by [Evolution Engine](https://github.com/evolution-engine/evolution-engine)</sub>"
        )
        return "\n".join(lines)

    # Header with summary
    risk_counts = _count_risks(changes)
    risk_summary = ", ".join(
        f"{count} {label}" for label, count in risk_counts.items() if count > 0
    )

    lines = [
        "## Evolution Engine Analysis",
        "",
    ]

    # Sources section (What EE Can See)
    if sources_info:
        lines.extend(_format_sources_section(sources_info, ci_provider=ci_provider))

    # Findings header
    lines.append("### Findings")
    lines.append("")
    lines.append(f"**{significant} unusual change(s) detected** [{risk_summary}]")
    lines.append("")

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
        if len(desc) > 83:
            desc = desc[:80] + "..."
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

    # "What To Do Next" section
    lines.append("---")
    lines.append("")
    lines.extend(_format_next_steps(investigation_prompt, report_url, ci_provider=ci_provider))

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
    residual_prompt: Optional[str] = None,
    report_url: Optional[str] = None,
    ci_provider: Optional[str] = None,
) -> str:
    """Format a verification result as a PR/MR comment update.

    Args:
        verification: Verification dict from Phase 5 verify().
        previous_changes: Number of changes in the original advisory.
        residual_prompt: Optional prompt for continuing fixes on remaining issues.
        report_url: Optional URL to the HTML report artifact.
        ci_provider: CI platform — "github", "gitlab", or None.

    Returns:
        Markdown string for updating the PR/MR comment.
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

    # Report link
    if report_url:
        lines.append(f"\U0001f4ca [View Full Report]({report_url})")
        lines.append("")

    # "What To Do Next" section (if there are unresolved issues)
    if persisting > 0 or new_issues > 0 or regressions > 0:
        lines.append("---")
        lines.append("")
        lines.extend(_format_next_steps(residual_prompt, report_url, ci_provider=ci_provider))

    lines.append(
        f"<sub>Resolution rate: {rate:.0%} | "
        f"Powered by [Evolution Engine](https://github.com/evolution-engine/evolution-engine)</sub>"
    )

    return "\n".join(lines)


def format_accepted_comment(
    advisory: dict,
    accepted_by: str,
    scope: str = "this-pr",
    ci_provider: Optional[str] = None,
) -> str:
    """Format an accepted-state PR/MR comment.

    Shows that findings were acknowledged as intentional, with original
    findings collapsed in a details section.

    Args:
        advisory: Original Phase 5 advisory dict.
        accepted_by: Username who accepted the findings.
        scope: Acceptance scope — "this-pr" or "permanent".
        ci_provider: CI platform — "gitlab" shows "MR" instead of "PR".

    Returns:
        Markdown string for the accepted comment.
    """
    changes = advisory.get("changes", [])
    summary = advisory.get("summary", {})
    significant = summary.get("significant_changes", len(changes))

    pr_label = "MR" if ci_provider == "gitlab" else "PR"
    if scope == "permanent":
        scope_label = "Accepted permanently"
    else:
        scope_label = f"Accepted for this {pr_label}"

    lines = [
        "## Evolution Engine Analysis",
        "",
        f"\u2705 **{scope_label}** — findings acknowledged as intentional.",
        "",
    ]

    # Collapsed original findings
    if changes:
        lines.append(f"<details>")
        lines.append(f"<summary>Original findings ({significant} change{'s' if significant != 1 else ''})</summary>")
        lines.append("")
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
            if len(desc) > 83:
                desc = desc[:80] + "..."
            lines.append(
                f"| {badge} {risk['label']} | {family} | {metric} | {current} | {normal} | {desc} |"
            )

        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append(f"<sub>Accepted by @{accepted_by}</sub>")

    return "\n".join(lines)


# ─── Internal helpers ───


def _format_sources_section(sources_info: dict, ci_provider: Optional[str] = None) -> list[str]:
    """Format the 'What EE Can See' section from sources info.

    Args:
        sources_info: Dict from `evo sources --json` with connected/detected keys.
        ci_provider: CI platform — "gitlab" shows GITLAB_TOKEN hint.

    Returns:
        List of markdown lines.
    """
    lines = ["### What EE Can See", ""]

    connected = sources_info.get("connected", [])
    detected = sources_info.get("detected", [])
    connected_families = set(sources_info.get("current_families", []))

    token_name = "GITLAB_TOKEN" if ci_provider == "gitlab" else "GITHUB_TOKEN"

    # Always show git (built-in)
    if "git" in connected_families:
        # Find git adapter info for baseline count
        lines.append("\u2705 Git history")

    # Show connected non-git families (deduplicate via seen set)
    seen_display = set()
    for c in connected:
        family = c.get("family", "?")
        if family == "git":
            continue
        display = _FAMILY_DISPLAY.get(family, family.replace("_", " ").title())
        if display in seen_display:
            continue
        seen_display.add(display)
        lines.append(f"\u2705 {display}")

    # Show detected-but-not-connected as available to enable
    seen_families = set()
    for d in detected:
        family = d.get("family", "")
        if family in connected_families or family in seen_families:
            continue
        seen_families.add(family)
        display = d.get("display_name", _FAMILY_DISPLAY.get(family, family.replace("_", " ").title()))
        # Skip if this display name was already shown as connected
        if display in seen_display:
            continue
        seen_display.add(display)
        hint = ""
        if family in ("ci", "deployment"):
            hint = f" — add `{token_name}` secret to enable"
        lines.append(f"\u2b1c {display}{hint}")

    # Always hint at CI/deploy if not connected and not detected
    for family, label in [
        ("ci", "CI builds"),
        ("deployment", "Deployments"),
    ]:
        if family not in connected_families and family not in seen_families:
            lines.append(f"\u2b1c {label} — add `{token_name}` secret to enable")

    lines.append("")
    return lines


def _format_next_steps(
    investigation_prompt: Optional[str] = None,
    report_url: Optional[str] = None,
    ci_provider: Optional[str] = None,
) -> list[str]:
    """Format the 'What To Do Next' section.

    Args:
        investigation_prompt: Optional copyable prompt for AI tools.
        report_url: Optional URL to the HTML report artifact.
        ci_provider: CI platform — "gitlab" uses local accept instructions.

    Returns:
        List of markdown lines.
    """
    lines = ["### What To Do Next", ""]

    if investigation_prompt:
        lines.append("**Option A — Fix the drift:**")
        lines.append("Copy this prompt to your AI coding tool, then push your fixes.")
        lines.append("EE will automatically re-analyze and show resolution progress.")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>\U0001f4cb Investigation Prompt (expand, then copy)</summary>")
        lines.append("")
        lines.append("```text")
        lines.append(investigation_prompt)
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    else:
        lines.append("**Option A — Investigate:**")
        lines.append("Run `evo investigate .` locally or enable `investigate: true` in the action.")
        lines.append("")

    if ci_provider == "gitlab":
        lines.append("**Option B — Accept for this MR:**")
        lines.append(
            "If these changes are intentional, run `evo analyze .` to see numbered findings (starting from 1), "
            "then `evo accept . 1 2 --scope this-run` to accept specific changes for this MR. "
            "Commit `.evo/accepted.json` and push."
        )
        lines.append("")
        lines.append("**Option C — Accept permanently:**")
        lines.append(
            "Run `evo accept . 1 2` (permanent by default) to suppress these findings across all future MRs. "
            "Commit `.evo/accepted.json` and push."
        )
        lines.append("")
    else:
        lines.append("**Option B — Accept for this PR:**")
        lines.append("If these changes are intentional, leave a PR comment with just `/evo accept` — findings won't reappear on this PR.")
        lines.append("")
        lines.append("**Option C — Accept permanently:**")
        lines.append("Leave a PR comment with `/evo accept permanent` to suppress these findings across all future PRs.")
        lines.append("")

    if report_url:
        lines.append(f"\U0001f4ca [View Full Report]({report_url})")
        lines.append("")

    return lines


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
