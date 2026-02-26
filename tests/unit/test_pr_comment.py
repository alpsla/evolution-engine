"""Tests for PR comment formatting."""

import pytest
from evolution.pr_comment import (
    format_pr_comment,
    format_verification_comment,
    format_accepted_comment,
    _count_risks,
    _fmt,
    _format_sources_section,
    _format_next_steps,
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


def _make_sources_info(connected=None, detected=None, families=None):
    return {
        "connected": connected or [
            {"family": "git", "adapter": "builtin", "tier": 1},
            {"family": "dependency", "adapter": "builtin", "tier": 1},
        ],
        "detected": detected or [],
        "current_families": families or ["git", "dependency"],
        "current_combinations": 1,
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

    def test_description_not_truncated(self):
        long_desc = "A" * 100
        changes = [_make_change(description=long_desc)]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "A" * 100 in result

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
            {"description": f"Pattern {i}", "sources": ["git"], "families": ["git"], "metrics": [f"metric_{i}"]}
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


# ─── Sources section ───


class TestSourcesSection:
    def test_sources_section_in_comment(self):
        changes = [_make_change()]
        sources = _make_sources_info()
        result = format_pr_comment(_make_advisory(changes=changes), sources_info=sources)
        assert "### What EE Can See" in result
        assert "\u2705 Git history" in result

    def test_sources_shows_connected_families(self):
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "builtin", "tier": 1},
            ],
            families=["git", "ci"],
        )
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes), sources_info=sources)
        assert "\u2705 Git history" in result
        assert "\u2705 CI" in result

    def test_sources_shows_missing_families(self):
        sources = _make_sources_info(
            connected=[{"family": "git", "adapter": "builtin", "tier": 1}],
            families=["git"],
        )
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes), sources_info=sources)
        assert "\u2b1c" in result  # unchecked box for missing
        assert "CI builds" in result
        assert "GITHUB_TOKEN" in result

    def test_sources_hides_detected_without_action(self):
        """Detected services without a simple enable action are hidden from PR comment."""
        sources = _make_sources_info(
            connected=[{"family": "git", "adapter": "builtin", "tier": 1}],
            detected=[
                {"service": "sentry", "display_name": "Sentry", "family": "error_tracking",
                 "adapter": "evo-adapter-sentry", "detection_layers": ["config"]},
            ],
            families=["git"],
        )
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes), sources_info=sources)
        assert "Sentry" not in result
        # CI/deploy still hinted since they just need a token
        assert "CI builds" in result

    def test_sources_none_graceful(self):
        """No sources_info → no sources section at all."""
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes), sources_info=None)
        assert "What EE Can See" not in result

    def test_sources_in_all_clear(self):
        """Sources section still shown in all-clear comments."""
        sources = _make_sources_info()
        advisory = _make_advisory(significant_changes=0)
        result = format_pr_comment(advisory, sources_info=sources)
        assert "What EE Can See" in result
        assert "All clear" in result


# ─── Investigation prompt section ───


class TestInvestigationPrompt:
    def test_prompt_in_details_block(self):
        changes = [_make_change()]
        prompt = "Development pattern shift detected in my-repo.\nPlease investigate."
        result = format_pr_comment(
            _make_advisory(changes=changes),
            investigation_prompt=prompt,
        )
        assert "Investigation Prompt" in result
        assert "```text" in result
        assert "Development pattern shift detected" in result
        assert "Option A" in result
        assert "Option B" in result
        assert "Option C" in result

    def test_prompt_none_shows_fallback(self):
        changes = [_make_change()]
        result = format_pr_comment(
            _make_advisory(changes=changes),
            investigation_prompt=None,
        )
        assert "What To Do Next" in result
        assert "Option A" in result
        assert "Investigate" in result  # fallback wording
        assert "Investigation Prompt" not in result
        assert "Option B" in result
        assert "Option C" in result

    def test_what_to_do_next_always_present(self):
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "### What To Do Next" in result
        assert "/evo accept" in result

    def test_three_options_present(self):
        changes = [_make_change()]
        prompt = "Investigate this drift."
        result = format_pr_comment(
            _make_advisory(changes=changes),
            investigation_prompt=prompt,
        )
        assert "Option A — Fix the drift" in result
        assert "Option B — Accept for this PR" in result
        assert "Option C — Accept permanently" in result
        assert "/evo accept permanent" in result

    def test_three_options_without_prompt(self):
        changes = [_make_change()]
        result = format_pr_comment(_make_advisory(changes=changes))
        assert "Option A — Investigate" in result
        assert "Option B — Accept for this PR" in result
        assert "Option C — Accept permanently" in result
        assert "/evo accept permanent" in result

    def test_report_url_in_next_steps(self):
        changes = [_make_change()]
        result = format_pr_comment(
            _make_advisory(changes=changes),
            report_url="https://example.com/report",
        )
        assert "[View Full Report](https://example.com/report)" in result

    def test_report_url_none_no_link(self):
        changes = [_make_change()]
        result = format_pr_comment(
            _make_advisory(changes=changes),
            report_url=None,
        )
        assert "View Full Report" not in result


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


# ─── Verification with residual prompt ───


class TestVerificationResidualPrompt:
    def test_residual_prompt_in_verification(self):
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
                "resolved": [{"family": "git", "metric": "dispersion"}],
                "persisting": [{"family": "git", "metric": "files_touched", "improved": True}],
                "new": [],
                "regressions": [],
            }
        }
        residual = "ITERATION of fix loop...\nStill drifting: git/files_touched"
        result = format_verification_comment(verification, residual_prompt=residual)
        assert "### What To Do Next" in result
        assert "Investigation Prompt" in result
        assert "```text" in result
        assert "ITERATION of fix loop" in result

    def test_residual_prompt_not_shown_when_all_resolved(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 2,
                    "persisting": 0,
                    "new": 0,
                    "regressions": 0,
                    "total_before": 2,
                    "resolution_rate": 1.0,
                },
                "resolved": [
                    {"family": "git", "metric": "files_touched"},
                    {"family": "git", "metric": "dispersion"},
                ],
                "persisting": [],
                "new": [],
                "regressions": [],
            }
        }
        residual = "Should not appear"
        result = format_verification_comment(verification, residual_prompt=residual)
        assert "What To Do Next" not in result
        assert "Should not appear" not in result

    def test_residual_prompt_none_graceful(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 0,
                    "persisting": 1,
                    "new": 0,
                    "regressions": 0,
                    "total_before": 1,
                    "resolution_rate": 0,
                },
                "resolved": [],
                "persisting": [{"family": "git", "metric": "files_touched", "improved": False}],
                "new": [],
                "regressions": [],
            }
        }
        result = format_verification_comment(verification, residual_prompt=None)
        assert "Continue Fixing" not in result

    def test_report_url_in_verification(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 1,
                    "persisting": 0,
                    "new": 0,
                    "regressions": 0,
                    "total_before": 1,
                    "resolution_rate": 1.0,
                },
                "resolved": [{"family": "git", "metric": "files_touched"}],
                "persisting": [],
                "new": [],
                "regressions": [],
            }
        }
        result = format_verification_comment(
            verification,
            report_url="https://example.com/actions/runs/123",
        )
        assert "[View Full Report](https://example.com/actions/runs/123)" in result

    def test_report_url_none_no_link(self):
        verification = {
            "verification": {
                "summary": {
                    "resolved": 1,
                    "persisting": 0,
                    "new": 0,
                    "regressions": 0,
                    "total_before": 1,
                    "resolution_rate": 1.0,
                },
                "resolved": [{"family": "git", "metric": "files_touched"}],
                "persisting": [],
                "new": [],
                "regressions": [],
            }
        }
        result = format_verification_comment(verification, report_url=None)
        assert "View Full Report" not in result


# ─── format_accepted_comment ───


class TestFormatAcceptedComment:
    def test_accepted_basic(self):
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes)
        result = format_accepted_comment(advisory, accepted_by="alice")
        assert "## Evolution Engine Analysis" in result
        assert "Accepted for this PR" in result
        assert "findings acknowledged as intentional" in result
        assert "Accepted by @alice" in result

    def test_accepted_scope_this_pr(self):
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes)
        result = format_accepted_comment(advisory, accepted_by="alice", scope="this-pr")
        assert "Accepted for this PR" in result
        assert "Accepted permanently" not in result

    def test_accepted_scope_permanent(self):
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes)
        result = format_accepted_comment(advisory, accepted_by="alice", scope="permanent")
        assert "Accepted permanently" in result
        assert "Accepted for this PR" not in result

    def test_accepted_contains_original_findings(self):
        changes = [
            _make_change(metric="files_touched", deviation=5.0),
            _make_change(metric="dispersion", deviation=3.0, current=0.8, median=0.2),
        ]
        advisory = _make_advisory(changes=changes)
        result = format_accepted_comment(advisory, accepted_by="bob")
        assert "Original findings (2 changes)" in result
        assert "files_touched" in result
        assert "dispersion" in result
        assert "<details>" in result

    def test_accepted_single_change_grammar(self):
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes, significant_changes=1)
        result = format_accepted_comment(advisory, accepted_by="carol")
        assert "1 change)" in result
        assert "1 changes)" not in result

    def test_accepted_no_changes(self):
        advisory = _make_advisory(changes=[], significant_changes=0)
        result = format_accepted_comment(advisory, accepted_by="dave")
        assert "Accepted" in result
        assert "<details>" not in result  # no findings to collapse

    def test_accepted_table_format(self):
        changes = [_make_change(deviation=7.0)]
        advisory = _make_advisory(changes=changes)
        result = format_accepted_comment(advisory, accepted_by="eve")
        assert "| Risk | Family | Metric | Now | Usual | Change |" in result
        assert "Critical" in result

    def test_accepted_gitlab_says_mr(self):
        """GitLab provider: says 'this MR' not 'this PR'."""
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes)
        result = format_accepted_comment(advisory, accepted_by="alice", ci_provider="gitlab")
        assert "Accepted for this MR" in result
        assert "Accepted for this PR" not in result

    def test_accepted_github_says_pr(self):
        """Default (GitHub): says 'this PR'."""
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes)
        result = format_accepted_comment(advisory, accepted_by="alice", ci_provider=None)
        assert "Accepted for this PR" in result
        assert "Accepted for this MR" not in result

    def test_accepted_permanent_ignores_provider(self):
        """Permanent scope doesn't mention PR/MR."""
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes)
        result = format_accepted_comment(advisory, accepted_by="alice", scope="permanent", ci_provider="gitlab")
        assert "Accepted permanently" in result


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


class TestFormatSourcesSection:
    def test_basic_sources(self):
        sources = _make_sources_info()
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        assert "What EE Can See" in text
        assert "\u2705 Git history" in text

    def test_missing_ci_and_deploy_hinted(self):
        sources = _make_sources_info(
            connected=[{"family": "git", "adapter": "builtin", "tier": 1}],
            families=["git"],
        )
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        assert "CI builds" in text
        assert "Deployments" in text
        assert "GITHUB_TOKEN" in text

    def test_connected_ci_not_hinted(self):
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "builtin", "tier": 1},
            ],
            families=["git", "ci"],
        )
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        # CI connected, so no hint for CI
        assert "\u2705 CI" in text
        # But deployment still hinted
        assert "Deployments" in text

    def test_sources_gitlab_shows_gitlab_token(self):
        """GitLab provider: hints use GITLAB_TOKEN instead of GITHUB_TOKEN."""
        sources = _make_sources_info(
            connected=[{"family": "git", "adapter": "builtin", "tier": 1}],
            families=["git"],
        )
        lines = _format_sources_section(sources, ci_provider="gitlab")
        text = "\n".join(lines)
        assert "GITLAB_TOKEN" in text
        assert "GITHUB_TOKEN" not in text

    def test_sources_github_shows_github_token(self):
        """GitHub provider (default): hints use GITHUB_TOKEN."""
        sources = _make_sources_info(
            connected=[{"family": "git", "adapter": "builtin", "tier": 1}],
            families=["git"],
        )
        lines = _format_sources_section(sources, ci_provider=None)
        text = "\n".join(lines)
        assert "GITHUB_TOKEN" in text
        assert "GITLAB_TOKEN" not in text

    def test_detected_services_hidden_from_comment(self):
        """All detected-but-not-connected services are hidden — only CI/deploy hinted."""
        sources = _make_sources_info(
            connected=[{"family": "git", "adapter": "builtin", "tier": 1}],
            detected=[
                {"service": "pagerduty", "display_name": "PagerDuty", "family": "incidents",
                 "adapter": "evo-adapter-pagerduty", "detection_layers": ["config"]},
                {"service": "datadog", "display_name": "Datadog", "family": "monitoring",
                 "adapter": "evo-adapter-datadog", "detection_layers": ["config"]},
                {"service": "sentry", "display_name": "Sentry", "family": "error_tracking",
                 "adapter": "evo-adapter-sentry", "detection_layers": ["config"]},
            ],
            families=["git"],
        )
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        assert "PagerDuty" not in text
        assert "Datadog" not in text
        assert "Sentry" not in text
        # CI/deploy still get the token hint
        assert "CI builds" in text
        assert "Deployments" in text


class TestFormatNextSteps:
    def test_with_prompt(self):
        lines = _format_next_steps(investigation_prompt="Please investigate this drift.")
        text = "\n".join(lines)
        assert "Option A — Fix the drift" in text
        assert "Investigation Prompt" in text
        assert "Please investigate this drift." in text
        assert "Option B — Accept for this PR" in text
        assert "Option C — Accept permanently" in text
        assert "/evo accept" in text
        assert "/evo accept permanent" in text

    def test_without_prompt(self):
        lines = _format_next_steps(investigation_prompt=None)
        text = "\n".join(lines)
        assert "Option A — Investigate" in text
        assert "Investigation Prompt" not in text
        assert "Option B — Accept for this PR" in text
        assert "Option C — Accept permanently" in text
        assert "/evo accept" in text
        assert "/evo accept permanent" in text

    def test_with_report_url(self):
        lines = _format_next_steps(report_url="https://example.com/report")
        text = "\n".join(lines)
        assert "[View Full Report](https://example.com/report)" in text

    def test_without_report_url(self):
        lines = _format_next_steps(report_url=None)
        text = "\n".join(lines)
        assert "View Full Report" not in text

    def test_next_steps_gitlab_mentions_local_accept(self):
        """GitLab provider: mentions 'evo accept' locally, no '/evo accept'."""
        lines = _format_next_steps(ci_provider="gitlab")
        text = "\n".join(lines)
        assert "evo accept" in text
        assert "locally" in text
        assert "accepted.json" in text
        assert "/evo accept" not in text
        assert "this MR" in text

    def test_next_steps_github_default(self):
        """Default (GitHub): uses '/evo accept' comment instructions."""
        lines = _format_next_steps(ci_provider=None)
        text = "\n".join(lines)
        assert "/evo accept" in text
        assert "this PR" in text
        assert "accepted.json" not in text


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

    def test_canonical_module_importable(self):
        """Verify evolution.format_comment is importable (for python -m)."""
        from evolution.format_comment import main as fc_main
        assert callable(fc_main)

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

    def test_script_with_sources_and_prompt(self, tmp_path):
        """Run format_comment.py with sources and prompt flags."""
        import subprocess
        import json

        advisory = _make_advisory(
            changes=[_make_change()],
            families_affected=["git"],
        )
        advisory_path = tmp_path / "advisory.json"
        advisory_path.write_text(json.dumps(advisory))

        sources = _make_sources_info()
        sources_path = tmp_path / "sources.json"
        sources_path.write_text(json.dumps(sources))

        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("Investigate this drift in my-repo")

        output_path = tmp_path / "comment.md"

        script = Path(__file__).parent.parent.parent / "action" / "format_comment.py"
        if not script.exists():
            pytest.skip("action/format_comment.py not found")

        result = subprocess.run(
            [sys.executable, str(script),
             "--advisory", str(advisory_path),
             "--sources", str(sources_path),
             "--prompt", str(prompt_path),
             "--report-url", "https://example.com/report",
             "--output", str(output_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = output_path.read_text()
        assert "What EE Can See" in content
        assert "Investigation Prompt" in content
        assert "Investigate this drift" in content
        assert "View Full Report" in content

    def test_script_with_accepted_by(self, tmp_path):
        """Run format_comment.py with --accepted-by flag."""
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
             "--accepted-by", "testuser",
             "--output", str(output_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = output_path.read_text()
        assert "Accepted for this PR" in content
        assert "Accepted by @testuser" in content

    def test_script_with_accepted_by_permanent(self, tmp_path):
        """Run format_comment.py with --accepted-by and --scope permanent."""
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
             "--accepted-by", "testuser",
             "--scope", "permanent",
             "--output", str(output_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = output_path.read_text()
        assert "Accepted permanently" in content
        assert "Accepted by @testuser" in content

    def test_script_with_residual_prompt(self, tmp_path):
        """Run format_comment.py with --residual-prompt flag for verification."""
        import subprocess
        import json

        verification = {
            "verification": {
                "summary": {
                    "resolved": 1, "persisting": 1, "new": 0,
                    "regressions": 0, "total_before": 2, "resolution_rate": 0.5,
                },
                "resolved": [{"family": "git", "metric": "dispersion"}],
                "persisting": [{"family": "git", "metric": "files_touched", "improved": True}],
                "new": [], "regressions": [],
            }
        }
        verification_path = tmp_path / "verification.json"
        verification_path.write_text(json.dumps(verification))

        residual_path = tmp_path / "residual.txt"
        residual_path.write_text("Continue fixing: git/files_touched still drifting")

        output_path = tmp_path / "comment.md"

        script = Path(__file__).parent.parent.parent / "action" / "format_comment.py"
        if not script.exists():
            pytest.skip("action/format_comment.py not found")

        result = subprocess.run(
            [sys.executable, str(script),
             "--verification", str(verification_path),
             "--residual-prompt", str(residual_path),
             "--report-url", "https://example.com/runs/456",
             "--output", str(output_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = output_path.read_text()
        assert "What To Do Next" in content
        assert "Investigation Prompt" in content
        assert "git/files_touched still drifting" in content
        assert "View Full Report" in content

    def test_script_with_ci_provider_gitlab(self, tmp_path):
        """Run format_comment.py with --ci-provider gitlab — uses local accept."""
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
             "--ci-provider", "gitlab",
             "--output", str(output_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = output_path.read_text()
        assert "this MR" in content
        assert "locally" in content
        assert "/evo accept" not in content


import sys
from pathlib import Path


# ─── Accepted deviations visibility (Bug 7) ───


class TestAcceptedDeviationsVisibility:
    """Accepted deviations should be visible in PR comment output."""

    def test_accepted_shown_in_findings(self):
        """When there are accepted deviations alongside findings, show them."""
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes)
        advisory["summary"]["accepted_changes"] = 2
        advisory["summary"]["accepted_metrics"] = ["git/files_touched", "git/change_locality"]
        result = format_pr_comment(advisory)
        assert "2 accepted deviation(s) not shown" in result
        assert "git/files_touched" in result
        assert "git/change_locality" in result
        assert "evo accepted list" in result

    def test_accepted_shown_in_all_clear(self):
        """When all clear but accepted exist, show accepted note."""
        advisory = _make_advisory(significant_changes=0)
        advisory["summary"]["accepted_changes"] = 1
        advisory["summary"]["accepted_metrics"] = ["git/dispersion"]
        result = format_pr_comment(advisory)
        assert "All clear" in result
        assert "1 accepted deviation(s)" in result
        assert "git/dispersion" in result

    def test_no_accepted_no_extra_line(self):
        """When no accepted deviations, don't show the accepted line."""
        changes = [_make_change()]
        advisory = _make_advisory(changes=changes)
        result = format_pr_comment(advisory)
        assert "accepted deviation" not in result

    def test_accepted_many_truncated(self):
        """When many accepted metrics, show first 5 + count."""
        advisory = _make_advisory(significant_changes=0)
        metrics = [f"git/metric_{i}" for i in range(7)]
        advisory["summary"]["accepted_changes"] = 7
        advisory["summary"]["accepted_metrics"] = metrics
        result = format_pr_comment(advisory)
        assert "7 accepted deviation(s)" in result
        assert "+2 more" in result


# ─── Pro badge on Tier 2 adapters (Bug 5) ───


class TestProBadgeInSources:
    """Tier 2 adapters should show Pro badge in sources section."""

    def test_tier2_connected_shows_pro(self):
        """Connected Tier 2 adapters show Pro badge."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "github_actions", "tier": 2},
            ],
            families=["git", "ci"],
        )
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        assert "`Pro`" in text

    def test_tier1_no_pro_badge(self):
        """Tier 1 adapters don't show Pro badge on their own lines."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "dependency", "adapter": "builtin", "tier": 1},
            ],
            families=["git", "dependency"],
        )
        lines = _format_sources_section(sources)
        # Check that the dependency line specifically doesn't have Pro
        dep_lines = [l for l in lines if "Dependencies" in l]
        assert dep_lines
        assert "`Pro`" not in dep_lines[0]

    def test_ci_deploy_hints_show_pro(self):
        """CI/deploy hints show Pro badge."""
        sources = _make_sources_info(
            connected=[{"family": "git", "adapter": "builtin", "tier": 1}],
            families=["git"],
        )
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        assert "`Pro`" in text


# ─── Doc links (Bug 6) ───


class TestDocLinks:
    """Doc links should appear in sources section and next steps."""

    def test_sources_section_doc_link(self):
        """Sources section with hints includes setup guide link."""
        sources = _make_sources_info(
            connected=[{"family": "git", "adapter": "builtin", "tier": 1}],
            families=["git"],
        )
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        assert "INTEGRATIONS.md" in text

    def test_next_steps_verify_hint(self):
        """Next steps footer includes verify hint and docs link."""
        lines = _format_next_steps()
        text = "\n".join(lines)
        assert "evo analyze . --verify" in text
        assert "QUICKSTART.md" in text

    def test_sources_no_hints_no_doc_link(self):
        """When all families connected, no hint section = no doc link."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "github_actions", "tier": 2},
                {"family": "deployment", "adapter": "github_releases", "tier": 2},
            ],
            families=["git", "ci", "deployment"],
        )
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        assert "Setup guide" not in text


class TestDiagnosticHints:
    """Tests for diagnostic hints in sources section."""

    def test_platform_mismatch_hint(self):
        """Platform mismatch diagnostic appends hint to source line."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "github_actions", "tier": 2},
            ],
            families=["git", "ci"],
        )
        diagnostics = {
            "ci": {"status": "platform_mismatch", "message": "GITHUB_TOKEN is set but remote points to gitlab."}
        }
        lines = _format_sources_section(sources, diagnostics=diagnostics)
        text = "\n".join(lines)
        assert "(token/remote mismatch)" in text
        assert "CI" in text

    def test_no_data_hint(self):
        """no_data diagnostic appends (0 events) hint."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "deployment", "adapter": "github_releases", "tier": 2},
            ],
            families=["git", "deployment"],
        )
        diagnostics = {
            "deployment": {"status": "no_data", "message": "Connected to API but no events returned."}
        }
        lines = _format_sources_section(sources, diagnostics=diagnostics)
        text = "\n".join(lines)
        assert "(0 events)" in text

    def test_api_error_hint(self):
        """api_error diagnostic appends (API error) hint."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "github_actions", "tier": 2},
            ],
            families=["git", "ci"],
        )
        diagnostics = {
            "ci": {"status": "api_error", "message": "GitHub API returned 403 Forbidden."}
        }
        lines = _format_sources_section(sources, diagnostics=diagnostics)
        text = "\n".join(lines)
        assert "(API error)" in text

    def test_no_license_hint(self):
        """no_license diagnostic appends (requires Pro) hint."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "github_actions", "tier": 2},
            ],
            families=["git", "ci"],
        )
        diagnostics = {
            "ci": {"status": "no_license", "message": "Requires Evolution Engine Pro."}
        }
        lines = _format_sources_section(sources, diagnostics=diagnostics)
        text = "\n".join(lines)
        assert "(requires Pro)" in text

    def test_active_diagnostic_no_hint(self):
        """Active diagnostic should not add any hint suffix."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "github_actions", "tier": 2},
            ],
            families=["git", "ci"],
        )
        diagnostics = {"ci": {"status": "active", "message": ""}}
        lines = _format_sources_section(sources, diagnostics=diagnostics)
        text = "\n".join(lines)
        assert "(token/remote mismatch)" not in text
        assert "(0 events)" not in text
        assert "(API error)" not in text
        assert "(requires Pro)" not in text

    def test_no_diagnostics_backward_compat(self):
        """Without diagnostics param, no hints are added (backward compat)."""
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "github_actions", "tier": 2},
            ],
            families=["git", "ci"],
        )
        lines = _format_sources_section(sources)
        text = "\n".join(lines)
        assert "(token/remote mismatch)" not in text
        assert "(0 events)" not in text

    def test_diagnostics_in_format_pr_comment(self):
        """Diagnostics should propagate through format_pr_comment."""
        advisory = _make_advisory(
            changes=[_make_change()],
            families_affected=["git"],
        )
        sources = _make_sources_info(
            connected=[
                {"family": "git", "adapter": "builtin", "tier": 1},
                {"family": "ci", "adapter": "github_actions", "tier": 2},
            ],
            families=["git", "ci"],
        )
        diagnostics = {
            "ci": {"status": "platform_mismatch", "message": "GITHUB_TOKEN set but remote points to gitlab."}
        }
        comment = format_pr_comment(
            advisory, sources_info=sources, diagnostics=diagnostics,
        )
        assert "(token/remote mismatch)" in comment
