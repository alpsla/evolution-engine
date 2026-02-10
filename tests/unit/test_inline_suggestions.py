"""Unit tests for inline fix suggestions module."""

import pytest
from pathlib import Path

from evolution.inline_suggestions import (
    extract_suggestions,
    format_review_payload,
    _parse_findings,
    _extract_file_refs,
    _find_relevant_file,
    _format_suggestion_body,
)


# ─── _parse_findings ───


class TestParseFindings:
    def test_single_finding(self):
        text = """## Finding 1: files_touched
**Risk:** High
**Root cause:** Large refactor
**Suggested fix:** Split into smaller commits
"""
        findings = _parse_findings(text)
        assert len(findings) == 1
        assert findings[0]["title"] == "files_touched"
        assert findings[0]["risk"] == "High"
        assert "Split into smaller" in findings[0]["fix"]

    def test_multiple_findings(self):
        text = """Some preamble text

## Finding 1: dispersion
**Risk:** Medium
**Suggested fix:** Reduce scope

## Finding 2: files_touched
**Risk:** High
**Suggested fix:** Break up changes
"""
        findings = _parse_findings(text)
        assert len(findings) == 2
        assert findings[0]["title"] == "dispersion"
        assert findings[1]["title"] == "files_touched"

    def test_no_findings(self):
        text = "Just some regular text with no findings."
        assert _parse_findings(text) == []

    def test_finding_without_risk(self):
        text = """## Finding 1: metric_name
Some description without structured fields.
"""
        findings = _parse_findings(text)
        assert len(findings) == 1
        assert findings[0]["risk"] == ""
        assert findings[0]["fix"] == ""

    def test_finding_with_colon_in_title(self):
        text = "## Finding 1: ci/run_duration spike\n**Risk:** Low\n"
        findings = _parse_findings(text)
        assert findings[0]["title"] == "ci/run_duration spike"


# ─── _extract_file_refs ───


class TestExtractFileRefs:
    def test_path_with_line(self):
        text = "The issue is in `src/main.py:42` where the function is called."
        refs = _extract_file_refs(text)
        assert len(refs) == 1
        assert refs[0]["path"] == "src/main.py"
        assert refs[0]["line"] == 42

    def test_multiple_refs(self):
        text = "See src/a.py:10 and also src/b.py:20 for context."
        refs = _extract_file_refs(text)
        assert len(refs) == 2
        assert refs[0]["path"] == "src/a.py"
        assert refs[1]["path"] == "src/b.py"

    def test_deduplicates(self):
        text = "File src/main.py:10 and src/main.py:20 both reference it."
        refs = _extract_file_refs(text)
        assert len(refs) == 1  # same path, first line wins

    def test_path_without_line_fallback(self):
        text = "Check `config.toml` for the setting."
        refs = _extract_file_refs(text)
        assert len(refs) == 1
        assert refs[0]["path"] == "config.toml"
        assert refs[0]["line"] == 1

    def test_ignores_urls(self):
        text = "See `http://example.com` for docs and `config.py` for code."
        refs = _extract_file_refs(text)
        assert len(refs) == 1
        assert refs[0]["path"] == "config.py"

    def test_no_refs(self):
        text = "This finding has no file references at all."
        assert _extract_file_refs(text) == []

    def test_nested_path(self):
        text = "In `evolution/phase2_engine.py:100` the baseline is computed."
        refs = _extract_file_refs(text)
        assert refs[0]["path"] == "evolution/phase2_engine.py"
        assert refs[0]["line"] == 100


# ─── _find_relevant_file ───


class TestFindRelevantFile:
    def test_returns_first_existing_file(self, tmp_path):
        (tmp_path / "a.py").touch()
        advisory = {"evidence": {"files_affected": ["missing.py", "a.py"]}}
        finding = {"title": "test"}
        result = _find_relevant_file(finding, advisory, tmp_path)
        assert result == "a.py"

    def test_fallback_to_first_file(self, tmp_path):
        advisory = {"evidence": {"files_affected": ["nonexistent.py"]}}
        finding = {"title": "test"}
        result = _find_relevant_file(finding, advisory, tmp_path)
        assert result == "nonexistent.py"

    def test_no_files(self, tmp_path):
        advisory = {"evidence": {"files_affected": []}}
        result = _find_relevant_file({"title": ""}, advisory, tmp_path)
        assert result is None

    def test_no_evidence(self, tmp_path):
        result = _find_relevant_file({"title": ""}, {}, tmp_path)
        assert result is None

    def test_dict_format_files(self, tmp_path):
        (tmp_path / "b.py").touch()
        advisory = {
            "evidence": {
                "files_affected": [
                    {"path": "missing.py"},
                    {"path": "b.py"},
                ]
            }
        }
        result = _find_relevant_file({"title": ""}, advisory, tmp_path)
        assert result == "b.py"


# ─── _format_suggestion_body ───


class TestFormatSuggestionBody:
    def test_with_risk_and_fix(self):
        finding = {"risk": "High", "fix": "Refactor this", "text": "full text"}
        body = _format_suggestion_body(finding)
        assert "**Risk:** High" in body
        assert "Refactor this" in body
        assert "Suggested by Evolution Engine" in body

    def test_without_fix_uses_text(self):
        finding = {"risk": "", "fix": "", "text": "## Finding 1\nSome details here"}
        body = _format_suggestion_body(finding)
        assert "Some details here" in body
        assert "## Finding" not in body  # header stripped

    def test_truncates_long_text(self):
        finding = {"risk": "", "fix": "", "text": "## H\n" + "x" * 600}
        body = _format_suggestion_body(finding)
        assert body.count("x") <= 500
        assert "..." in body

    def test_no_risk_no_prefix(self):
        finding = {"risk": "", "fix": "Do the fix", "text": ""}
        body = _format_suggestion_body(finding)
        assert "**Risk:**" not in body


# ─── extract_suggestions (integration) ───


class TestExtractSuggestions:
    def test_empty_investigation(self):
        assert extract_suggestions(None, {}) == []
        assert extract_suggestions({}, {}) == []
        assert extract_suggestions({"success": False}, {}) == []

    def test_no_report_text(self):
        result = extract_suggestions({"success": True, "report": ""}, {})
        assert result == []

    def test_with_file_refs(self, tmp_path):
        investigation = {
            "success": True,
            "report": """## Finding 1: dispersion spike
**Risk:** High
**Suggested fix:** See `src/main.py:42` for the issue.
""",
        }
        advisory = {}
        # repo_path doesn't exist, so file validation is skipped
        result = extract_suggestions(investigation, advisory, repo_path="/nonexistent")
        assert len(result) == 1
        assert result[0]["path"] == "src/main.py"
        assert result[0]["line"] == 42
        assert result[0]["side"] == "RIGHT"

    def test_falls_back_to_advisory_files(self, tmp_path):
        (tmp_path / "affected.py").touch()
        investigation = {
            "success": True,
            "report": """## Finding 1: some metric
**Risk:** Medium
**Suggested fix:** Reduce complexity in the module.
""",
        }
        advisory = {"evidence": {"files_affected": ["affected.py"]}}
        result = extract_suggestions(investigation, advisory, repo_path=tmp_path)
        assert len(result) == 1
        assert result[0]["path"] == "affected.py"
        assert result[0]["line"] == 1

    def test_deduplicates_same_path_line(self, tmp_path):
        investigation = {
            "success": True,
            "report": """## Finding 1: metric_a
**Risk:** High
**Suggested fix:** See `src/a.py:10`

## Finding 2: metric_b
**Risk:** Medium
**Suggested fix:** Also see `src/a.py:10`
""",
        }
        result = extract_suggestions(investigation, {}, repo_path="/nonexistent")
        # Both findings reference same file:line, should deduplicate
        paths = [(s["path"], s["line"]) for s in result]
        assert len(set(paths)) == len(paths)

    def test_multiple_findings_multiple_files(self):
        investigation = {
            "success": True,
            "report": """## Finding 1: dispersion
**Risk:** High
**Suggested fix:** See `src/a.py:10`

## Finding 2: files_touched
**Risk:** Medium
**Suggested fix:** See `src/b.py:20`
""",
        }
        result = extract_suggestions(investigation, {}, repo_path="/nonexistent")
        assert len(result) == 2
        paths = {s["path"] for s in result}
        assert paths == {"src/a.py", "src/b.py"}


# ─── format_review_payload ───


class TestFormatReviewPayload:
    def test_basic_payload(self):
        suggestions = [
            {"path": "src/main.py", "line": 42, "body": "Fix this", "side": "RIGHT"},
        ]
        payload = format_review_payload(suggestions, commit_sha="abc123")
        assert payload["commit_id"] == "abc123"
        assert payload["event"] == "COMMENT"
        assert len(payload["comments"]) == 1
        assert payload["comments"][0]["path"] == "src/main.py"
        assert payload["comments"][0]["line"] == 42

    def test_auto_summary(self):
        suggestions = [
            {"path": "a.py", "line": 1, "body": "fix", "side": "RIGHT"},
            {"path": "b.py", "line": 1, "body": "fix", "side": "RIGHT"},
        ]
        payload = format_review_payload(suggestions, commit_sha="sha")
        assert "2 suggestions" in payload["body"]

    def test_singular_summary(self):
        suggestions = [
            {"path": "a.py", "line": 1, "body": "fix", "side": "RIGHT"},
        ]
        payload = format_review_payload(suggestions, commit_sha="sha")
        assert "1 suggestion" in payload["body"]
        assert "1 suggestions" not in payload["body"]

    def test_custom_summary(self):
        payload = format_review_payload(
            [{"path": "a.py", "line": 1, "body": "x", "side": "RIGHT"}],
            commit_sha="sha",
            summary="Custom summary",
        )
        assert payload["body"] == "Custom summary"

    def test_empty_suggestions(self):
        payload = format_review_payload([], commit_sha="sha")
        assert payload["comments"] == []
        assert "0 suggestions" in payload["body"]
