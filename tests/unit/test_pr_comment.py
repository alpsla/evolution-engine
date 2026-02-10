"""Tests for PR comment formatting."""

import pytest
from evolution.pr_comment import (
    format_pr_comment,
    format_verification_comment,
    _count_risks,
    _fmt,
)


# ─── Fixtures ───


def _make_change(family="git", metric="files_touched", deviation=3.0,
                 current=12, median=4, description="Touched 12 files"):
    return {
        "family": family,
        "metric": metric,
        "deviation_stddev": deviation,
        "current": current,
        "normal": {"median": median},
        "description": description,
    }


def _make_advisory(changes=None, patterns=None, candidates=None,
                   families_affected=None, significant_changes=None):
    changes = changes or []
    return {
        "scope": "test-repo",
        "summary": {
            "significant_changes": significant_changes if significant_changes is not None else len(changes),
            "families_affected": families_affected or ["git"],
        },
        "changes": changes,
        "pattern_matches": patterns or [],
        "candidate_patterns": candidates or [],
    }


# ─── format_pr_comment ───


class TestFormatPrComment:
    def test_all_clear_no_changes(self):
        advisory = _make_advisory(significant_changes=0)
        result = format_pr_comment(advisory)
        assert "All clear" in result
        assert "no significant deviations" in result
        assert "Evolution Engine" in result

    def test_all_clear_empty_changes(self):
        advisory = _make_advisory(changes=[], significant_changes=0)
        result = format_pr_comment(advisory)
        assert "All clear" in result

    def test_single_change(self):
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "1 unusual change(s) detected" in result
        assert "git" in result
        assert "files_touched" in result
        assert "12" in result  # current value

    def test_multiple_changes_sorted_by_deviation(self):
        changes = [
            _make_change(metric="files_touched", deviation=2.0),
            _make_change(metric="dispersion", deviation=5.0, current=0.8, median=0.2),
        ]
        result = format_pr_comment(_make_advisory(changes=changes))
        # dispersion (5.0) should come before files_touched (2.0)
        disp_pos = result.index("dispersion")
        files_pos = result.index("files_touched")
        assert disp_pos < files_pos

    def test_risk_badges_in_output(self):
        changes = [
            _make_change(deviation=7.0),  # Critical
            _make_change(metric="dispersion", deviation=1.5),  # Low
        ]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "Critical" in result
        assert "Low" in result

    def test_risk_summary_in_header(self):
        changes = [
            _make_change(deviation=7.0),
            _make_change(metric="dispersion", deviation=3.0),
        ]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "2 unusual change(s) detected" in result
        # Should have risk counts in brackets
        assert "1 Critical" in result
        assert "1 Medium" in result

    def test_table_headers_present(self):
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "| Risk | Family | Metric | Now | Usual | Change |" in result

    def test_description_truncation(self):
        long_desc = "A" * 80
        changes = [_make_change(description=long_desc)]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "A" * 57 + "..." in result
        assert "A" * 80 not in result

    def test_short_description_not_truncated(self):
        short_desc = "Small change"
        changes = [_make_change(description=short_desc)]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "Small change" in result

    def test_pattern_matches_section(self):
        changes = [_make_change()]
        patterns = [
            {"description": "Dep changes correlate with dispersion", "sources": ["dep", "git"]},
        ]
        result = format_pr_comment(_make_advisory(changes=changes, patterns=patterns))
        assert "Patterns (1 known, 0 candidate)" in result
        assert "dep, git" in result
        assert "Dep changes correlate with dispersion" in result
        assert "<details>" in result

    def test_candidate_patterns_section(self):
        changes = [_make_change()]
        candidates = [
            {"description": "CI builds take longer with large changes", "families": ["ci", "git"]},
        ]
        result = format_pr_comment(_make_advisory(changes=changes, candidates=candidates))
        assert "Patterns (0 known, 1 candidate)" in result
        assert "ci, git" in result

    def test_patterns_limited_to_5(self):
        changes = [_make_change()]
        patterns = [
            {"description": f"Pattern {i}", "sources": ["git"]}
            for i in range(10)
        ]
        result = format_pr_comment(_make_advisory(changes=changes, patterns=patterns))
        assert "Pattern 4" in result
        assert "Pattern 5" not in result  # 0-indexed, so patterns 0-4 shown

    def test_investigation_included(self):
        changes = [_make_change()]
        investigation = {
            "success": True,
            "report": "## Finding 1: files_touched\nRisk: Medium\nLots of files changed.",
        }
        result = format_pr_comment(_make_advisory(changes=changes), investigation=investigation)
        assert "AI Investigation" in result
        assert "Finding 1: files_touched" in result

    def test_investigation_truncated_at_3000(self):
        changes = [_make_change()]
        investigation = {
            "success": True,
            "report": "A" * 5000,
        }
        result = format_pr_comment(_make_advisory(changes=changes), investigation=investigation)
        assert "... truncated" in result
        assert ".evo/investigation/" in result
        assert "A" * 5000 not in result

    def test_investigation_not_shown_when_failed(self):
        changes = [_make_change()]
        investigation = {"success": False, "report": "Error occurred"}
        result = format_pr_comment(_make_advisory(changes=changes), investigation=investigation)
        assert "AI Investigation" not in result

    def test_investigation_not_shown_when_none(self):
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes), investigation=None)
        assert "AI Investigation" not in result

    def test_footer_with_families(self):
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes, families_affected=["git", "ci"])
        result = format_pr_comment(advisory)
        assert "Families: git, ci" in result
        assert "Powered by" in result

    def test_repo_name_fallback(self):
        # scope not in advisory, repo_name provided
        advisory = {"summary": {"significant_changes": 0}, "changes": []}
        result = format_pr_comment(advisory, repo_name="my-repo")
        assert "All clear" in result

    def test_float_formatting_in_table(self):
        changes = [_make_change(current=0.85, median=0.25)]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "0.85" in result
        assert "0.25" in result

    def test_negative_deviation(self):
        changes = [_make_change(deviation=-3.5, current=1, median=5,
                                description="Fewer files than usual")]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "Medium" in result  # abs(3.5) >= 2.0
        assert "files_touched" in result


# ─── format_verification_comment ───


class TestFormatVerificationComment:
    def test_all_resolved(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 3,
                    "persisting": 0,
                    "new": 0,
                    "regressions": 0,
                    "total_before": 3,
                    "resolution_rate": 1.0,
                },
                "resolved": [
                    {"family": "git", "metric": "files_touched"},
                    {"family": "git", "metric": "dispersion"},
                    {"family": "ci", "metric": "run_duration"},
                ],
                "persisting": [],
                "new": [],
                "regressions": [],
            }
        }
        result = format_verification_comment(verification)
        assert "All clear" in result
        assert "all issues resolved" in result
        assert "git / files_touched" in result
        assert "back to normal" in result

    def test_partial_resolution(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 2,
                    "persisting": 1,
                    "new": 0,
                    "regressions": 0,
                    "total_before": 3,
                    "resolution_rate": 0.667,
                },
                "resolved": [
                    {"family": "git", "metric": "files_touched"},
                    {"family": "git", "metric": "dispersion"},
                ],
                "persisting": [
                    {"family": "ci", "metric": "run_duration", "improved": True},
                ],
                "new": [],
                "regressions": [],
            }
        }
        result = format_verification_comment(verification)
        assert "2 of 3 resolved" in result
        assert "67%" in result
        assert "Still flagged" in result
        assert "improving" in result

    def test_persisting_no_improvement(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 0,
                    "persisting": 2,
                    "new": 0,
                    "regressions": 0,
                    "total_before": 2,
                    "resolution_rate": 0,
                },
                "resolved": [],
                "persisting": [
                    {"family": "git", "metric": "files_touched", "improved": False},
                    {"family": "ci", "metric": "run_duration", "improved": False},
                ],
                "new": [],
                "regressions": [],
            }
        }
        result = format_verification_comment(verification)
        assert "No changes resolved yet" in result
        assert "no change" in result

    def test_regressions_shown(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 1,
                    "persisting": 0,
                    "new": 0,
                    "regressions": 2,
                    "total_before": 1,
                    "resolution_rate": 0.5,
                },
                "resolved": [{"family": "git", "metric": "files_touched"}],
                "persisting": [],
                "new": [],
                "regressions": [
                    {"family": "ci", "metric": "run_failed"},
                    {"family": "dep", "metric": "dependency_count"},
                ],
            }
        }
        result = format_verification_comment(verification)
        assert "regression(s)" in result
        assert "Regressions" in result
        assert "ci / run_failed" in result
        assert "was normal before" in result

    def test_new_issues_shown(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 1,
                    "persisting": 0,
                    "new": 1,
                    "regressions": 0,
                    "total_before": 1,
                    "resolution_rate": 0.5,
                },
                "resolved": [{"family": "git", "metric": "files_touched"}],
                "persisting": [],
                "new": [{"family": "dep", "metric": "max_depth"}],
                "regressions": [],
            }
        }
        result = format_verification_comment(verification)
        assert "New observations" in result
        assert "dep / max_depth" in result

    def test_verification_without_wrapper(self):
        """Verification dict without outer 'verification' key."""
        verification = {
            "summary": {
                "resolved": 0,
                "persisting": 0,
                "new": 0,
                "regressions": 0,
                "total_before": 0,
                "resolution_rate": 0,
            },
            "resolved": [],
            "persisting": [],
            "new": [],
            "regressions": [],
        }
        result = format_verification_comment(verification)
        assert "All clear" in result

    def test_resolution_rate_in_footer(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 1,
                    "persisting": 1,
                    "new": 0,
                    "regressions": 0,
                    "total_before": 2,
                    "resolution_rate": 0.5,
                },
                "resolved": [{"family": "git", "metric": "files_touched"}],
                "persisting": [{"family": "ci", "metric": "run_duration", "improved": False}],
                "new": [],
                "regressions": [],
            }
        }
        result = format_verification_comment(verification)
        assert "Resolution rate: 50%" in result

    def test_header_structure(self):
        verification = {
            "summary": {
                "resolved": 0, "persisting": 0, "new": 0,
                "regressions": 0, "total_before": 0, "resolution_rate": 0,
            },
            "resolved": [], "persisting": [], "new": [], "regressions": [],
        }
        result = format_verification_comment(verification)
        assert result.startswith("## Evolution Engine — Verification Update")


# ─── Helper functions ───


class TestCountRisks:
    def test_empty_changes(self):
        assert _count_risks([]) == {}

    def test_mixed_risk_levels(self):
        changes = [
            {"deviation_stddev": 7.0},   # Critical
            {"deviation_stddev": 5.0},   # High
            {"deviation_stddev": 3.0},   # Medium
            {"deviation_stddev": 1.5},   # Low
            {"deviation_stddev": 0.5},   # Normal
        ]
        counts = _count_risks(changes)
        assert counts["Critical"] == 1
        assert counts["High"] == 1
        assert counts["Medium"] == 1
        assert counts["Low"] == 1
        assert counts["Normal"] == 1

    def test_same_risk_level(self):
        changes = [
            {"deviation_stddev": 3.0},
            {"deviation_stddev": 2.5},
            {"deviation_stddev": 2.1},
        ]
        counts = _count_risks(changes)
        assert counts["Medium"] == 3

    def test_missing_deviation(self):
        changes = [{}]
        counts = _count_risks(changes)
        assert counts.get("Normal") == 1


class TestFmt:
    def test_large_float(self):
        assert _fmt(123.456) == "123"

    def test_medium_float(self):
        assert _fmt(12.34) == "12.3"

    def test_small_float(self):
        assert _fmt(1.23) == "1.23"

    def test_integer(self):
        assert _fmt(5) == "5"

    def test_string(self):
        assert _fmt("hello") == "hello"

    def test_zero_float(self):
        assert _fmt(0.0) == "0.00"


# ─── format_comment.py script ───


class TestFormatCommentScript:
    def test_script_importable(self, tmp_path):
        """Verify format_comment.py can be imported as a module."""
        import importlib.util
        script = Path(__file__).parent.parent.parent / "action" / "format_comment.py"
        if not script.exists():
            pytest.skip("action/format_comment.py not found")
        spec = importlib.util.spec_from_file_location("format_comment", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main")

    def test_script_writes_advisory_comment(self, tmp_path):
        """Run format_comment.py with a sample advisory."""
        import subprocess
        import json

        advisory = _make_advisory(
            changes=[_make_change()],
            families_affected=["git"],
        )
        advisory_path = tmp_path / "advisory.json"
        advisory_path.write_text(json.dumps(advisory))
        output_path = tmp_path / "comment.md"

        script = Path(__file__).parent.parent.parent / "action" / "format_comment.py"
        if not script.exists():
            pytest.skip("action/format_comment.py not found")

        result = subprocess.run(
            [sys.executable, str(script),
             "--advisory", str(advisory_path),
             "--output", str(output_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = output_path.read_text()
        assert "Evolution Engine" in content
        assert "files_touched" in content

    def test_script_writes_verification_comment(self, tmp_path):
        """Run format_comment.py with a sample verification."""
        import subprocess
        import json

        verification = {
            "verification": {
                "summary": {
                    "resolved": 1, "persisting": 0, "new": 0,
                    "regressions": 0, "total_before": 1, "resolution_rate": 1.0,
                },
                "resolved": [{"family": "git", "metric": "files_touched"}],
                "persisting": [], "new": [], "regressions": [],
            }
        }
        verification_path = tmp_path / "verification.json"
        verification_path.write_text(json.dumps(verification))
        output_path = tmp_path / "comment.md"

        script = Path(__file__).parent.parent.parent / "action" / "format_comment.py"
        if not script.exists():
            pytest.skip("action/format_comment.py not found")

        result = subprocess.run(
            [sys.executable, str(script),
             "--verification", str(verification_path),
             "--output", str(output_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = output_path.read_text()
        assert "Verification Update" in content
        assert "All clear" in content


import sys
from pathlib import Path
