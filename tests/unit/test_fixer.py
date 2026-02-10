"""Unit tests for the fixer module (fix-verify loop)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from evolution.agents.base import AgentResult
from evolution.fixer import FixIteration, FixResult, Fixer


@pytest.fixture
def repo_with_advisory(tmp_path):
    """Create a mock repo with .evo and advisory for fix testing."""
    # Git repo
    (tmp_path / ".git").mkdir()

    # .evo structure
    evo_dir = tmp_path / ".evo"
    phase5 = evo_dir / "phase5"
    phase5.mkdir(parents=True)

    advisory = {
        "advisory_id": "fix-test-001",
        "scope": "test-repo",
        "changes": [
            {"family": "git", "metric": "files_touched", "current": 47,
             "normal": {"mean": 4.5}, "deviation_stddev": 14.2},
            {"family": "ci", "metric": "run_duration", "current": 340,
             "normal": {"mean": 45}, "deviation_stddev": 19.7},
        ],
    }
    (phase5 / "advisory.json").write_text(json.dumps(advisory))
    (phase5 / "investigation_prompt.txt").write_text(
        "Files changed: 47 (10x normal). CI duration: 340s (8x normal)."
    )

    # Investigation report
    inv_dir = evo_dir / "investigation"
    inv_dir.mkdir(parents=True)
    (inv_dir / "investigation.txt").write_text(
        "## Finding 1: files_touched\n"
        "Risk: High\n"
        "Root cause: Auth refactor spans 6 packages\n"
        "Suggested fix: Extract shared test fixtures\n\n"
        "## Finding 2: run_duration\n"
        "Risk: Medium\n"
        "Root cause: 12 new integration tests each spin up a DB\n"
        "Suggested fix: Use shared DB fixture\n"
    )

    return tmp_path, evo_dir


class TestFixIteration:
    def test_all_clear(self):
        it = FixIteration(
            iteration=1,
            agent_response="Fixed everything",
            resolved=3,
            persisting=0,
            new_issues=0,
            regressions=0,
        )
        assert it.all_clear is True

    def test_not_clear_with_persisting(self):
        it = FixIteration(
            iteration=1,
            agent_response="Partially fixed",
            resolved=2,
            persisting=1,
        )
        assert it.all_clear is False

    def test_not_clear_with_regressions(self):
        it = FixIteration(
            iteration=1,
            agent_response="Fixed but broke something",
            resolved=3,
            regressions=1,
        )
        assert it.all_clear is False

    def test_to_dict(self):
        it = FixIteration(
            iteration=2,
            agent_response="done",
            resolved=1,
            persisting=1,
        )
        d = it.to_dict()
        assert d["iteration"] == 2
        assert d["resolved"] == 1
        assert d["all_clear"] is False


class TestFixResult:
    def test_all_clear_result(self):
        r = FixResult(
            status="all_clear",
            iterations=[FixIteration(1, "done", resolved=3)],
            branch="evo/fix-test",
            total_resolved=3,
            total_remaining=0,
        )
        d = r.to_dict()
        assert d["status"] == "all_clear"
        assert d["total_resolved"] == 3
        assert d["total_remaining"] == 0
        assert d["branch"] == "evo/fix-test"

    def test_dry_run_result(self):
        r = FixResult(
            status="dry_run",
            iterations=[FixIteration(0, "preview")],
            dry_run=True,
        )
        assert r.dry_run is True


class TestFixerDryRun:
    def test_dry_run_returns_prompt(self, repo_with_advisory):
        repo_path, evo_dir = repo_with_advisory
        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        result = fixer.run(dry_run=True)

        assert result.status == "dry_run"
        assert result.dry_run is True
        assert len(result.iterations) == 1
        assert "FIX PROMPT" in result.iterations[0].agent_response
        assert "Auth refactor" in result.iterations[0].agent_response

    def test_dry_run_no_investigation(self, tmp_path):
        """Dry run with only advisory prompt (no investigation report)."""
        evo_dir = tmp_path / ".evo"
        phase5 = evo_dir / "phase5"
        phase5.mkdir(parents=True)

        (phase5 / "advisory.json").write_text(json.dumps({"advisory_id": "x"}))
        (phase5 / "investigation_prompt.txt").write_text("Some advisory data")

        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)
        result = fixer.run(dry_run=True)

        assert result.status == "dry_run"
        assert "Some advisory data" in result.iterations[0].agent_response


class TestFixerLoop:
    def test_all_clear_after_one_iteration(self, repo_with_advisory):
        """Agent fixes everything in one go."""
        repo_path, evo_dir = repo_with_advisory

        mock_agent = MagicMock()
        mock_agent.name = "mock-cli"
        mock_agent.can_edit_files = True
        mock_agent.complete_with_files.return_value = AgentResult(
            text="Applied fixes to auth module",
            success=True,
        )

        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        # Mock git branch creation
        with patch("subprocess.run") as mock_git, \
             patch.object(fixer, "_verify") as mock_verify:

            mock_git.return_value = MagicMock(returncode=0)
            mock_verify.return_value = {
                "status": "verified",
                "verification": {
                    "summary": {
                        "resolved": 2,
                        "persisting": 0,
                        "new": 0,
                        "regressions": 0,
                    },
                    "resolved": [{"family": "git", "metric": "files_touched"}],
                    "persisting": [],
                    "new": [],
                    "regressions": [],
                },
            }

            result = fixer.run(agent=mock_agent, max_iterations=3)

        assert result.status == "all_clear"
        assert len(result.iterations) == 1
        assert result.total_resolved == 2
        assert result.total_remaining == 0

    def test_partial_fix_then_clear(self, repo_with_advisory):
        """Agent needs 2 iterations to fix everything."""
        repo_path, evo_dir = repo_with_advisory

        mock_agent = MagicMock()
        mock_agent.name = "mock-cli"
        mock_agent.can_edit_files = True
        mock_agent.complete_with_files.return_value = AgentResult(
            text="Applied fixes", success=True,
        )

        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        verify_responses = [
            # Iteration 1: partial fix
            {
                "status": "verified",
                "verification": {
                    "summary": {"resolved": 1, "persisting": 1, "new": 0, "regressions": 0},
                    "resolved": [{"family": "git", "metric": "files_touched"}],
                    "persisting": [{"family": "ci", "metric": "run_duration",
                                    "improved": True, "after_deviation": 5.0}],
                    "new": [],
                    "regressions": [],
                },
            },
            # Iteration 2: all clear
            {
                "status": "verified",
                "verification": {
                    "summary": {"resolved": 2, "persisting": 0, "new": 0, "regressions": 0},
                    "resolved": [],
                    "persisting": [],
                    "new": [],
                    "regressions": [],
                },
            },
        ]

        with patch("subprocess.run") as mock_git, \
             patch.object(fixer, "_verify", side_effect=verify_responses):
            mock_git.return_value = MagicMock(returncode=0)
            result = fixer.run(agent=mock_agent, max_iterations=3)

        assert result.status == "all_clear"
        assert len(result.iterations) == 2

    def test_no_progress_stops_loop(self, repo_with_advisory):
        """Loop stops when fix doesn't reduce remaining issues."""
        repo_path, evo_dir = repo_with_advisory

        mock_agent = MagicMock()
        mock_agent.name = "mock-cli"
        mock_agent.can_edit_files = True
        mock_agent.complete_with_files.return_value = AgentResult(
            text="Tried to fix", success=True,
        )

        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        # Same result both times = no progress
        same_verification = {
            "status": "verified",
            "verification": {
                "summary": {"resolved": 0, "persisting": 2, "new": 0, "regressions": 0},
                "resolved": [],
                "persisting": [
                    {"family": "git", "metric": "files_touched", "improved": False},
                    {"family": "ci", "metric": "run_duration", "improved": False},
                ],
                "new": [],
                "regressions": [],
            },
        }

        with patch("subprocess.run") as mock_git, \
             patch.object(fixer, "_verify", return_value=same_verification):
            mock_git.return_value = MagicMock(returncode=0)
            result = fixer.run(agent=mock_agent, max_iterations=5)

        assert result.status == "no_progress"
        assert len(result.iterations) == 2  # tried twice, then stopped

    def test_max_iterations_reached(self, repo_with_advisory):
        """Loop stops at max_iterations even if not resolved."""
        repo_path, evo_dir = repo_with_advisory

        mock_agent = MagicMock()
        mock_agent.name = "mock-cli"
        mock_agent.can_edit_files = True
        mock_agent.complete_with_files.return_value = AgentResult(
            text="Trying...", success=True,
        )

        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        # Each iteration improves by 1, but never reaches 0
        improving = [
            {"status": "verified", "verification": {
                "summary": {"resolved": 1, "persisting": 3, "new": 0, "regressions": 0},
                "resolved": [],
                "persisting": [
                    {"family": "git", "metric": "files_touched", "improved": True, "after_deviation": 8.0},
                    {"family": "ci", "metric": "run_duration", "improved": True, "after_deviation": 10.0},
                    {"family": "git", "metric": "dispersion", "improved": False, "after_deviation": 3.0},
                ],
                "new": [], "regressions": [],
            }},
            {"status": "verified", "verification": {
                "summary": {"resolved": 2, "persisting": 2, "new": 0, "regressions": 0},
                "resolved": [],
                "persisting": [
                    {"family": "ci", "metric": "run_duration", "improved": True, "after_deviation": 5.0},
                    {"family": "git", "metric": "dispersion", "improved": True, "after_deviation": 2.0},
                ],
                "new": [], "regressions": [],
            }},
        ]

        with patch("subprocess.run") as mock_git, \
             patch.object(fixer, "_verify", side_effect=improving):
            mock_git.return_value = MagicMock(returncode=0)
            result = fixer.run(agent=mock_agent, max_iterations=2)

        assert result.status == "max_iterations"
        assert len(result.iterations) == 2

    def test_agent_cannot_edit_files(self, repo_with_advisory):
        """Non-file-editing agent returns error."""
        repo_path, evo_dir = repo_with_advisory

        mock_agent = MagicMock()
        mock_agent.name = "text-only"
        mock_agent.can_edit_files = False

        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)
        result = fixer.run(agent=mock_agent)

        assert result.status == "error"
        assert "cannot edit files" in result.iterations[0].agent_response

    def test_agent_failure_stops_loop(self, repo_with_advisory):
        """Agent error stops the loop immediately."""
        repo_path, evo_dir = repo_with_advisory

        mock_agent = MagicMock()
        mock_agent.name = "mock-cli"
        mock_agent.can_edit_files = True
        mock_agent.complete_with_files.return_value = AgentResult(
            text="", success=False, error="Rate limited",
        )

        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        with patch("subprocess.run") as mock_git:
            mock_git.return_value = MagicMock(returncode=0)
            result = fixer.run(agent=mock_agent)

        assert result.status == "error"


class TestFixerHelpers:
    def test_load_investigation_prefers_report(self, repo_with_advisory):
        """Should prefer investigation report over raw advisory prompt."""
        _, evo_dir = repo_with_advisory
        fixer = Fixer(repo_path="/tmp", evo_dir=evo_dir)
        text = fixer._load_investigation()

        assert "Auth refactor" in text  # from investigation report

    def test_load_investigation_falls_back(self, tmp_path):
        """Falls back to investigation_prompt.txt when no report."""
        evo_dir = tmp_path / ".evo"
        phase5 = evo_dir / "phase5"
        phase5.mkdir(parents=True)
        (phase5 / "investigation_prompt.txt").write_text("Advisory data here")

        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)
        text = fixer._load_investigation()

        assert text == "Advisory data here"

    def test_load_investigation_missing(self, tmp_path):
        """Returns None when nothing is available."""
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir(parents=True)
        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)
        assert fixer._load_investigation() is None

    def test_format_residual(self):
        verification = {
            "verification": {
                "persisting": [
                    {"family": "git", "metric": "files_touched",
                     "improved": True, "after_deviation": 5.0},
                ],
                "new": [
                    {"family": "ci", "metric": "run_failed",
                     "deviation": 3.0},
                ],
                "regressions": [],
                "resolved": [
                    {"family": "git", "metric": "dispersion"},
                ],
            },
        }

        text = Fixer._format_residual(verification)

        assert "STILL FLAGGED" in text
        assert "files_touched" in text
        assert "improving" in text
        assert "NEW ISSUES" in text
        assert "run_failed" in text
        assert "ALREADY RESOLVED: 1" in text

    def test_format_residual_no_issues(self):
        verification = {
            "verification": {
                "persisting": [],
                "new": [],
                "regressions": [],
                "resolved": [{"family": "git"}],
            },
        }
        text = Fixer._format_residual(verification)
        assert "RESIDUAL FINDINGS" in text
        assert "ALREADY RESOLVED: 1" in text
