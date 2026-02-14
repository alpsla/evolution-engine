"""
Unit tests for commit watcher (evolution/watcher.py).

Tests cover git helpers, threshold checking, daemon status,
and commit detection — without forking or spawning daemons.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from evolution.watcher import CommitWatcher, SEVERITY_LEVELS


# ─── Fixtures ───


@pytest.fixture
def watcher(tmp_path):
    """Create a CommitWatcher with a temp repo path."""
    return CommitWatcher(
        repo_path=str(tmp_path),
        evo_dir=str(tmp_path / ".evo"),
        interval=1,
        min_severity="concern",
    )


# ─── TestGetCurrentHead ───


class TestGetCurrentHead:
    """Test _get_current_head() — mock subprocess, verify SHA returned."""

    def test_returns_sha(self, watcher):
        sha = "abc123def456789012345678901234567890abcd"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = sha + "\n"

        with patch("evolution.watcher.subprocess.run", return_value=mock_result) as mock_run:
            result = watcher._get_current_head()

        assert result == sha
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "HEAD"],
            cwd=str(watcher.repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_strips_whitespace(self, watcher):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  abc123  \n"

        with patch("evolution.watcher.subprocess.run", return_value=mock_result):
            assert watcher._get_current_head() == "abc123"

    def test_raises_on_failure(self, watcher):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: not a git repository"

        with patch("evolution.watcher.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="git rev-parse HEAD failed"):
                watcher._get_current_head()


# ─── TestGetCurrentBranch ───


class TestGetCurrentBranch:
    """Test _get_current_branch() — mock subprocess, verify branch returned."""

    def test_returns_branch_name(self, watcher):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "main\n"

        with patch("evolution.watcher.subprocess.run", return_value=mock_result) as mock_run:
            result = watcher._get_current_branch()

        assert result == "main"
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(watcher.repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_feature_branch(self, watcher):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "feature/add-watcher\n"

        with patch("evolution.watcher.subprocess.run", return_value=mock_result):
            assert watcher._get_current_branch() == "feature/add-watcher"

    def test_raises_on_failure(self, watcher):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"

        with patch("evolution.watcher.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="git rev-parse --abbrev-ref HEAD failed"):
                watcher._get_current_branch()


# ─── TestCheckThreshold ───


class TestCheckThreshold:
    """Test _check_threshold() with various advisory levels and severity settings."""

    def _make_advisory(self, level):
        """Helper to create a result dict with a given status level."""
        return {
            "status": "complete",
            "advisory": {
                "status": {"level": level, "label": level.replace("_", " ").title()},
                "significant_changes": 1,
            },
        }

    def test_action_required_meets_critical(self, watcher):
        watcher.min_severity = "critical"
        assert watcher._check_threshold(self._make_advisory("action_required")) is True

    def test_needs_attention_does_not_meet_critical(self, watcher):
        watcher.min_severity = "critical"
        assert watcher._check_threshold(self._make_advisory("needs_attention")) is False

    def test_needs_attention_meets_concern(self, watcher):
        watcher.min_severity = "concern"
        assert watcher._check_threshold(self._make_advisory("needs_attention")) is True

    def test_all_clear_does_not_meet_concern(self, watcher):
        watcher.min_severity = "concern"
        assert watcher._check_threshold(self._make_advisory("all_clear")) is False

    def test_worth_monitoring_meets_watch(self, watcher):
        watcher.min_severity = "watch"
        assert watcher._check_threshold(self._make_advisory("worth_monitoring")) is True

    def test_all_clear_meets_info(self, watcher):
        watcher.min_severity = "info"
        assert watcher._check_threshold(self._make_advisory("all_clear")) is True

    def test_action_required_meets_all_thresholds(self, watcher):
        advisory = self._make_advisory("action_required")
        for sev in SEVERITY_LEVELS:
            watcher.min_severity = sev
            assert watcher._check_threshold(advisory) is True

    def test_empty_advisory_returns_false_for_concern(self, watcher):
        watcher.min_severity = "concern"
        assert watcher._check_threshold({}) is False

    def test_missing_status_defaults_to_all_clear(self, watcher):
        watcher.min_severity = "watch"
        result = {"advisory": {"significant_changes": 0}}
        assert watcher._check_threshold(result) is False


# ─── TestDaemonStatus ───


class TestDaemonStatus:
    """Test daemon_status() with no PID file, stale PID, and valid PID."""

    def test_no_pid_file(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        result = CommitWatcher.daemon_status(str(tmp_path), str(evo_dir))
        assert result == {"running": False, "pid": None}

    def test_stale_pid_file(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        pid_file = evo_dir / "watch.pid"
        pid_file.write_text("99999999")  # Very likely not running

        with patch("os.kill", side_effect=ProcessLookupError):
            result = CommitWatcher.daemon_status(str(tmp_path), str(evo_dir))

        assert result == {"running": False, "pid": None}

    def test_valid_pid_file(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        pid_file = evo_dir / "watch.pid"
        pid_file.write_text("12345")

        with patch("os.kill") as mock_kill:
            mock_kill.return_value = None  # os.kill(pid, 0) succeeds
            result = CommitWatcher.daemon_status(str(tmp_path), str(evo_dir))

        assert result == {"running": True, "pid": 12345}
        mock_kill.assert_called_once_with(12345, 0)

    def test_invalid_pid_content(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        pid_file = evo_dir / "watch.pid"
        pid_file.write_text("not-a-number")

        result = CommitWatcher.daemon_status(str(tmp_path), str(evo_dir))
        assert result == {"running": False, "pid": None}

    def test_permission_error_assumes_running(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        pid_file = evo_dir / "watch.pid"
        pid_file.write_text("1")

        with patch("os.kill", side_effect=PermissionError):
            result = CommitWatcher.daemon_status(str(tmp_path), str(evo_dir))

        assert result == {"running": True, "pid": 1}

    def test_default_evo_dir(self, tmp_path):
        """daemon_status uses repo_path/.evo when evo_dir is None."""
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        # No PID file
        result = CommitWatcher.daemon_status(str(tmp_path))
        assert result == {"running": False, "pid": None}


# ─── TestStopDaemon ───


class TestStopDaemon:
    """Test stop_daemon() class method."""

    def test_no_pid_file(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        result = CommitWatcher.stop_daemon(str(tmp_path), str(evo_dir))
        assert result["ok"] is False
        assert "No PID file" in result["error"]

    def test_stale_pid(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        pid_file = evo_dir / "watch.pid"
        pid_file.write_text("99999999")

        with patch("os.kill") as mock_kill:
            # First call: os.kill(pid, 0) → ProcessLookupError
            mock_kill.side_effect = ProcessLookupError
            result = CommitWatcher.stop_daemon(str(tmp_path), str(evo_dir))

        assert result["ok"] is False
        assert "not running" in result["error"]
        # PID file should be cleaned up
        assert not pid_file.exists()

    def test_successful_stop(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        pid_file = evo_dir / "watch.pid"
        pid_file.write_text("12345")

        call_count = 0

        def mock_kill_side_effect(pid, sig):
            nonlocal call_count
            call_count += 1
            if sig == 0 and call_count <= 1:
                return None  # Process is running on first check
            if sig == 15:  # SIGTERM
                return None
            raise ProcessLookupError  # Process exited after SIGTERM

        with patch("os.kill", side_effect=mock_kill_side_effect):
            with patch("time.sleep"):
                result = CommitWatcher.stop_daemon(str(tmp_path), str(evo_dir))

        assert result["ok"] is True


# ─── TestRunDetection ───


class TestRunDetection:
    """Test that run() detects HEAD changes and runs analysis."""

    def test_detects_new_commit(self, watcher):
        """run() should detect when HEAD changes and trigger analysis."""
        sha_sequence = iter([
            "aaa111",  # Initial HEAD
            "aaa111",  # First poll — no change
            "bbb222",  # Second poll — new commit
        ])

        analysis_result = {
            "status": "complete",
            "advisory_status": "complete",
            "advisory": {
                "status": {"level": "all_clear", "label": "All Clear"},
                "significant_changes": 0,
            },
        }

        with (
            patch.object(watcher, "_get_current_head", side_effect=lambda: next(sha_sequence)),
            patch.object(watcher, "_get_current_branch", return_value="main"),
            patch.object(watcher, "_run_analysis", return_value=analysis_result) as mock_analysis,
            patch("time.sleep", side_effect=[None, None, KeyboardInterrupt]),
            patch("builtins.print"),
        ):
            stats = watcher.run()

        assert stats["commits_seen"] == 1
        assert stats["analyses_run"] == 1
        mock_analysis.assert_called_once()

    def test_triggers_callback_when_threshold_met(self, watcher):
        """run() should call callback when advisory meets threshold."""
        callback = MagicMock()
        watcher.callback = callback
        watcher.min_severity = "concern"

        sha_sequence = iter([
            "aaa111",  # Initial HEAD
            "bbb222",  # New commit
        ])

        analysis_result = {
            "status": "complete",
            "advisory_status": "complete",
            "advisory": {
                "status": {"level": "action_required", "label": "Action Required"},
                "significant_changes": 3,
            },
        }

        with (
            patch.object(watcher, "_get_current_head", side_effect=lambda: next(sha_sequence)),
            patch.object(watcher, "_get_current_branch", return_value="main"),
            patch.object(watcher, "_run_analysis", return_value=analysis_result),
            patch("time.sleep", side_effect=[None, KeyboardInterrupt]),
            patch("builtins.print"),
        ):
            stats = watcher.run()

        assert stats["alerts_triggered"] == 1
        callback.assert_called_once_with(analysis_result["advisory"])

    def test_no_callback_when_below_threshold(self, watcher):
        """run() should not call callback when advisory is below threshold."""
        callback = MagicMock()
        watcher.callback = callback
        watcher.min_severity = "critical"

        sha_sequence = iter([
            "aaa111",
            "bbb222",
        ])

        analysis_result = {
            "status": "complete",
            "advisory_status": "complete",
            "advisory": {
                "status": {"level": "all_clear", "label": "All Clear"},
                "significant_changes": 0,
            },
        }

        with (
            patch.object(watcher, "_get_current_head", side_effect=lambda: next(sha_sequence)),
            patch.object(watcher, "_get_current_branch", return_value="main"),
            patch.object(watcher, "_run_analysis", return_value=analysis_result),
            patch("time.sleep", side_effect=[None, KeyboardInterrupt]),
            patch("builtins.print"),
        ):
            stats = watcher.run()

        assert stats["alerts_triggered"] == 0
        callback.assert_not_called()

    def test_handles_analysis_failure(self, watcher):
        """run() should continue watching after analysis failure."""
        sha_sequence = iter([
            "aaa111",
            "bbb222",  # Commit 1 — analysis fails
            "ccc333",  # Commit 2 — analysis succeeds
        ])

        analysis_results = iter([
            RuntimeError("orchestrator exploded"),
            {
                "status": "complete",
                "advisory_status": "complete",
                "advisory": {
                    "status": {"level": "all_clear", "label": "All Clear"},
                    "significant_changes": 0,
                },
            },
        ])

        def run_analysis_side_effect():
            result = next(analysis_results)
            if isinstance(result, Exception):
                raise result
            return result

        with (
            patch.object(watcher, "_get_current_head", side_effect=lambda: next(sha_sequence)),
            patch.object(watcher, "_get_current_branch", return_value="main"),
            patch.object(watcher, "_run_analysis", side_effect=run_analysis_side_effect),
            patch("time.sleep", side_effect=[None, None, KeyboardInterrupt]),
            patch("builtins.print"),
        ):
            stats = watcher.run()

        assert stats["commits_seen"] == 2
        assert stats["analyses_run"] == 1  # Only the second succeeded

    def test_returns_stats_on_keyboard_interrupt(self, watcher):
        """run() should return stats dict when interrupted."""
        with (
            patch.object(watcher, "_get_current_head", return_value="aaa111"),
            patch.object(watcher, "_get_current_branch", return_value="main"),
            patch("time.sleep", side_effect=KeyboardInterrupt),
            patch("builtins.print"),
        ):
            stats = watcher.run()

        assert isinstance(stats, dict)
        assert stats == {"commits_seen": 0, "analyses_run": 0, "alerts_triggered": 0}

    def test_skips_when_head_fails(self, watcher):
        """run() should skip poll when _get_current_head raises."""
        call_count = 0

        def head_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "aaa111"  # Initial HEAD
            if call_count == 2:
                raise RuntimeError("git failed")  # Poll failure
            return "aaa111"  # Normal again (but same SHA)

        with (
            patch.object(watcher, "_get_current_head", side_effect=head_side_effect),
            patch.object(watcher, "_get_current_branch", return_value="main"),
            patch("time.sleep", side_effect=[None, None, KeyboardInterrupt]),
            patch("builtins.print"),
        ):
            stats = watcher.run()

        assert stats["commits_seen"] == 0


# ─── TestConstructor ───


class TestConstructor:
    """Test CommitWatcher constructor defaults and validation."""

    def test_default_evo_dir(self, tmp_path):
        w = CommitWatcher(repo_path=str(tmp_path))
        assert w.evo_dir == tmp_path.resolve() / ".evo"

    def test_custom_evo_dir(self, tmp_path):
        custom = tmp_path / "custom_evo"
        w = CommitWatcher(repo_path=str(tmp_path), evo_dir=str(custom))
        assert w.evo_dir == custom.resolve()

    def test_default_interval(self, tmp_path):
        w = CommitWatcher(repo_path=str(tmp_path))
        assert w.interval == 10

    def test_minimum_interval(self, tmp_path):
        w = CommitWatcher(repo_path=str(tmp_path), interval=0)
        assert w.interval == 1

    def test_invalid_severity_defaults_to_concern(self, tmp_path):
        w = CommitWatcher(repo_path=str(tmp_path), min_severity="bogus")
        assert w.min_severity == "concern"

    def test_valid_severity(self, tmp_path):
        for sev in SEVERITY_LEVELS:
            w = CommitWatcher(repo_path=str(tmp_path), min_severity=sev)
            assert w.min_severity == sev

    def test_callback_stored(self, tmp_path):
        cb = lambda x: None
        w = CommitWatcher(repo_path=str(tmp_path), callback=cb)
        assert w.callback is cb
