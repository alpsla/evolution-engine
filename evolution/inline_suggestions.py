"""
Inline Fix Suggestions — Map investigation findings to file-level review comments.

Parses an investigation report to extract findings with file references,
then produces GitHub-compatible review comment payloads that can be posted
as inline comments on a PR.

Usage:
    from evolution.inline_suggestions import extract_suggestions
    suggestions = extract_suggestions(investigation, advisory)
    # Each suggestion: {path, line, body, side}
"""

import json
import re
from pathlib import Path
from typing import Optional


def extract_suggestions(
    investigation: dict,
    advisory: dict,
    repo_path: str | Path = ".",
) -> list[dict]:
    """Extract inline suggestions from an investigation report.

    Parses the investigation text for file references (e.g. `src/main.py:42`)
    and maps them to review comment payloads.

    Args:
        investigation: Investigation report dict (from investigation.json).
        advisory: Phase 5 advisory dict.
        repo_path: Repository root path for file validation.

    Returns:
        List of suggestion dicts with: path, line, body, side.
    """
    if not investigation or not investigation.get("success"):
        return []

    report_text = investigation.get("report", "")
    if not report_text:
        return []

    suggestions = []
    repo = Path(repo_path)

    # Parse the investigation into findings
    findings = _parse_findings(report_text)

    for finding in findings:
        # Extract file references from the finding text
        file_refs = _extract_file_refs(finding["text"])

        if not file_refs:
            # No specific file — create a general suggestion from the finding
            # Map to the most relevant file from the advisory evidence
            relevant_file = _find_relevant_file(finding, advisory, repo)
            if relevant_file:
                suggestions.append({
                    "path": relevant_file,
                    "line": 1,
                    "body": _format_suggestion_body(finding),
                    "side": "RIGHT",
                })
        else:
            for ref in file_refs:
                # Validate file exists
                full_path = repo / ref["path"]
                if full_path.exists() or not repo.exists():
                    suggestions.append({
                        "path": ref["path"],
                        "line": ref.get("line", 1),
                        "body": _format_suggestion_body(finding),
                        "side": "RIGHT",
                    })

    # Deduplicate by path+line
    seen = set()
    deduped = []
    for s in suggestions:
        key = (s["path"], s["line"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return deduped


def format_review_payload(
    suggestions: list[dict],
    commit_sha: str,
    summary: str = "",
) -> dict:
    """Format suggestions as a GitHub Pull Request Review payload.

    Args:
        suggestions: List from extract_suggestions().
        commit_sha: HEAD commit SHA for the review.
        summary: Optional summary body for the review.

    Returns:
        Dict suitable for POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews.
    """
    if not summary:
        n = len(suggestions)
        summary = (
            f"## Evolution Engine — Fix Suggestions\n\n"
            f"Found **{n} suggestion{'s' if n != 1 else ''}** based on AI investigation.\n\n"
            f"<sub>These are automated suggestions — review carefully before applying.</sub>"
        )

    comments = []
    for s in suggestions:
        comments.append({
            "path": s["path"],
            "line": s["line"],
            "side": s.get("side", "RIGHT"),
            "body": s["body"],
        })

    return {
        "commit_id": commit_sha,
        "body": summary,
        "event": "COMMENT",  # COMMENT, APPROVE, or REQUEST_CHANGES
        "comments": comments,
    }


# ─── Internal Helpers ───


def _parse_findings(text: str) -> list[dict]:
    """Parse investigation text into structured findings.

    Expects format like:
        ## Finding 1: metric_name
        **Risk:** Medium
        **Root cause:** ...
        **Suggested fix:** ...
    """
    findings = []
    # Split on ## Finding headers
    sections = re.split(r"(?=##\s+Finding\s+\d+)", text)

    for section in sections:
        section = section.strip()
        if not section.startswith("## Finding"):
            continue

        # Extract title
        title_match = re.match(r"##\s+Finding\s+\d+[:\s]*(.*?)(?:\n|$)", section)
        title = title_match.group(1).strip() if title_match else ""

        # Extract risk
        risk_match = re.search(r"\*\*Risk[:\s]*\*\*\s*(.*?)(?:\n|$)", section)
        risk = risk_match.group(1).strip() if risk_match else ""

        # Extract suggested fix
        fix_match = re.search(
            r"\*\*Suggested\s+fix[:\s]*\*\*\s*(.*?)(?=\n\*\*|\n##|$)",
            section, re.DOTALL
        )
        fix = fix_match.group(1).strip() if fix_match else ""

        findings.append({
            "title": title,
            "risk": risk,
            "fix": fix,
            "text": section,
        })

    return findings


def _extract_file_refs(text: str) -> list[dict]:
    """Extract file:line references from text.

    Matches patterns like:
        src/main.py:42
        `evolution/cli.py:100`
        path/to/file.ts (line 15)
    """
    refs = []
    seen = set()

    # Pattern 1: path/file.ext:line
    for m in re.finditer(r"[`\s(]?([a-zA-Z0-9_./-]+\.\w{1,6}):(\d+)", text):
        path = m.group(1)
        line = int(m.group(2))
        if path not in seen:
            seen.add(path)
            refs.append({"path": path, "line": line})

    # Pattern 2: path/file.ext without line number
    if not refs:
        for m in re.finditer(r"[`\s(]([a-zA-Z0-9_./-]+\.\w{1,6})[`\s)]", text):
            path = m.group(1)
            # Filter out common non-file patterns
            if path.startswith("http") or path.startswith("www"):
                continue
            if path in seen:
                continue
            seen.add(path)
            refs.append({"path": path, "line": 1})

    return refs


def _find_relevant_file(finding: dict, advisory: dict, repo: Path) -> Optional[str]:
    """Find the most relevant file for a finding based on advisory evidence."""
    evidence = advisory.get("evidence", {})
    files = evidence.get("files_affected", [])

    if not files:
        return None

    # Try to match the finding title/metric to a relevant file
    title = finding.get("title", "").lower()

    # Return the first affected file that exists
    for f in files[:5]:
        fpath = f if isinstance(f, str) else f.get("path", "")
        if fpath and (repo / fpath).exists():
            return fpath

    # Fallback: return first file regardless
    first = files[0]
    return first if isinstance(first, str) else first.get("path", "")


def _format_suggestion_body(finding: dict) -> str:
    """Format a finding as a review comment body."""
    parts = []

    risk = finding.get("risk", "")
    if risk:
        parts.append(f"**Risk:** {risk}")

    fix = finding.get("fix", "")
    if fix:
        parts.append(f"\n{fix}")
    else:
        # Use the full finding text, truncated
        text = finding.get("text", "")
        # Remove the header
        text = re.sub(r"^##.*?\n", "", text).strip()
        if len(text) > 500:
            text = text[:497] + "..."
        parts.append(text)

    parts.append("\n<sub>Suggested by Evolution Engine</sub>")
    return "\n".join(parts)
