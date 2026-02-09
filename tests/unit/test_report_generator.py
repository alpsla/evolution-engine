"""Unit tests for the HTML report generator."""

import json
from pathlib import Path

import pytest

from evolution.report_generator import generate_report, _esc, _fmt_num, _format_date


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
        assert "Pattern Recognition" in html
        assert "Matched" in html

    def test_contains_evidence(self, advisory_dir):
        html = generate_report(advisory_dir)
        assert "a1b2c3" in html
        assert "Fix the widget parser" in html
        assert "src/parser.py" in html

    def test_contains_timeline(self, advisory_dir):
        html = generate_report(advisory_dir)
        assert "Timeline" in html

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
        assert "No evidence collected" in html

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
        assert "No significant changes detected" in html


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
        assert _format_date("2026-02-09T12:30:00Z") == "2026-02-09 12:30"
        assert _format_date("") == ""
        assert _format_date("not-a-date") == "not-a-date"
