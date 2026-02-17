"""Unit tests for the HTML report generator."""

import json
from pathlib import Path

import pytest

from evolution.report_generator import (
    generate_report, _esc, _fmt_num, _format_date, _detect_remote_url,
    _render_html,
)


@pytest.fixture
def advisory_dir(tmp_path):
    """Create a minimal Phase 5 output directory."""
    phase5 = tmp_path / "phase5"
    phase5.mkdir()

    advisory = {
        "advisory_id": "test123",
        "scope": "test/repo",
        "generated_at": "2026-02-09T12:00:00Z",
        "period": {
            "from": "2025-01-01T00:00:00Z",
            "to": "2026-02-09T12:00:00Z",
        },
        "summary": {
            "significant_changes": 3,
            "families_affected": ["git", "dependency"],
            "known_patterns_matched": 1,
            "candidate_patterns_matched": 0,
            "event_groups": 2,
            "new_observations": 2,
        },
        "changes": [
            {
                "family": "git",
                "metric": "files_touched",
                "normal": {"mean": 3.5, "stddev": 5.0, "median": 2.0, "mad": 1.0},
                "current": 150,
                "deviation_stddev": 99.83,
                "deviation_unit": "modified_zscore",
                "description": "This change touched 150 files.",
                "event_ref": "abc123",
            },
            {
                "family": "git",
                "metric": "dispersion",
                "normal": {"mean": 0.3, "stddev": 0.2, "median": 0.1, "mad": 0.05},
                "current": 1.5,
                "deviation_stddev": 18.87,
                "deviation_unit": "modified_zscore",
                "description": "High dispersion detected.",
                "event_ref": "abc123",
            },
            {
                "family": "dependency",
                "metric": "dependency_count",
                "normal": {"mean": 50.0, "stddev": 10.0, "median": 48.0, "mad": 5.0},
                "current": 120,
                "deviation_stddev": 9.69,
                "deviation_unit": "modified_zscore",
                "description": "Dependency count increased.",
                "event_ref": "def456",
            },
        ],
        "event_groups": [
            {
                "event_ref": "abc123",
                "primary": {
                    "family": "git",
                    "metric": "files_touched",
                    "normal": {"mean": 3.5, "stddev": 5.0, "median": 2.0, "mad": 1.0},
                    "current": 150,
                    "deviation_stddev": 99.83,
                    "deviation_unit": "modified_zscore",
                    "description": "This change touched 150 files.",
                    "event_ref": "abc123",
                },
                "families": ["git"],
                "changes": [
                    {
                        "family": "git",
                        "metric": "files_touched",
                        "normal": {"mean": 3.5, "stddev": 5.0, "median": 2.0, "mad": 1.0},
                        "current": 150,
                        "deviation_stddev": 99.83,
                        "deviation_unit": "modified_zscore",
                        "event_ref": "abc123",
                    },
                    {
                        "family": "git",
                        "metric": "dispersion",
                        "normal": {"mean": 0.3, "stddev": 0.2, "median": 0.1, "mad": 0.05},
                        "current": 1.5,
                        "deviation_stddev": 18.87,
                        "deviation_unit": "modified_zscore",
                        "event_ref": "abc123",
                    },
                ],
                "signal_count": 2,
            },
            {
                "event_ref": "def456",
                "primary": {
                    "family": "dependency",
                    "metric": "dependency_count",
                    "normal": {"mean": 50.0, "stddev": 10.0, "median": 48.0, "mad": 5.0},
                    "current": 120,
                    "deviation_stddev": 9.69,
                    "deviation_unit": "modified_zscore",
                    "event_ref": "def456",
                },
                "families": ["dependency"],
                "changes": [
                    {
                        "family": "dependency",
                        "metric": "dependency_count",
                        "normal": {"mean": 50.0, "stddev": 10.0, "median": 48.0, "mad": 5.0},
                        "current": 120,
                        "deviation_stddev": 9.69,
                        "deviation_unit": "modified_zscore",
                        "event_ref": "def456",
                    },
                ],
                "signal_count": 1,
            },
        ],
        "pattern_matches": [
            {
                "sources": ["git", "dependency"],
                "metrics": ["dispersion", "dependency_count"],
                "correlation_strength": 0.45,
                "description_statistical": "Git dispersion correlates with dependency count.",
            },
        ],
        "candidate_patterns": [],
    }

    evidence = {
        "evidence_id": "ev123",
        "advisory_ref": "test123",
        "commits": [
            {
                "sha": "a1b2c3d4e5f6",
                "message": "Fix the widget parser\n\nLong description.",
                "author": {"name": "Alice", "email": "alice@test.com"},
                "timestamp": "2026-02-08T10:00:00Z",
                "files_changed": ["src/parser.py", "tests/test_parser.py"],
            },
        ],
        "files_affected": [
            {"path": "src/parser.py", "change_type": "modified"},
            {"path": "tests/test_parser.py", "change_type": "modified"},
        ],
        "dependencies_changed": [],
        "timeline": [
            {
                "family": "git",
                "event_text": "Commit a1b2c3: Fix the widget parser",
                "timestamp": "2026-02-08T10:00:00Z",
            },
        ],
    }

    (phase5 / "advisory.json").write_text(json.dumps(advisory))
    (phase5 / "evidence.json").write_text(json.dumps(evidence))

    return tmp_path


class TestGenerateReport:
    def test_produces_valid_html(self, advisory_dir):
        html = generate_report(advisory_dir)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_scope(self, advisory_dir):
        html = generate_report(advisory_dir)
        assert "test/repo" in html

    def test_contains_changes(self, advisory_dir):
        html = generate_report(advisory_dir)
        assert "Files Changed" in html
        assert "Change Dispersion" in html
        assert "Total Dependencies" in html

    def test_contains_pattern_section(self, advisory_dir):
        html = generate_report(advisory_dir)
        assert "Patterns" in html
        assert "Known Pattern" in html

    def test_contains_evidence(self, advisory_dir):
        html = generate_report(advisory_dir)
        assert "a1b2c3" in html
        assert "Fix the widget parser" in html
        assert "src/parser.py" in html

    def test_contains_evidence_in_prompt(self, advisory_dir):
        """Evidence (commits, files) is embedded in the full investigation prompt."""
        html = generate_report(advisory_dir)
        assert "COMMITS" in html
        assert "SOURCE FILES CHANGED" in html

    def test_custom_title(self, advisory_dir):
        html = generate_report(advisory_dir, title="My Custom Report")
        assert "My Custom Report" in html

    def test_with_calibration_stats(self, advisory_dir):
        cal = {"events": 5000, "signals": 12345}
        html = generate_report(advisory_dir, calibration_result=cal)
        assert "5,000" in html
        assert "12,345" in html

    def test_missing_advisory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            generate_report(tmp_path)

    def test_no_evidence_file(self, advisory_dir):
        """Report works even if evidence.json doesn't exist."""
        (advisory_dir / "phase5" / "evidence.json").unlink()
        html = generate_report(advisory_dir)
        assert "<!DOCTYPE html>" in html
        assert "Evolution Advisory" in html

    def test_empty_advisory(self, tmp_path):
        """Minimal advisory with no changes."""
        phase5 = tmp_path / "phase5"
        phase5.mkdir()
        (phase5 / "advisory.json").write_text(json.dumps({
            "advisory_id": "empty",
            "scope": "empty/repo",
            "generated_at": "2026-01-01T00:00:00Z",
            "period": {"from": "", "to": ""},
            "summary": {
                "significant_changes": 0,
                "families_affected": [],
                "known_patterns_matched": 0,
                "candidate_patterns_matched": 0,
                "event_groups": 0,
                "new_observations": 0,
            },
            "changes": [],
            "event_groups": [],
            "pattern_matches": [],
            "candidate_patterns": [],
        }))
        html = generate_report(tmp_path)
        assert "No unusual changes detected" in html

    def test_change_cards_have_anchor_ids(self, advisory_dir):
        """Each change card should have a unique id for deep-linking."""
        html = generate_report(advisory_dir)
        assert 'id="change-git-files_touched"' in html
        assert 'id="change-git-dispersion"' in html
        assert 'id="change-dependency-dependency_count"' in html

    def test_change_cards_contain_action_buttons(self, advisory_dir):
        """Each change card should have Accept and Fix with AI action buttons."""
        html = generate_report(advisory_dir)
        assert 'class="change-actions' in html
        assert "Accept" in html
        assert "Fix with AI" in html
        # Verify the accept commands use correct 1-based indices
        assert "evo accept . 1" in html
        assert "evo accept . 2" in html
        assert "evo accept . 3" in html
        # Verify fix prompt contains investigation steps and after-fix guidance
        assert "INVESTIGATE:" in html
        assert "AFTER FIX:" in html
        assert "evo analyze ." in html
        # Verify progress tracker
        assert 'id="progressTracker"' in html
        assert "0</span> of 3 resolved" in html

    def test_filter_buttons_present(self, advisory_dir):
        """Severity filter buttons should appear in the changes section."""
        html = generate_report(advisory_dir)
        assert 'class="severity-filters' in html
        assert "filterChanges(" in html
        assert 'btn-filter active" onclick="filterChanges(\'all\'' in html
        assert ">All</button>" in html
        assert ">Critical</button>" in html
        assert ">Medium</button>" in html
        assert ">Low</button>" in html

    def test_evidence_in_drift_prompt(self, advisory_dir):
        """Drift prompt embeds recent commits as evidence."""
        html = generate_report(advisory_dir)
        assert "RECENT COMMITS" in html or "FILES CHANGED IN TRIGGER" in html

    def test_filter_js_function_present(self, advisory_dir):
        """The filterChanges JS function should be in the report."""
        html = generate_report(advisory_dir)
        assert "function filterChanges(" in html
        assert "filter-hidden" in html

    def test_copy_command_js_function_present(self, advisory_dir):
        """The copyCommand JS function should be in the report."""
        html = generate_report(advisory_dir)
        assert "function copyCommand(" in html

    def test_accept_posts_to_server(self, advisory_dir):
        """acceptFinding JS should POST to /api/accept before clipboard fallback."""
        html = generate_report(advisory_dir)
        assert "fetch('/api/accept'" in html
        assert "'Content-Type': 'application/json'" in html

    def test_accept_clipboard_fallback(self, advisory_dir):
        """acceptFinding JS should fall back to clipboard on fetch failure."""
        html = generate_report(advisory_dir)
        assert ".catch(function()" in html
        assert "_copyText(text)" in html
        assert "Command copied" in html

    def test_accept_buttons_pass_scope(self, advisory_dir):
        """Accept button onclick should pass scope as second argument."""
        html = generate_report(advisory_dir)
        assert "'permanent'" in html
        assert "'this-run'" in html

    def test_show_toast_function_present(self, advisory_dir):
        """_showToast helper should exist in the report JS."""
        html = generate_report(advisory_dir)
        assert "function _showToast(" in html

    def test_mark_accepted_function_present(self, advisory_dir):
        """_markAccepted helper should exist in the report JS."""
        html = generate_report(advisory_dir)
        assert "function _markAccepted(" in html

    def test_load_accepted_on_page_load(self, advisory_dir):
        """DOMContentLoaded should fetch /api/accepted."""
        html = generate_report(advisory_dir)
        assert "fetch('/api/accepted')" in html


class TestHelpers:
    def test_esc_html(self):
        assert _esc('<script>alert("xss")</script>') == '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
        assert _esc("normal text") == "normal text"
        assert _esc("a & b") == "a &amp; b"

    def test_fmt_num_int(self):
        assert _fmt_num(1234) == "1,234"
        assert _fmt_num(0) == "0"

    def test_fmt_num_float(self):
        assert _fmt_num(0.0001) == "0.0001"
        assert _fmt_num(1.5) == "1.50"
        assert _fmt_num(1234.5) == "1,234.5"

    def test_format_date(self):
        assert _format_date("2026-02-09T12:30:00Z") == "Feb 09, 2026 at 12:30 PM"
        assert _format_date("") == ""
        assert _format_date("not-a-date") == "not-a-date"


class TestReportPolish:
    """Tests for Fix #15: confidence, commit links, similar-severity patterns."""

    def test_confidence_note_shown(self, advisory_dir):
        """Executive summary should show confidence based on commit count."""
        html = generate_report(advisory_dir)
        assert "Based on" in html
        assert "prior commit" in html

    def test_commit_links_with_remote(self):
        """When remote_url is provided, commit SHAs should be clickable."""
        advisory = {
            "scope": "test/repo",
            "generated_at": "2026-02-09T12:00:00Z",
            "period": {"from": "2026-01-01", "to": "2026-02-09"},
            "summary": {
                "significant_changes": 1,
                "families_affected": ["git"],
                "known_patterns_matched": 0,
                "candidate_patterns_matched": 0,
            },
            "changes": [{
                "family": "git", "metric": "files_touched",
                "normal": {"mean": 3, "median": 2, "mad": 1},
                "current": 50, "deviation_stddev": 10.0,
                "trigger_commit": "abc123def456", "commit_message": "Big refactor",
            }],
            "pattern_matches": [], "candidate_patterns": [],
        }
        evidence = {
            "commits": [{"sha": "abc123def456", "message": "Big refactor",
                         "author": {"name": "Test"}, "timestamp": "2026-02-08T10:00:00Z"}],
            "files_affected": [], "dependencies_changed": [], "timeline": [],
        }
        html = _render_html(advisory, evidence, "Test",
                            remote_url="https://github.com/owner/repo")
        assert 'href="https://github.com/owner/repo/commit/abc123def456"' in html
        assert 'class="commit-link"' in html

    def test_commit_links_without_remote(self):
        """Without remote_url, commit SHAs should be plain text."""
        advisory = {
            "scope": "test/repo",
            "generated_at": "2026-02-09T12:00:00Z",
            "period": {"from": "2026-01-01", "to": "2026-02-09"},
            "summary": {
                "significant_changes": 1,
                "families_affected": ["git"],
                "known_patterns_matched": 0,
                "candidate_patterns_matched": 0,
            },
            "changes": [{
                "family": "git", "metric": "files_touched",
                "normal": {"mean": 3, "median": 2, "mad": 1},
                "current": 50, "deviation_stddev": 10.0,
                "trigger_commit": "abc123def456",
            }],
            "pattern_matches": [], "candidate_patterns": [],
        }
        evidence = {
            "commits": [{"sha": "abc123def456", "message": "Refactor",
                         "author": {"name": "Test"}, "timestamp": "2026-02-08T10:00:00Z"}],
            "files_affected": [], "dependencies_changed": [], "timeline": [],
        }
        html = _render_html(advisory, evidence, "Test", remote_url="")
        assert "<code>abc123de</code>" in html
        assert "commit-link" not in html.split("fix-prompt-text")[0]  # not in commit attribution

    def test_detect_remote_url_no_repo(self, tmp_path):
        """Non-git directory should return empty string."""
        assert _detect_remote_url(tmp_path) == ""

    def test_similar_severity_patterns_label(self, advisory_dir):
        """Pattern groups should use 'similar-severity patterns' not 'related patterns'."""
        from evolution.report_generator import _build_grouped_pattern_card
        patterns = [
            {"sources": ["git"], "metrics": ["dispersion"], "correlation_strength": 0.5},
            {"sources": ["git"], "metrics": ["dispersion"], "correlation_strength": 0.4},
        ]
        html = _build_grouped_pattern_card(patterns, "Known Pattern")
        assert "similar-severity patterns" in html
        assert "related patterns" not in html


class TestVerificationBanner:
    """Test _build_verification_banner historical trigger detection."""

    def _persisting(self, **overrides):
        """Build a persisting change dict with sensible defaults."""
        base = {
            "family": "git", "metric": "dispersion",
            "was_deviation": 4.0, "now_deviation": 4.0,
            "improved": False,
            "current": 0.20, "was_value": 0.20,  # value near baseline = transient
            "latest_value": 0.20,
            "normal": {"median": 0.20, "mean": 0.20, "stddev": 0.5, "mad": 0.3},
        }
        base.update(overrides)
        return base

    def test_transient_historical_trigger(self):
        """Unchanged deviation + latest value near baseline → 'returned to normal'."""
        from evolution.report_generator import _build_verification_banner
        verification = {
            "resolved": [],
            "persisting": [self._persisting(
                latest_deviation=0.5, latest_value=0.22,  # near baseline 0.20
            )],
            "new": [],
        }
        html = _build_verification_banner(verification)
        assert "returned to normal" in html
        assert "Transient spike" in html
        assert "Stabilized drift" not in html
        assert "Active deviation" not in html

    def test_persistent_historical_trigger(self):
        """Unchanged deviation + high latest_deviation → 'still actively deviating'."""
        from evolution.report_generator import _build_verification_banner
        verification = {
            "resolved": [],
            "persisting": [self._persisting(latest_deviation=2.5)],
            "new": [],
        }
        html = _build_verification_banner(verification)
        assert "still actively deviating" in html
        assert "verify-trend-warn" in html
        assert "Active deviation" in html
        assert "Transient spike" not in html

    def test_stabilized_drift(self):
        """Low latest deviation but value far from baseline → 'stabilized at new level'."""
        from evolution.report_generator import _build_verification_banner
        verification = {
            "resolved": [],
            "persisting": [self._persisting(
                family="dependency", metric="dependency_count",
                was_deviation=182.1, now_deviation=182.1,
                current=1613, was_value=1613,
                latest_value=1613,  # far from baseline 1478
                normal={"median": 1478, "mean": 1478, "stddev": 10, "mad": 5},
                latest_deviation=0.0,
            )],
            "new": [],
        }
        html = _build_verification_banner(verification)
        assert "stabilized at new level" in html
        assert "verify-trend-stabilized" in html
        assert "Stabilized drift" in html
        assert "Transient spike" not in html

    def test_mixed_transient_and_persistent(self):
        """Both transient and active deviation → both notes shown."""
        from evolution.report_generator import _build_verification_banner
        verification = {
            "resolved": [],
            "persisting": [
                self._persisting(
                    latest_deviation=0.3, latest_value=0.21,  # near baseline
                ),
                self._persisting(
                    family="ci", metric="run_duration",
                    was_deviation=3.0, now_deviation=3.0,
                    current=120, was_value=120,
                    latest_value=120,
                    normal={"median": 45, "mean": 45, "stddev": 10, "mad": 5},
                    latest_deviation=2.0,  # still actively deviating
                ),
            ],
            "new": [],
        }
        html = _build_verification_banner(verification)
        assert "Transient spike" in html
        assert "Active deviation" in html

    def test_improving_not_classified_as_historical(self):
        """Improving metrics should not get historical trigger classification."""
        from evolution.report_generator import _build_verification_banner
        verification = {
            "resolved": [],
            "persisting": [self._persisting(
                was_deviation=4.0, now_deviation=2.0, improved=True,
                was_value=0.85, current=0.45,
            )],
            "new": [],
        }
        html = _build_verification_banner(verification)
        assert "improving" in html
        assert "Transient" not in html
        assert "Stabilized" not in html
        assert "Active deviation" not in html

    def test_no_latest_deviation_defaults_transient(self):
        """When latest_deviation is missing, treat as returned to normal."""
        from evolution.report_generator import _build_verification_banner
        p = self._persisting()
        p.pop("latest_deviation", None)
        verification = {
            "resolved": [],
            "persisting": [p],
            "new": [],
        }
        html = _build_verification_banner(verification)
        assert "returned to normal" in html
        assert "Transient spike" in html

    def test_shows_observed_values_not_sigma(self):
        """Verify table shows actual values, not raw σ numbers."""
        from evolution.report_generator import _build_verification_banner
        verification = {
            "resolved": [],
            "persisting": [self._persisting(
                family="dependency", metric="dependency_count",
                was_deviation=182.1, now_deviation=182.1,
                current=1613, was_value=1613,
                latest_value=1613,
                normal={"median": 1478, "mean": 1478, "stddev": 10, "mad": 5},
                latest_deviation=0.0,
            )],
            "new": [],
        }
        html = _build_verification_banner(verification)
        assert "1,613" in html  # formatted observed value
        assert "1,478" in html  # baseline value
        assert "182.1" not in html  # raw σ should NOT appear
