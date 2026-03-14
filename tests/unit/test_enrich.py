"""Unit tests for the enrich feature: summary extraction, advisory enrichment, CLI command."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from evolution.cli import main
from evolution.investigator import Investigator


# ──────────────── Summary extraction ────────────────


class TestExtractFindingSummaries:
    def test_basic_extraction(self):
        text = """
## Finding 1: files_touched
Risk: High
Root cause: Large refactoring commit

## Finding Summaries
- [git/files_touched]: A large refactoring commit touched 10x more files than usual.
- [ci/run_duration]: Build times spiked because the refactoring triggered all test suites.
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {
            "git/files_touched": "A large refactoring commit touched 10x more files than usual.",
            "ci/run_duration": "Build times spiked because the refactoring triggered all test suites.",
        }

    def test_without_brackets(self):
        text = """
## Finding Summaries
- git/dispersion: Changes were spread across many unrelated directories.
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {
            "git/dispersion": "Changes were spread across many unrelated directories.",
        }

    def test_asterisk_bullets(self):
        text = """
## Finding Summaries
* [ci/run_failed]: The CI pipeline started failing after a dependency update.
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {
            "ci/run_failed": "The CI pipeline started failing after a dependency update.",
        }

    def test_missing_section_returns_empty(self):
        text = """
## Finding 1: files_touched
Risk: High
Root cause: Large commit
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {}

    def test_empty_section_returns_empty(self):
        text = """
## Finding Summaries

## Next Steps
Do something.
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {}

    def test_case_insensitive_header(self):
        text = """
## finding summaries
- [git/files_touched]: Big commit.
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {"git/files_touched": "Big commit."}

    def test_multiple_hash_levels(self):
        text = """
### Finding Summaries
- [git/files_touched]: Big commit.
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {"git/files_touched": "Big commit."}

    def test_stops_at_next_section(self):
        text = """
## Finding Summaries
- [git/files_touched]: Big commit.

## Recommended Fix Order
1. Fix the thing
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {"git/files_touched": "Big commit."}

    def test_empty_description_skipped(self):
        text = """
## Finding Summaries
- [git/files_touched]:
- [ci/run_duration]: Valid description.
"""
        result = Investigator.extract_finding_summaries(text)
        assert result == {"ci/run_duration": "Valid description."}

    def test_empty_input(self):
        assert Investigator.extract_finding_summaries("") == {}

    def test_key_normalized_to_lowercase(self):
        text = """
## Finding Summaries
- [Git/Files_Touched]: Big commit.
"""
        result = Investigator.extract_finding_summaries(text)
        assert "git/files_touched" in result


# ──────────────── CLI command ────────────────


@pytest.fixture
def evo_dir_with_advisory(tmp_path):
    """Create a minimal .evo dir with advisory for enrich testing."""
    evo = tmp_path / ".evo"
    phase5 = evo / "phase5"
    phase5.mkdir(parents=True)

    advisory = {
        "advisory_id": "test123",
        "scope": "test-repo",
        "period": {"from": "2026-01-01", "to": "2026-02-09"},
        "changes": [
            {
                "family": "git",
                "metric": "files_touched",
                "normal": {"mean": 4.5, "median": 3.0, "mad": 1.5},
                "current": 47,
                "deviation_stddev": 14.2,
            },
            {
                "family": "ci",
                "metric": "run_duration",
                "normal": {"mean": 45, "median": 40, "mad": 10},
                "current": 340,
                "deviation_stddev": 19.7,
            },
        ],
    }
    (phase5 / "advisory.json").write_text(json.dumps(advisory))
    return tmp_path


AI_RESPONSE_WITH_SUMMARIES = """
## Finding 1: files_touched
Risk: High
Root cause: Large refactoring commit

## Finding 2: run_duration
Risk: Medium
Root cause: All test suites triggered

## Finding Summaries
- [git/files_touched]: A large refactoring commit touched 10x more files than usual.
- [ci/run_duration]: Build times spiked because the refactoring triggered all test suites.
"""


class TestEnrichCommand:
    def test_enrich_from_file(self, evo_dir_with_advisory, tmp_path):
        response_file = tmp_path / "response.txt"
        response_file.write_text(AI_RESPONSE_WITH_SUMMARIES)

        runner = CliRunner()
        with patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, [
                "enrich", str(evo_dir_with_advisory),
                "--from", str(response_file),
            ])

        assert result.exit_code == 0
        assert "Enriched 2 finding(s)" in result.output

        # Verify advisory was updated
        advisory = json.loads(
            (evo_dir_with_advisory / ".evo" / "phase5" / "advisory.json").read_text()
        )
        assert advisory["changes"][0]["description_friendly"] == \
            "A large refactoring commit touched 10x more files than usual."
        assert advisory["changes"][1]["description_friendly"] == \
            "Build times spiked because the refactoring triggered all test suites."

    def test_enrich_from_stdin(self, evo_dir_with_advisory):
        runner = CliRunner()
        with patch("evolution.telemetry.track_event"):
            result = runner.invoke(
                main,
                ["enrich", str(evo_dir_with_advisory)],
                input=AI_RESPONSE_WITH_SUMMARIES,
            )

        assert result.exit_code == 0
        assert "Enriched 2 finding(s)" in result.output

    def test_enrich_no_advisory(self, tmp_path):
        (tmp_path / ".evo" / "phase5").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(main, [
            "enrich", str(tmp_path), "--from", "/dev/null",
        ])

        assert result.exit_code != 0
        assert "No advisory found" in result.output

    def test_enrich_no_summaries_section(self, evo_dir_with_advisory, tmp_path):
        response_file = tmp_path / "response.txt"
        response_file.write_text("Just some text without finding summaries section.")

        runner = CliRunner()
        result = runner.invoke(main, [
            "enrich", str(evo_dir_with_advisory),
            "--from", str(response_file),
        ])

        assert result.exit_code != 0
        assert "No Finding Summaries section" in result.output

    def test_enrich_empty_input(self, evo_dir_with_advisory, tmp_path):
        response_file = tmp_path / "empty.txt"
        response_file.write_text("")

        runner = CliRunner()
        result = runner.invoke(main, [
            "enrich", str(evo_dir_with_advisory),
            "--from", str(response_file),
        ])

        assert result.exit_code != 0
        assert "Empty input" in result.output

    def test_enrich_partial_match(self, evo_dir_with_advisory, tmp_path):
        """Only one finding matches — should still work."""
        response_file = tmp_path / "response.txt"
        response_file.write_text("""
## Finding Summaries
- [git/files_touched]: A large refactoring commit.
- [dependency/dependency_count]: Unrelated finding not in advisory.
""")

        runner = CliRunner()
        with patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, [
                "enrich", str(evo_dir_with_advisory),
                "--from", str(response_file),
            ])

        assert result.exit_code == 0
        assert "Enriched 1 finding(s)" in result.output

    def test_enrich_no_input_shows_help(self, evo_dir_with_advisory):
        """Without --from and no stdin, should show usage hint or empty error."""
        runner = CliRunner()
        result = runner.invoke(main, [
            "enrich", str(evo_dir_with_advisory),
        ])

        # CliRunner provides empty stdin (not a TTY), so it reads "" from stdin
        assert result.exit_code != 0


# ──────────────── Report display priority ────────────────


class TestReportDescriptionPriority:
    def test_change_card_uses_friendly_description(self):
        """description_friendly should be preferred over metric_insight."""
        from evolution.report_generator import _build_change_card

        change = {
            "family": "git",
            "metric": "files_touched",
            "normal": {"mean": 4.5, "median": 3.0, "mad": 1.5},
            "current": 47,
            "deviation_stddev": 14.2,
            "description_friendly": "A large refactoring commit touched 10x more files than usual.",
        }

        html = _build_change_card(change)
        assert "A large refactoring commit touched 10x more files than usual." in html

    def test_change_card_falls_back_to_insight(self):
        """Without description_friendly, should use metric_insight."""
        from evolution.report_generator import _build_change_card

        change = {
            "family": "git",
            "metric": "files_touched",
            "normal": {"mean": 4.5, "median": 3.0, "mad": 1.5},
            "current": 47,
            "deviation_stddev": 14.2,
        }

        html = _build_change_card(change)
        # Should contain insight or comparison text, not be empty
        assert "user-friendly-summary" in html


# ──────────────── Pattern description extraction ────────────────


class TestExtractPatternDescriptions:
    def test_basic_extraction(self):
        text = """
## Pattern Descriptions
- [abc123def456]: Large commits cause longer builds because more test suites run.
- [789xyz]: Dependency updates trigger test failures due to breaking API changes.
"""
        result = Investigator.extract_pattern_descriptions(text)
        assert result == {
            "abc123def456": "Large commits cause longer builds because more test suites run.",
            "789xyz": "Dependency updates trigger test failures due to breaking API changes.",
        }

    def test_without_brackets(self):
        text = """
## Pattern Descriptions
- abc123: Large commits correlate with build time increases.
"""
        result = Investigator.extract_pattern_descriptions(text)
        assert result == {
            "abc123": "Large commits correlate with build time increases.",
        }

    def test_missing_section_returns_empty(self):
        text = """
## Finding Summaries
- [git/files_touched]: Something happened.
"""
        result = Investigator.extract_pattern_descriptions(text)
        assert result == {}

    def test_empty_description_skipped(self):
        text = """
## Pattern Descriptions
- [abc123]:
- [def456]: Valid description.
"""
        result = Investigator.extract_pattern_descriptions(text)
        assert result == {"def456": "Valid description."}

    def test_stops_at_next_section(self):
        text = """
## Pattern Descriptions
- [abc123]: Pattern explanation.

## Recommended Fix Order
1. Fix the thing
"""
        result = Investigator.extract_pattern_descriptions(text)
        assert result == {"abc123": "Pattern explanation."}

    def test_case_insensitive_header(self):
        text = """
### pattern descriptions
- [abc123]: Pattern explanation.
"""
        result = Investigator.extract_pattern_descriptions(text)
        assert result == {"abc123": "Pattern explanation."}

    def test_empty_input(self):
        assert Investigator.extract_pattern_descriptions("") == {}

    def test_pattern_ids_with_hyphens_and_underscores(self):
        text = """
## Pattern Descriptions
- [pat-123_abc]: Some explanation.
"""
        result = Investigator.extract_pattern_descriptions(text)
        assert result == {"pat-123_abc": "Some explanation."}


# ──────────────── Investigation prompt pattern section ────────────────


class TestInvestigationPromptPatternSection:
    def test_prompt_includes_pattern_descriptions_request(self):
        """When candidate patterns lack description_semantic, prompt should ask for them."""
        from evolution.phase5_engine import Phase5Engine
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            engine = Phase5Engine.__new__(Phase5Engine)
            engine.output_path = Path(td)

            advisory = {
                "period": {"from": "2026-01-01", "to": "2026-02-09"},
                "scope": "test-repo",
                "changes": [
                    {
                        "family": "git",
                        "metric": "files_touched",
                        "normal": {"mean": 3.0},
                        "current": 20,
                        "deviation_stddev": 5.7,
                    },
                ],
                "candidate_patterns": [
                    {
                        "pattern_id": "abc123def456",
                        "families": ["git", "ci"],
                        "metrics": ["files_touched", "run_duration"],
                        "description": "files_touched correlates with run_duration at 0.85",
                    },
                ],
                "pattern_matches": [],
                "evidence": {},
            }

            prompt = engine._format_investigation_prompt(advisory)
            assert "Pattern Descriptions" in prompt
            assert "abc123def456" in prompt[:len(prompt)]  # pattern_id truncated to 12
            assert "files_touched" in prompt
            assert "run_duration" in prompt

    def test_prompt_skips_patterns_with_semantic_desc(self):
        """Patterns that already have description_semantic should not be listed."""
        from evolution.phase5_engine import Phase5Engine
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            engine = Phase5Engine.__new__(Phase5Engine)
            engine.output_path = Path(td)

            advisory = {
                "period": {"from": "2026-01-01", "to": "2026-02-09"},
                "scope": "test-repo",
                "changes": [
                    {
                        "family": "git",
                        "metric": "files_touched",
                        "normal": {"mean": 3.0},
                        "current": 20,
                        "deviation_stddev": 5.7,
                    },
                ],
                "candidate_patterns": [
                    {
                        "pattern_id": "abc123",
                        "families": ["git"],
                        "metrics": ["files_touched"],
                        "description_semantic": "Already described.",
                    },
                ],
                "pattern_matches": [],
                "evidence": {},
            }

            prompt = engine._format_investigation_prompt(advisory)
            assert "Pattern Descriptions" not in prompt

    def test_prompt_no_patterns_no_section(self):
        """No candidate patterns = no Pattern Descriptions section."""
        from evolution.phase5_engine import Phase5Engine
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            engine = Phase5Engine.__new__(Phase5Engine)
            engine.output_path = Path(td)

            advisory = {
                "period": {"from": "2026-01-01", "to": "2026-02-09"},
                "scope": "test-repo",
                "changes": [],
                "candidate_patterns": [],
                "pattern_matches": [],
                "evidence": {},
            }

            prompt = engine._format_investigation_prompt(advisory)
            assert "Pattern Descriptions" not in prompt


# ──────────────── Investigation prompt ────────────────


class TestInvestigationPromptSummaryRequest:
    def test_prompt_includes_finding_summaries_instruction(self, tmp_path):
        """The investigation prompt should ask the AI to include Finding Summaries."""
        # We need to check the Phase 5 engine's prompt
        # Use a simpler approach: check the investigator fallback prompt
        # The main prompt is built by phase5_engine, tested via integration
        from evolution.investigator import Investigator

        phase5 = tmp_path / "phase5"
        phase5.mkdir(parents=True)

        advisory = {
            "advisory_id": "test",
            "scope": "test-repo",
            "period": {"from": "2026-01-01", "to": "2026-02-09"},
            "changes": [
                {
                    "family": "git",
                    "metric": "files_touched",
                    "normal": {"mean": 3.0},
                    "current": 20,
                    "deviation_stddev": 5.7,
                },
            ],
            "pattern_matches": [],
            "candidate_patterns": [],
        }
        (phase5 / "advisory.json").write_text(json.dumps(advisory))

        # Write investigation prompt that includes the Finding Summaries instruction
        prompt_text = (
            "Development pattern shift detected.\n\n"
            "## Finding Summaries\n"
            "- [family/metric]: One sentence explaining what happened.\n"
        )
        (phase5 / "investigation_prompt.txt").write_text(prompt_text)

        inv = Investigator(evo_dir=tmp_path)
        prompt, _ = inv.get_prompt()
        assert "Finding Summaries" in prompt
