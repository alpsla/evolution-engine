"""Unit tests for the fixer module (fix-verify loop)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from evolution.agents.base import AgentResult
from evolution.fixer import (
    FixIteration, FixResult, Fixer,
    RESIDUAL_PROMPT_TEMPLATE,
)


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


# ── Residual mode fixtures ──

@pytest.fixture
def repo_with_both_advisories(tmp_path):
    """Create a mock repo with current and previous advisories for residual testing."""
    evo_dir = tmp_path / ".evo"
    phase5 = evo_dir / "phase5"
    phase5.mkdir(parents=True)

    # Previous advisory (before fix attempt): 3 issues
    previous_advisory = {
        "advisory_id": "prev-001",
        "scope": "test-repo",
        "changes": [
            {"family": "git", "metric": "files_touched", "current": 47,
             "normal": {"mean": 4.5}, "deviation_stddev": 14.2},
            {"family": "ci", "metric": "run_duration", "current": 340,
             "normal": {"mean": 45}, "deviation_stddev": 19.7},
            {"family": "git", "metric": "dispersion", "current": 0.95,
             "normal": {"mean": 0.3}, "deviation_stddev": 8.1},
        ],
    }
    (phase5 / "advisory_previous.json").write_text(json.dumps(previous_advisory))

    # Current advisory (after fix attempt): 1 resolved, 1 persisting, 1 new
    current_advisory = {
        "advisory_id": "curr-001",
        "scope": "test-repo",
        "changes": [
            # files_touched resolved (not present) — was in previous
            # run_duration still persisting
            {"family": "ci", "metric": "run_duration", "current": 200,
             "normal": {"mean": 45}, "deviation_stddev": 10.3},
            # dispersion still persisting
            {"family": "git", "metric": "dispersion", "current": 0.8,
             "normal": {"mean": 0.3}, "deviation_stddev": 6.2},
            # new issue not in previous
            {"family": "dep", "metric": "dependency_count", "current": 150,
             "normal": {"mean": 30}, "deviation_stddev": 4.0},
        ],
    }
    (phase5 / "advisory.json").write_text(json.dumps(current_advisory))

    # Investigation report
    inv_dir = evo_dir / "investigation"
    inv_dir.mkdir(parents=True)
    (inv_dir / "investigation.txt").write_text(
        "## Finding 1: files_touched\nRoot cause: Auth refactor\n\n"
        "## Finding 2: run_duration\nRoot cause: DB tests\n\n"
        "## Finding 3: dispersion\nRoot cause: Scattered changes\n"
    )

    return tmp_path, evo_dir


class TestResidualMode:
    """Tests for --residual mode (iteration-aware external prompts)."""

    def test_residual_prompt_no_previous(self, repo_with_advisory):
        """Falls back to normal dry_run when no previous advisory exists."""
        repo_path, evo_dir = repo_with_advisory
        # repo_with_advisory has no advisory_previous.json
        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        result = fixer.run(dry_run=True, residual=True)

        # Should fall back to normal dry_run
        assert result.status == "dry_run"
        assert result.dry_run is True
        assert "FIX PROMPT" in result.iterations[0].agent_response

    def test_residual_prompt_with_resolved(self, repo_with_both_advisories):
        """Items in previous but not current are shown as resolved."""
        repo_path, evo_dir = repo_with_both_advisories
        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        with patch.object(fixer, "_get_recent_changes_context",
                          return_value="(mocked changes)"):
            result = fixer.run(dry_run=True, residual=True)

        assert result.status == "dry_run_residual"
        assert result.dry_run is True

        prompt = result.iterations[0].agent_response
        # git/files_touched was in previous but not current => resolved
        assert "git / files_touched" in prompt
        assert "Already Fixed" in prompt or "was deviation" in prompt

        # Metadata
        assert result.resolved_count == 1  # git/files_touched
        assert result.total_resolved == 1

    def test_residual_prompt_with_persisting(self, repo_with_both_advisories):
        """Items in both current and previous are shown as persisting."""
        repo_path, evo_dir = repo_with_both_advisories
        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        with patch.object(fixer, "_get_recent_changes_context",
                          return_value="(mocked changes)"):
            result = fixer.run(dry_run=True, residual=True)

        prompt = result.iterations[0].agent_response
        # ci/run_duration and git/dispersion are in both => persisting
        assert "ci / run_duration" in prompt
        assert "git / dispersion" in prompt
        # Should show deviation change (before -> after)
        assert "19.7" in prompt or "10.3" in prompt  # previous or current deviation

        assert result.persisting_count == 2

    def test_residual_prompt_with_new_issues(self, repo_with_both_advisories):
        """Items only in current (not in previous) are shown as new issues."""
        repo_path, evo_dir = repo_with_both_advisories
        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        with patch.object(fixer, "_get_recent_changes_context",
                          return_value="(mocked changes)"):
            result = fixer.run(dry_run=True, residual=True)

        prompt = result.iterations[0].agent_response
        # dep/dependency_count is only in current => new
        assert "dep / dependency_count" in prompt
        assert "New Issues" in prompt

        assert result.new_count == 1
        assert result.total_remaining == 3  # 2 persisting + 1 new

    def test_build_residual_prompt_format(self, repo_with_both_advisories):
        """Verify the residual prompt template is filled correctly."""
        repo_path, evo_dir = repo_with_both_advisories
        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        previous_advisory = json.loads(
            (evo_dir / "phase5" / "advisory_previous.json").read_text()
        )
        current_advisory = json.loads(
            (evo_dir / "phase5" / "advisory.json").read_text()
        )

        with patch.object(fixer, "_get_recent_changes_context",
                          return_value="Modified files:\n  auth.py"):
            prompt = fixer._build_residual_prompt(
                current_advisory, previous_advisory,
                "Investigation text here",
            )

        # Check all template sections are present
        assert "ITERATION of a course-correction loop" in prompt
        assert "Already Resolved" in prompt
        assert "Still Drifting" in prompt
        assert "Previous Changes" in prompt
        assert "Original Investigation" in prompt
        assert "Investigation text here" in prompt
        assert "Modified files:" in prompt
        assert "auth.py" in prompt

        # Resolved section has the right item
        assert "git / files_touched" in prompt
        assert "was deviation 14.2" in prompt

        # Persisting section has the right items with before->after deviations
        assert "ci / run_duration: deviation 19.7 -> 10.3" in prompt
        assert "git / dispersion: deviation 8.1 -> 6.2" in prompt

        # New section
        assert "dep / dependency_count: deviation 4.0" in prompt

        # Footer guidance
        assert "don't undo them" in prompt

    def test_save_previous_advisory(self, repo_with_advisory):
        """Verify save_previous_advisory copies advisory.json to advisory_previous.json."""
        repo_path, evo_dir = repo_with_advisory
        fixer = Fixer(repo_path=repo_path, evo_dir=evo_dir)

        previous_path = evo_dir / "phase5" / "advisory_previous.json"
        assert not previous_path.exists()

        result = fixer.save_previous_advisory()

        assert result is True
        assert previous_path.exists()

        # Content should match original advisory
        original = json.loads((evo_dir / "phase5" / "advisory.json").read_text())
        copied = json.loads(previous_path.read_text())
        assert copied == original

    def test_save_previous_advisory_no_current(self, tmp_path):
        """Returns False when no current advisory exists."""
        evo_dir = tmp_path / ".evo"
        phase5 = evo_dir / "phase5"
        phase5.mkdir(parents=True)

        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)
        result = fixer.save_previous_advisory()

        assert result is False

    def test_load_advisory_valid(self, tmp_path):
        """_load_advisory returns parsed dict for valid JSON."""
        path = tmp_path / "test.json"
        data = {"advisory_id": "test", "changes": []}
        path.write_text(json.dumps(data))

        result = Fixer._load_advisory(path)
        assert result == data

    def test_load_advisory_missing(self, tmp_path):
        """_load_advisory returns None for missing file."""
        path = tmp_path / "nonexistent.json"
        result = Fixer._load_advisory(path)
        assert result is None

    def test_load_advisory_invalid_json(self, tmp_path):
        """_load_advisory returns None for invalid JSON."""
        path = tmp_path / "bad.json"
        path.write_text("not valid json {{{")

        result = Fixer._load_advisory(path)
        assert result is None

    def test_residual_deviation_below_threshold(self, tmp_path):
        """Items in both advisories but with deviation < 1.0 are treated as resolved."""
        evo_dir = tmp_path / ".evo"
        phase5 = evo_dir / "phase5"
        phase5.mkdir(parents=True)

        # Previous: one issue with high deviation
        previous = {
            "advisory_id": "prev",
            "changes": [
                {"family": "ci", "metric": "run_duration",
                 "deviation_stddev": 5.0},
            ],
        }
        (phase5 / "advisory_previous.json").write_text(json.dumps(previous))

        # Current: same issue but deviation now below 1.0
        current = {
            "advisory_id": "curr",
            "changes": [
                {"family": "ci", "metric": "run_duration",
                 "deviation_stddev": 0.8},
            ],
        }
        (phase5 / "advisory.json").write_text(json.dumps(current))

        inv_dir = evo_dir / "investigation"
        inv_dir.mkdir(parents=True)
        (inv_dir / "investigation.txt").write_text("CI slow")

        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)

        with patch.object(fixer, "_get_recent_changes_context",
                          return_value="(mocked)"):
            result = fixer.run(dry_run=True, residual=True)

        assert result.status == "dry_run_residual"
        prompt = result.iterations[0].agent_response
        # The item should be in the resolved section since deviation < 1.0
        assert "was deviation 5.0" in prompt
        # Persisting section should say none
        assert "all previous issues resolved" in prompt
