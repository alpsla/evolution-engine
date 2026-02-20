"""Unit tests for evo verify residual prompt auto-save and resolution progress."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from evolution.cli import main, _load_investigation_text


def _make_advisory(changes, advisory_id="adv-001", scope="test-repo"):
    """Helper to build an advisory dict."""
    return {
        "advisory_id": advisory_id,
        "scope": scope,
        "changes": changes,
    }


def _make_change(family, metric, deviation):
    """Helper to build a single change entry."""
    return {
        "family": family,
        "metric": metric,
        "current": 42,
        "normal": {"mean": 5},
        "deviation_stddev": deviation,
    }


@pytest.fixture
def repo_dir(tmp_path):
    """Create a minimal repo structure with .evo directories."""
    (tmp_path / ".git").mkdir()
    evo_dir = tmp_path / ".evo"
    phase5 = evo_dir / "phase5"
    phase5.mkdir(parents=True)
    inv_dir = evo_dir / "investigation"
    inv_dir.mkdir(parents=True)
    (inv_dir / "investigation.txt").write_text(
        "## Finding 1\nRisk: High\nRoot cause: large refactor\n"
    )
    return tmp_path


@pytest.fixture
def previous_advisory_file(tmp_path):
    """Write a previous advisory with 3 findings and return the path."""
    advisory = _make_advisory(
        changes=[
            _make_change("git", "files_touched", 14.2),
            _make_change("ci", "run_duration", 19.7),
            _make_change("git", "dispersion", 3.5),
        ],
        advisory_id="prev-001",
    )
    prev_path = tmp_path / "previous_advisory.json"
    prev_path.write_text(json.dumps(advisory))
    return prev_path


class TestResidualPromptCreated:
    """Residual prompt file is created when findings persist after verify."""

    def test_residual_file_created_on_persisting_findings(
        self, repo_dir, previous_advisory_file
    ):
        """When some findings persist, residual_prompt.txt should be saved."""
        current_advisory = _make_advisory(
            changes=[
                _make_change("git", "files_touched", 10.0),
                _make_change("ci", "run_duration", 15.0),
            ],
            advisory_id="curr-001",
        )

        verify_result = {
            "status": "verified",
            "verification_text": "Fix Verification Report",
            "advisory": current_advisory,
            "verification": {
                "summary": {
                    "total_before": 3,
                    "resolved": 1,
                    "persisting": 2,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [{"family": "git", "metric": "dispersion"}],
                "persisting": [
                    {"family": "git", "metric": "files_touched"},
                    {"family": "ci", "metric": "run_duration"},
                ],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5, \
             patch("evolution.fixer.Fixer") as mock_fixer_cls:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_engine._load_previous_advisory.return_value = _make_advisory(
                changes=[
                    _make_change("git", "files_touched", 14.2),
                    _make_change("ci", "run_duration", 19.7),
                    _make_change("git", "dispersion", 3.5),
                ],
                advisory_id="prev-001",
            )
            mock_p5.return_value = mock_engine

            mock_fixer = MagicMock()
            mock_fixer._build_residual_prompt.return_value = (
                "## What's Still Broken\n- git / files_touched\n- ci / run_duration"
            )
            mock_fixer_cls.return_value = mock_fixer

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            residual_path = repo_dir / ".evo" / "phase5" / "residual_prompt.txt"
            assert residual_path.exists()
            content = residual_path.read_text()
            assert "Still Broken" in content

    def test_residual_file_contains_prompt_content(
        self, repo_dir, previous_advisory_file
    ):
        """The saved residual file should contain the full prompt from Fixer."""
        current_advisory = _make_advisory(
            changes=[_make_change("ci", "run_duration", 15.0)],
            advisory_id="curr-002",
        )

        verify_result = {
            "status": "verified",
            "verification_text": "Fix Verification Report",
            "advisory": current_advisory,
            "verification": {
                "summary": {
                    "total_before": 2,
                    "resolved": 1,
                    "persisting": 1,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [{"family": "ci", "metric": "run_duration"}],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        expected_prompt = (
            "This is an ITERATION of a fix loop.\n"
            "## What's Still Broken\n"
            "- ci / run_duration: deviation 19.7 -> 15.0\n"
            "Focus ONLY on the still broken items."
        )

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5, \
             patch("evolution.fixer.Fixer") as mock_fixer_cls:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_engine._load_previous_advisory.return_value = _make_advisory(
                changes=[
                    _make_change("git", "files_touched", 14.2),
                    _make_change("ci", "run_duration", 19.7),
                ],
                advisory_id="prev-002",
            )
            mock_p5.return_value = mock_engine

            mock_fixer = MagicMock()
            mock_fixer._build_residual_prompt.return_value = expected_prompt
            mock_fixer_cls.return_value = mock_fixer

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            residual_path = repo_dir / ".evo" / "phase5" / "residual_prompt.txt"
            content = residual_path.read_text()
            assert content == expected_prompt


class TestNoResidualWhenAllClear:
    """Residual prompt file is NOT created when all findings are resolved."""

    def test_no_residual_file_when_all_resolved(
        self, repo_dir, previous_advisory_file
    ):
        """When all findings resolve, no residual_prompt.txt should be written."""
        current_advisory = _make_advisory(
            changes=[],
            advisory_id="curr-clear",
        )

        verify_result = {
            "status": "verified",
            "verification_text": "ALL ISSUES RESOLVED. No new issues detected.",
            "advisory": current_advisory,
            "verification": {
                "summary": {
                    "total_before": 3,
                    "resolved": 3,
                    "persisting": 0,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [
                    {"family": "git", "metric": "files_touched"},
                    {"family": "ci", "metric": "run_duration"},
                    {"family": "git", "metric": "dispersion"},
                ],
                "persisting": [],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_p5.return_value = mock_engine

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            residual_path = repo_dir / ".evo" / "phase5" / "residual_prompt.txt"
            assert not residual_path.exists()
            assert "All findings resolved" in result.output

    def test_success_message_on_all_clear(
        self, repo_dir, previous_advisory_file
    ):
        """The success message should be printed when everything is resolved."""
        verify_result = {
            "status": "verified",
            "verification_text": "ALL ISSUES RESOLVED.",
            "advisory": _make_advisory(changes=[], advisory_id="curr-clear"),
            "verification": {
                "summary": {
                    "total_before": 2,
                    "resolved": 2,
                    "persisting": 0,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_p5.return_value = mock_engine

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            assert "no residual prompt needed" in result.output


class TestResolutionProgress:
    """Resolution progress percentage is calculated correctly."""

    def test_progress_67_percent(self, repo_dir, previous_advisory_file):
        """2 resolved out of 3 total = 66%."""
        verify_result = {
            "status": "verified",
            "verification_text": "Fix Verification Report",
            "advisory": _make_advisory(
                changes=[_make_change("ci", "run_duration", 15.0)],
                advisory_id="curr-prog",
            ),
            "verification": {
                "summary": {
                    "total_before": 3,
                    "resolved": 2,
                    "persisting": 1,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [{"family": "ci", "metric": "run_duration"}],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5, \
             patch("evolution.fixer.Fixer") as mock_fixer_cls:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_engine._load_previous_advisory.return_value = _make_advisory(
                changes=[
                    _make_change("git", "files_touched", 14.2),
                    _make_change("ci", "run_duration", 19.7),
                    _make_change("git", "dispersion", 3.5),
                ],
            )
            mock_p5.return_value = mock_engine

            mock_fixer = MagicMock()
            mock_fixer._build_residual_prompt.return_value = "residual"
            mock_fixer_cls.return_value = mock_fixer

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            assert "Resolved: 2 of 3 (66%)" in result.output

    def test_progress_50_percent(self, repo_dir, previous_advisory_file):
        """1 resolved out of 2 total = 50%."""
        verify_result = {
            "status": "verified",
            "verification_text": "Fix Verification Report",
            "advisory": _make_advisory(
                changes=[_make_change("ci", "run_duration", 15.0)],
                advisory_id="curr-half",
            ),
            "verification": {
                "summary": {
                    "total_before": 2,
                    "resolved": 1,
                    "persisting": 1,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [{"family": "ci", "metric": "run_duration"}],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5, \
             patch("evolution.fixer.Fixer") as mock_fixer_cls:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_engine._load_previous_advisory.return_value = _make_advisory(
                changes=[
                    _make_change("git", "files_touched", 14.2),
                    _make_change("ci", "run_duration", 19.7),
                ],
            )
            mock_p5.return_value = mock_engine

            mock_fixer = MagicMock()
            mock_fixer._build_residual_prompt.return_value = "residual"
            mock_fixer_cls.return_value = mock_fixer

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            assert "Resolved: 1 of 2 (50%)" in result.output

    def test_progress_0_percent_all_persist(self, repo_dir, previous_advisory_file):
        """0 resolved out of 3 total = 0%."""
        verify_result = {
            "status": "verified",
            "verification_text": "Fix Verification Report",
            "advisory": _make_advisory(
                changes=[
                    _make_change("git", "files_touched", 14.0),
                    _make_change("ci", "run_duration", 19.0),
                    _make_change("git", "dispersion", 3.0),
                ],
                advisory_id="curr-zero",
            ),
            "verification": {
                "summary": {
                    "total_before": 3,
                    "resolved": 0,
                    "persisting": 3,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [
                    {"family": "git", "metric": "files_touched"},
                    {"family": "ci", "metric": "run_duration"},
                    {"family": "git", "metric": "dispersion"},
                ],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5, \
             patch("evolution.fixer.Fixer") as mock_fixer_cls:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_engine._load_previous_advisory.return_value = _make_advisory(
                changes=[
                    _make_change("git", "files_touched", 14.2),
                    _make_change("ci", "run_duration", 19.7),
                    _make_change("git", "dispersion", 3.5),
                ],
            )
            mock_p5.return_value = mock_engine

            mock_fixer = MagicMock()
            mock_fixer._build_residual_prompt.return_value = "residual"
            mock_fixer_cls.return_value = mock_fixer

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            assert "Resolved: 0 of 3 (0%)" in result.output

    def test_new_findings_count_in_remaining(self, repo_dir, previous_advisory_file):
        """New findings should count as remaining (not resolved)."""
        verify_result = {
            "status": "verified",
            "verification_text": "Fix Verification Report",
            "advisory": _make_advisory(
                changes=[
                    _make_change("ci", "run_duration", 15.0),
                    _make_change("dependency", "dependency_count", 5.0),
                ],
                advisory_id="curr-new",
            ),
            "verification": {
                "summary": {
                    "total_before": 3,
                    "resolved": 2,
                    "persisting": 1,
                    "new": 1,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [{"family": "ci", "metric": "run_duration"}],
                "new": [{"family": "dependency", "metric": "dependency_count"}],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5, \
             patch("evolution.fixer.Fixer") as mock_fixer_cls:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_engine._load_previous_advisory.return_value = _make_advisory(
                changes=[
                    _make_change("git", "files_touched", 14.2),
                    _make_change("ci", "run_duration", 19.7),
                    _make_change("git", "dispersion", 3.5),
                ],
            )
            mock_p5.return_value = mock_engine

            mock_fixer = MagicMock()
            mock_fixer._build_residual_prompt.return_value = "residual"
            mock_fixer_cls.return_value = mock_fixer

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            # 2 remaining (1 persisting + 1 new) means residual prompt is saved
            assert "Residual prompt saved to" in result.output
            assert "Copy to your AI tool" in result.output


class TestResidualPromptMessages:
    """Verify the correct CLI messages are printed."""

    def test_residual_prompt_saved_message(self, repo_dir, previous_advisory_file):
        """The path message should appear when residual prompt is saved."""
        verify_result = {
            "status": "verified",
            "verification_text": "Report",
            "advisory": _make_advisory(
                changes=[_make_change("git", "files_touched", 10.0)],
            ),
            "verification": {
                "summary": {
                    "total_before": 1,
                    "resolved": 0,
                    "persisting": 1,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [{"family": "git", "metric": "files_touched"}],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5, \
             patch("evolution.fixer.Fixer") as mock_fixer_cls:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_engine._load_previous_advisory.return_value = _make_advisory(
                changes=[_make_change("git", "files_touched", 14.2)],
            )
            mock_p5.return_value = mock_engine

            mock_fixer = MagicMock()
            mock_fixer._build_residual_prompt.return_value = "prompt content"
            mock_fixer_cls.return_value = mock_fixer

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            assert "Residual prompt saved to" in result.output
            assert "residual_prompt.txt" in result.output
            assert "Copy to your AI tool to continue fixing." in result.output

    def test_non_verified_status_no_residual(self, repo_dir, previous_advisory_file):
        """When status is not 'verified', no residual logic runs."""
        verify_result = {
            "status": "no_current_data",
            "message": "No significant changes detected.",
            "verification": {
                "resolved": [],
                "persisting": [],
                "new": [],
                "regressions": [],
            },
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_p5.return_value = mock_engine

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir)],
            )

            assert result.exit_code == 0
            residual_path = repo_dir / ".evo" / "phase5" / "residual_prompt.txt"
            assert not residual_path.exists()
            assert "no_current_data" in result.output


class TestVerifyQuietFlag:
    """Test --quiet flag suppresses output and writes verification JSON."""

    def test_quiet_no_output_all_resolved(self, repo_dir, previous_advisory_file):
        """--quiet should produce no output when all issues resolved."""
        verify_result = {
            "status": "verified",
            "verification_text": "ALL ISSUES RESOLVED.",
            "advisory": _make_advisory(changes=[], advisory_id="curr-clear"),
            "verification": {
                "summary": {
                    "total_before": 2,
                    "resolved": 2,
                    "persisting": 0,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_p5.return_value = mock_engine

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir), "--quiet"],
            )

            assert result.exit_code == 0
            assert result.output == ""

    def test_quiet_exit_code_1_when_issues_persist(self, repo_dir, previous_advisory_file):
        """--quiet should exit with code 1 when issues still persist."""
        verify_result = {
            "status": "verified",
            "verification_text": "Report",
            "advisory": _make_advisory(
                changes=[_make_change("git", "files_touched", 10.0)],
            ),
            "verification": {
                "summary": {
                    "total_before": 2,
                    "resolved": 1,
                    "persisting": 1,
                    "new": 0,
                    "regressions": 0,
                },
                "resolved": [],
                "persisting": [{"family": "git", "metric": "files_touched"}],
                "new": [],
                "regressions": [],
            },
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_p5.return_value = mock_engine

            result = runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir), "--quiet"],
            )

            assert result.exit_code == 1
            assert result.output == ""

    def test_quiet_writes_verification_json(self, repo_dir, previous_advisory_file):
        """--quiet should still write verification.json to disk."""
        verification_data = {
            "summary": {
                "total_before": 1,
                "resolved": 1,
                "persisting": 0,
                "new": 0,
                "regressions": 0,
            },
            "resolved": [],
            "persisting": [],
            "new": [],
            "regressions": [],
        }
        verify_result = {
            "status": "verified",
            "verification_text": "ALL CLEAR",
            "advisory": _make_advisory(changes=[]),
            "verification": verification_data,
            "formats": {},
        }

        runner = CliRunner()
        with patch("evolution.phase5_engine.Phase5Engine") as mock_p5:
            mock_engine = MagicMock()
            mock_engine.verify.return_value = verify_result
            mock_p5.return_value = mock_engine

            runner.invoke(
                main,
                ["verify", str(previous_advisory_file), "--path", str(repo_dir), "--quiet"],
            )

            vf_path = repo_dir / ".evo" / "phase5" / "verification.json"
            assert vf_path.exists()
            data = json.loads(vf_path.read_text())
            assert data["summary"]["resolved"] == 1


class TestLoadInvestigationText:
    """Test the _load_investigation_text helper."""

    def test_loads_existing_investigation(self, tmp_path):
        """Should read investigation.txt when it exists."""
        evo_dir = tmp_path / ".evo"
        inv_dir = evo_dir / "investigation"
        inv_dir.mkdir(parents=True)
        (inv_dir / "investigation.txt").write_text("Finding: high dispersion")

        text = _load_investigation_text(evo_dir)
        assert text == "Finding: high dispersion"

    def test_fallback_when_no_investigation(self, tmp_path):
        """Should return fallback text when no investigation file exists."""
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir(parents=True)

        text = _load_investigation_text(evo_dir)
        assert "no investigation report" in text
