"""Tests for hook-based loop closure — resolution tracking across commits.

Covers:
- compare_advisories() with various scenarios
- Orchestrator includes resolution info when previous advisory exists
- Hook script includes resolution progress in notification
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.fixer import compare_advisories
from evolution.hooks import _build_hook_script


# ──────────────── compare_advisories ────────────────


class TestCompareAdvisories:
    """Test the compare_advisories function with various scenarios."""

    def test_all_resolved(self):
        """All previous findings are gone in the current advisory."""
        previous = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 19.7},
            ],
        }
        current = {"changes": []}

        result = compare_advisories(current, previous)

        assert len(result["resolved"]) == 2
        assert len(result["persisting"]) == 0
        assert len(result["new"]) == 0
        assert len(result["regressions"]) == 0
        # Check resolved items have correct fields
        families = {r["family"] for r in result["resolved"]}
        assert families == {"git", "ci"}

    def test_all_persisting(self):
        """All findings remain in the current advisory."""
        previous = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 19.7},
            ],
        }
        current = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 10.0},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 15.0},
            ],
        }

        result = compare_advisories(current, previous)

        assert len(result["resolved"]) == 0
        assert len(result["persisting"]) == 2
        assert len(result["new"]) == 0
        assert len(result["regressions"]) == 0
        # Check improvement tracking
        for p in result["persisting"]:
            assert p["improved"] is True  # deviation decreased

    def test_partial_resolution(self):
        """Some findings resolved, some remain."""
        previous = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 19.7},
                {"family": "git", "metric": "dispersion", "deviation_stddev": 8.1},
            ],
        }
        current = {
            "changes": [
                # files_touched resolved (absent)
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 10.3},
                # dispersion still present
                {"family": "git", "metric": "dispersion", "deviation_stddev": 6.2},
            ],
        }

        result = compare_advisories(current, previous)

        assert len(result["resolved"]) == 1
        assert result["resolved"][0]["family"] == "git"
        assert result["resolved"][0]["metric"] == "files_touched"
        assert len(result["persisting"]) == 2
        assert len(result["new"]) == 0

    def test_new_findings(self):
        """Current advisory has findings not in previous (new family)."""
        previous = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
            ],
        }
        current = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "dependency", "metric": "dependency_count", "deviation_stddev": 4.0},
            ],
        }

        result = compare_advisories(current, previous)

        assert len(result["resolved"]) == 0
        assert len(result["persisting"]) == 1
        assert len(result["new"]) == 1
        assert result["new"][0]["family"] == "dependency"

    def test_regressions(self):
        """New findings in a previously-affected family are regressions."""
        previous = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
            ],
        }
        current = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                # New metric in same family = regression
                {"family": "git", "metric": "dispersion", "deviation_stddev": 5.0},
            ],
        }

        result = compare_advisories(current, previous)

        assert len(result["regressions"]) == 1
        assert result["regressions"][0]["metric"] == "dispersion"
        assert len(result["new"]) == 0  # Not new, it's a regression

    def test_empty_advisories(self):
        """Both advisories have no changes."""
        result = compare_advisories({"changes": []}, {"changes": []})
        assert result == {"resolved": [], "persisting": [], "new": [], "regressions": []}

    def test_no_previous(self):
        """Previous has no changes, current has some."""
        previous = {"changes": []}
        current = {
            "changes": [
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 5.0},
            ],
        }

        result = compare_advisories(current, previous)

        assert len(result["resolved"]) == 0
        assert len(result["persisting"]) == 0
        assert len(result["new"]) == 1

    def test_worsening_deviation(self):
        """Persisting finding where deviation increased is not improved."""
        previous = {
            "changes": [
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 5.0},
            ],
        }
        current = {
            "changes": [
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 8.0},
            ],
        }

        result = compare_advisories(current, previous)

        assert len(result["persisting"]) == 1
        assert result["persisting"][0]["improved"] is False
        assert result["persisting"][0]["was_deviation"] == 5.0
        assert result["persisting"][0]["now_deviation"] == 8.0

    def test_missing_changes_key(self):
        """Advisories without 'changes' key should not crash."""
        result = compare_advisories({}, {})
        assert result == {"resolved": [], "persisting": [], "new": [], "regressions": []}

    def test_mixed_scenario(self):
        """Complex scenario: resolved + persisting + new + regression."""
        previous = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 19.7},
                {"family": "git", "metric": "dispersion", "deviation_stddev": 8.1},
            ],
        }
        current = {
            "changes": [
                # files_touched resolved (absent)
                # run_duration persisting (same family)
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 10.3},
                # dispersion resolved (absent)
                # New metric in git family = regression
                {"family": "git", "metric": "cochange_novelty_ratio", "deviation_stddev": 3.5},
                # New finding in new family = new
                {"family": "dependency", "metric": "dependency_count", "deviation_stddev": 4.0},
            ],
        }

        result = compare_advisories(current, previous)

        assert len(result["resolved"]) == 2  # files_touched + dispersion
        assert len(result["persisting"]) == 1  # run_duration
        assert len(result["new"]) == 1  # dependency_count (new family)
        assert len(result["regressions"]) == 1  # cochange_novelty_ratio (git family was in previous)


# ──────────────── Orchestrator resolution tracking ────────────────


class TestOrchestratorResolution:
    """Test that orchestrator includes resolution info when previous advisory exists."""

    def test_resolution_included_when_previous_exists(self, tmp_path):
        """Orchestrator result should contain resolution dict when previous advisory exists."""
        from evolution.orchestrator import Orchestrator

        evo_dir = tmp_path / ".evo"
        phase5_dir = evo_dir / "phase5"
        phase5_dir.mkdir(parents=True)

        # Write a previous advisory
        previous_advisory = {
            "advisory_id": "prev-001",
            "scope": "test-repo",
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 19.7},
            ],
        }
        (phase5_dir / "advisory.json").write_text(json.dumps(previous_advisory))

        orch = Orchestrator.__new__(Orchestrator)
        orch.repo_path = tmp_path
        orch.evo_dir = evo_dir

        # Test _load_previous_advisory
        loaded = orch._load_previous_advisory()
        assert loaded is not None
        assert loaded["advisory_id"] == "prev-001"
        assert len(loaded["changes"]) == 2

    def test_no_resolution_when_no_previous(self, tmp_path):
        """Orchestrator should return None resolution when no previous advisory."""
        from evolution.orchestrator import Orchestrator

        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir(parents=True)

        orch = Orchestrator.__new__(Orchestrator)
        orch.repo_path = tmp_path
        orch.evo_dir = evo_dir

        loaded = orch._load_previous_advisory()
        assert loaded is None

    def test_compute_resolution_all_resolved(self, tmp_path):
        """Resolution dict shows all resolved when current advisory has no changes."""
        from evolution.orchestrator import Orchestrator

        evo_dir = tmp_path / ".evo"
        phase5_dir = evo_dir / "phase5"
        phase5_dir.mkdir(parents=True)

        orch = Orchestrator.__new__(Orchestrator)
        orch.repo_path = tmp_path
        orch.evo_dir = evo_dir

        previous_advisory = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 19.7},
            ],
        }

        current_advisory = {"changes": []}

        p5_result = {
            "status": "complete",
            "advisory": current_advisory,
        }

        resolution = orch._compute_resolution(previous_advisory, p5_result)

        assert resolution is not None
        assert resolution["resolved"] == 2
        assert resolution["persisting"] == 0
        assert resolution["new"] == 0
        assert resolution["regressions"] == 0
        assert resolution["total_before"] == 2

    def test_compute_resolution_partial(self, tmp_path):
        """Resolution dict shows partial progress."""
        from evolution.orchestrator import Orchestrator

        evo_dir = tmp_path / ".evo"
        phase5_dir = evo_dir / "phase5"
        phase5_dir.mkdir(parents=True)

        orch = Orchestrator.__new__(Orchestrator)
        orch.repo_path = tmp_path
        orch.evo_dir = evo_dir

        previous_advisory = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 19.7},
            ],
        }

        current_advisory = {
            "changes": [
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 10.3},
            ],
        }

        p5_result = {
            "status": "complete",
            "advisory": current_advisory,
        }

        resolution = orch._compute_resolution(previous_advisory, p5_result)

        assert resolution is not None
        assert resolution["resolved"] == 1
        assert resolution["persisting"] == 1
        assert resolution["total_before"] == 2

    def test_compute_resolution_none_when_no_previous(self, tmp_path):
        """Returns None when no previous advisory."""
        from evolution.orchestrator import Orchestrator

        orch = Orchestrator.__new__(Orchestrator)
        orch.repo_path = tmp_path
        orch.evo_dir = tmp_path / ".evo"

        p5_result = {"status": "complete", "advisory": {"changes": []}}
        assert orch._compute_resolution(None, p5_result) is None

    def test_compute_resolution_none_when_no_current(self, tmp_path):
        """Returns None when current pipeline has no advisory."""
        from evolution.orchestrator import Orchestrator

        orch = Orchestrator.__new__(Orchestrator)
        orch.repo_path = tmp_path
        orch.evo_dir = tmp_path / ".evo"

        previous = {"changes": [{"family": "git", "metric": "files_touched", "deviation_stddev": 5.0}]}
        p5_result = {"status": "no_signals", "advisory": None}
        assert orch._compute_resolution(previous, p5_result) is None

    def test_residual_prompt_saved_when_findings_remain(self, tmp_path):
        """Residual prompt is auto-saved when there are remaining findings."""
        from evolution.orchestrator import Orchestrator

        evo_dir = tmp_path / ".evo"
        phase5_dir = evo_dir / "phase5"
        phase5_dir.mkdir(parents=True)
        inv_dir = evo_dir / "investigation"
        inv_dir.mkdir(parents=True)
        (inv_dir / "investigation.txt").write_text("Root cause: X")

        orch = Orchestrator.__new__(Orchestrator)
        orch.repo_path = tmp_path
        orch.evo_dir = evo_dir

        previous_advisory = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 19.7},
            ],
        }

        current_advisory = {
            "changes": [
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 10.3},
            ],
        }

        p5_result = {"status": "complete", "advisory": current_advisory}

        resolution = orch._compute_resolution(previous_advisory, p5_result)

        # Check residual prompt was saved
        residual_path = phase5_dir / "residual_prompt.txt"
        assert residual_path.exists()
        content = residual_path.read_text()
        assert "ITERATION" in content
        assert "ci / run_duration" in content

    def test_no_residual_prompt_when_all_resolved(self, tmp_path):
        """No residual prompt when all findings are resolved."""
        from evolution.orchestrator import Orchestrator

        evo_dir = tmp_path / ".evo"
        phase5_dir = evo_dir / "phase5"
        phase5_dir.mkdir(parents=True)

        orch = Orchestrator.__new__(Orchestrator)
        orch.repo_path = tmp_path
        orch.evo_dir = evo_dir

        previous_advisory = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 14.2},
            ],
        }

        current_advisory = {"changes": []}

        p5_result = {"status": "complete", "advisory": current_advisory}

        resolution = orch._compute_resolution(previous_advisory, p5_result)

        assert resolution["resolved"] == 1
        assert resolution["persisting"] == 0
        residual_path = phase5_dir / "residual_prompt.txt"
        assert not residual_path.exists()


# ──────────────── Hook script resolution display ────────────────


class TestHookScriptResolution:
    """Test that the hook script handles resolution progress in notifications."""

    def test_hook_script_checks_resolution_key(self):
        """Hook script should check for 'resolution' key in JSON output."""
        script = _build_hook_script(
            background=True, auto_open=False, notify=True,
            min_severity="concern", families="",
        )
        assert "resolution" in script

    def test_hook_script_prints_resolved_count(self):
        """Hook script Python one-liner should format resolution progress."""
        script = _build_hook_script(
            background=True, auto_open=False, notify=True,
            min_severity="concern", families="",
        )
        assert "resolved" in script
        assert "total_before" in script

    def test_hook_script_notification_uses_resolution_msg(self):
        """Notification block should use resolution message when available."""
        script = _build_hook_script(
            background=True, auto_open=False, notify=True,
            min_severity="concern", families="",
        )
        # Should parse resolution info from _evo_level
        assert "_evo_msg" in script
        assert "_evo_resolution" in script

    def test_hook_script_without_notify_no_resolution_block(self):
        """When notify=False, notification block is absent (no resolution display)."""
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        # No notification block, but resolution is still extracted in Python
        assert "resolution" in script  # Still in the Python parser
        assert "_evo_msg" not in script  # No notification message variable

    def test_hook_script_resolution_format(self):
        """The Python one-liner should output 'resolved X of Y|level' format."""
        script = _build_hook_script(
            background=True, auto_open=False, notify=True,
            min_severity="concern", families="",
        )
        # Check the Python one-liner produces the expected format
        assert "resolved" in script
        assert "'|'" in script  # Separator between resolution and level

    def test_hook_script_fallback_without_resolution(self):
        """When no resolution key, should just print level (backward compat)."""
        script = _build_hook_script(
            background=True, auto_open=False, notify=True,
            min_severity="concern", families="",
        )
        # The else branch prints just the level
        assert "print(level)" in script
