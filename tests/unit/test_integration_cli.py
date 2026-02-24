"""
Unit tests for integration CLI commands: init, hooks, config, history, verify.

Uses Click's CliRunner for isolated command testing.
Mocks at module boundaries to avoid real I/O, AI calls, and filesystem side effects.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from evolution.cli import main
from evolution.license import ProFeatureError


@pytest.fixture
def runner():
    return CliRunner()


# ──────────────── TestInit ────────────────


class TestInit:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def _mock_pi(self, setup_return=None, env_overrides=None):
        """Build a canned ProjectInit mock."""
        env = {
            "is_git_repo": True,
            "has_github": True,
            "has_workflows": False,
            "has_gitlab": False,
            "has_evo": False,
            "has_evo_action": False,
            "has_evo_gitlab": False,
            "repo_name": "test-repo",
            "suggested_path": "cli",
            "ci_provider": "github",
        }
        if env_overrides:
            env.update(env_overrides)

        if setup_return is None:
            setup_return = {"ok": True, "actions": ["Created .evo/", "Ready to analyze"]}

        pi = MagicMock()
        pi.detect_environment.return_value = env
        pi.setup.return_value = setup_return
        pi.first_run_hint.return_value = "Run `evo analyze .` to start"
        return pi

    def test_init_cli_path(self, runner, tmp_path):
        """--path cli → calls setup(path='cli'), prints actions."""
        pi = self._mock_pi()

        with patch("evolution.init.ProjectInit", return_value=pi), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["init", str(tmp_path), "--path", "cli"])

        assert result.exit_code == 0
        pi.setup.assert_called_once_with("cli", families="")
        assert "Integration path: cli" in result.output
        assert "Created .evo/" in result.output

    def test_init_hooks_pro_gate(self, runner, tmp_path):
        """--path hooks + require_pro raises → exit 1."""
        pi = self._mock_pi()

        with patch("evolution.init.ProjectInit", return_value=pi), \
             patch("evolution.license.require_pro", side_effect=ProFeatureError("Git Hooks")):
            result = runner.invoke(main, ["init", str(tmp_path), "--path", "hooks"])

        assert result.exit_code == 1
        assert "Pro" in result.output

    def test_init_action_pro_gate(self, runner, tmp_path):
        """--path action + require_pro raises → exit 1."""
        pi = self._mock_pi()

        with patch("evolution.init.ProjectInit", return_value=pi), \
             patch("evolution.license.require_pro", side_effect=ProFeatureError("CI Integration")):
            result = runner.invoke(main, ["init", str(tmp_path), "--path", "action"])

        assert result.exit_code == 1
        assert "Pro" in result.output

    def test_init_setup_failure_exits_1(self, runner, tmp_path):
        """pi.setup() returns ok=False → exit 1."""
        pi = self._mock_pi(setup_return={"ok": False, "error": "No git repo"})

        with patch("evolution.init.ProjectInit", return_value=pi), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["init", str(tmp_path), "--path", "cli"])

        assert result.exit_code == 1
        assert "No git repo" in result.output

    def test_init_families_option(self, runner, tmp_path):
        """--families git,ci → ProjectInit.setup() receives families."""
        pi = self._mock_pi()

        with patch("evolution.init.ProjectInit", return_value=pi) as pi_cls, \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, [
                "init", str(tmp_path), "--path", "cli", "--families", "git,ci",
            ])

        assert result.exit_code == 0
        pi.setup.assert_called_once_with("cli", families="git,ci")


# ──────────────── TestHooksInstall ────────────────


class TestHooksInstall:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_hooks_install_happy_path(self, runner, tmp_path):
        """Pro passes, install succeeds → prints hook path, trigger."""
        mock_hm = MagicMock()
        mock_hm.install.return_value = {
            "ok": True,
            "hook_path": str(tmp_path / ".git" / "hooks" / "post-commit"),
            "trigger": "post-commit",
        }
        mock_hm.status.return_value = {
            "installed": True,
            "trigger": "post-commit",
            "hook_path": str(tmp_path / ".git" / "hooks" / "post-commit"),
            "config": {"min_severity": "concern", "notify": False},
        }

        with patch("evolution.license.require_pro"), \
             patch("evolution.hooks.HookManager", return_value=mock_hm):
            result = runner.invoke(main, ["hooks", "install", str(tmp_path)])

        assert result.exit_code == 0
        assert "Hook installed:" in result.output
        assert "post-commit" in result.output
        assert "EE will now analyze" in result.output

    def test_hooks_install_no_pro(self, runner, tmp_path):
        """require_pro raises → exit 1, 'Pro' in output."""
        with patch("evolution.license.require_pro",
                    side_effect=ProFeatureError("Git Hooks")):
            result = runner.invoke(main, ["hooks", "install", str(tmp_path)])

        assert result.exit_code == 1
        assert "Pro" in result.output

    def test_hooks_install_failure(self, runner, tmp_path):
        """hm.install() returns ok=False → exit 1."""
        mock_hm = MagicMock()
        mock_hm.install.return_value = {"ok": False, "error": "Not a git repo"}

        with patch("evolution.license.require_pro"), \
             patch("evolution.hooks.HookManager", return_value=mock_hm):
            result = runner.invoke(main, ["hooks", "install", str(tmp_path)])

        assert result.exit_code == 1
        assert "Not a git repo" in result.output


# ──────────────── TestHooksUninstall ────────────────


class TestHooksUninstall:
    def test_hooks_uninstall_success(self, runner, tmp_path):
        """Returns removed paths → prints 'Removed:'."""
        mock_hm = MagicMock()
        mock_hm.uninstall.return_value = {
            "ok": True,
            "removed": [str(tmp_path / ".git" / "hooks" / "post-commit")],
        }

        with patch("evolution.hooks.HookManager", return_value=mock_hm):
            result = runner.invoke(main, ["hooks", "uninstall", str(tmp_path)])

        assert result.exit_code == 0
        assert "Removed:" in result.output

    def test_hooks_uninstall_not_found(self, runner, tmp_path):
        """Returns empty → prints 'No EE hooks found'."""
        mock_hm = MagicMock()
        mock_hm.uninstall.return_value = {"ok": True, "removed": []}

        with patch("evolution.hooks.HookManager", return_value=mock_hm):
            result = runner.invoke(main, ["hooks", "uninstall", str(tmp_path)])

        assert result.exit_code == 0
        assert "No EE hooks found" in result.output


# ──────────────── TestHooksStatus ────────────────


class TestHooksStatus:
    def test_hooks_status_installed(self, runner, tmp_path):
        """Returns installed=True → shows trigger, path."""
        mock_hm = MagicMock()
        mock_hm.status.return_value = {
            "installed": True,
            "trigger": "post-commit",
            "hook_path": str(tmp_path / ".git" / "hooks" / "post-commit"),
            "config": {
                "trigger": "post-commit",
                "min_severity": "concern",
                "background": True,
                "notify": False,
                "auto_open": False,
            },
        }

        with patch("evolution.hooks.HookManager", return_value=mock_hm):
            result = runner.invoke(main, ["hooks", "status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Hook: installed" in result.output
        assert "post-commit" in result.output

    def test_hooks_status_not_installed(self, runner, tmp_path):
        """Returns installed=False → shows 'not installed'."""
        mock_hm = MagicMock()
        mock_hm.status.return_value = {
            "installed": False,
            "trigger": None,
            "hook_path": None,
            "config": {
                "trigger": "post-commit",
                "min_severity": "concern",
                "background": True,
                "notify": False,
                "auto_open": False,
            },
        }

        with patch("evolution.hooks.HookManager", return_value=mock_hm):
            result = runner.invoke(main, ["hooks", "status", str(tmp_path)])

        assert result.exit_code == 0
        assert "not installed" in result.output
        assert "evo hooks install" in result.output


# ──────────────── TestConfig ────────────────


class TestConfig:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_config_list(self, runner):
        """Shows grouped settings output."""
        mock_cfg = MagicMock()
        mock_cfg.path = "/tmp/config/config.toml"
        mock_cfg.user_overrides.return_value = {}
        mock_cfg.all.return_value = {"analysis.depth": 50}
        mock_cfg.get.return_value = 50

        with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.config.config_groups", return_value={
                 "analysis": {"label": "Analysis Settings"},
             }), \
             patch("evolution.config.config_keys_for_group", return_value=["analysis.depth"]), \
             patch("evolution.config.config_metadata", return_value={
                 "description": "Number of commits to analyze",
             }):
            result = runner.invoke(main, ["config", "list"])

        assert result.exit_code == 0
        assert "Config file:" in result.output
        assert "Analysis Settings" in result.output

    def test_config_get_found(self, runner):
        """Known key → prints value."""
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = 50

        with patch("evolution.config.EvoConfig", return_value=mock_cfg):
            result = runner.invoke(main, ["config", "get", "analysis.depth"])

        assert result.exit_code == 0
        assert "50" in result.output

    def test_config_get_unknown_exits_1(self, runner):
        """Unknown key → exit 1."""
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = None

        with patch("evolution.config.EvoConfig", return_value=mock_cfg):
            result = runner.invoke(main, ["config", "get", "no.such.key"])

        assert result.exit_code == 1
        assert "Unknown key" in result.output

    def test_config_set(self, runner):
        """Sets value → prints 'key = value'."""
        mock_cfg = MagicMock()

        with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.config._parse_value", return_value=100):
            result = runner.invoke(main, ["config", "set", "analysis.depth", "100"])

        assert result.exit_code == 0
        assert "analysis.depth = 100" in result.output
        mock_cfg.set.assert_called_once_with("analysis.depth", 100)

    def test_config_reset(self, runner):
        """Resets → prints 'Reset key to default'."""
        mock_cfg = MagicMock()
        mock_cfg.delete.return_value = True

        with patch("evolution.config.EvoConfig", return_value=mock_cfg):
            result = runner.invoke(main, ["config", "reset", "analysis.depth"])

        assert result.exit_code == 0
        assert "Reset analysis.depth to default" in result.output


# ──────────────── TestHistoryList ────────────────


class TestHistoryList:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def _mock_runs(self):
        return [
            {
                "timestamp": "2026-02-20T12:00:00",
                "changes_count": 3,
                "families": ["git", "ci"],
                "scope": "test-repo",
            },
            {
                "timestamp": "2026-02-20T10:00:00",
                "changes_count": 1,
                "families": ["git"],
                "scope": "test-repo",
            },
        ]

    def test_history_list_happy(self, runner, tmp_path):
        """Has runs → shows run count and entries."""
        mock_hm = MagicMock()
        mock_hm.list_runs.return_value = self._mock_runs()

        with patch("evolution.history.HistoryManager", return_value=mock_hm):
            result = runner.invoke(main, ["history", "list", str(tmp_path)])

        assert result.exit_code == 0
        assert "2 snapshot" in result.output
        assert "2026-02-20T12:00:00" in result.output
        assert "3 changes" in result.output

    def test_history_list_no_runs(self, runner, tmp_path):
        """No runs → 'No run history found'."""
        mock_hm = MagicMock()
        mock_hm.list_runs.return_value = []

        with patch("evolution.history.HistoryManager", return_value=mock_hm):
            result = runner.invoke(main, ["history", "list", str(tmp_path)])

        assert result.exit_code == 0
        assert "No run history found" in result.output

    def test_history_list_json(self, runner, tmp_path):
        """--json → valid JSON array."""
        runs = self._mock_runs()
        mock_hm = MagicMock()
        mock_hm.list_runs.return_value = runs

        with patch("evolution.history.HistoryManager", return_value=mock_hm):
            result = runner.invoke(main, ["history", "list", str(tmp_path), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2


# ──────────────── TestHistoryShow ────────────────


class TestHistoryShow:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_history_show_happy(self, runner, tmp_path):
        """Shows snapshot details."""
        mock_hm = MagicMock()
        mock_hm.load_run.return_value = {
            "timestamp": "2026-02-20T12:00:00",
            "scope": "test-repo",
            "saved_at": "2026-02-20T12:00:01",
            "advisory": {
                "changes": [
                    {
                        "family": "git",
                        "metric": "dispersion",
                        "deviation_stddev": 3.2,
                        "observed": 0.85,
                    },
                ],
            },
        }

        with patch("evolution.history.HistoryManager", return_value=mock_hm):
            result = runner.invoke(main, [
                "history", "show", "2026-02-20T12:00:00", str(tmp_path),
            ])

        assert result.exit_code == 0
        assert "Snapshot: 2026-02-20T12:00:00" in result.output
        assert "1 significant change" in result.output
        assert "git / dispersion" in result.output

    def test_history_show_not_found(self, runner, tmp_path):
        """Invalid run → exit 1."""
        mock_hm = MagicMock()
        mock_hm.load_run.side_effect = FileNotFoundError("No such snapshot")

        with patch("evolution.history.HistoryManager", return_value=mock_hm):
            result = runner.invoke(main, [
                "history", "show", "bad-timestamp", str(tmp_path),
            ])

        assert result.exit_code == 1


# ──────────────── TestHistoryDiff ────────────────


class TestHistoryDiff:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_history_diff_happy(self, runner, tmp_path):
        """Compares two runs → prints summary."""
        mock_hm = MagicMock()
        mock_hm.list_runs.return_value = [
            {"timestamp": "2026-02-20T12:00:00"},
            {"timestamp": "2026-02-20T10:00:00"},
        ]
        mock_hm.compare.return_value = {
            "summary_text": "Compared 2 runs: 1 resolved, 0 new",
            "resolved": [{"family": "git", "metric": "dispersion"}],
            "new": [],
        }

        with patch("evolution.history.HistoryManager", return_value=mock_hm):
            result = runner.invoke(main, ["history", "diff", str(tmp_path)])

        assert result.exit_code == 0
        assert "Compared 2 runs" in result.output

    def test_history_diff_too_few_runs(self, runner, tmp_path):
        """< 2 runs → exit 1, 'Need at least 2 runs'."""
        mock_hm = MagicMock()
        mock_hm.list_runs.return_value = [
            {"timestamp": "2026-02-20T12:00:00"},
        ]

        with patch("evolution.history.HistoryManager", return_value=mock_hm):
            result = runner.invoke(main, ["history", "diff", str(tmp_path)])

        assert result.exit_code == 1
        assert "Need at least 2 runs" in result.output


# ──────────────── TestHistoryClean ────────────────


class TestHistoryClean:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_history_clean_no_args_exits_1(self, runner, tmp_path):
        """No --keep or --before → exit 1."""
        with patch("evolution.history.HistoryManager"):
            result = runner.invoke(main, ["history", "clean", str(tmp_path)])

        assert result.exit_code == 1
        assert "--keep" in result.output or "Specify" in result.output


# ──────────────── TestVerify ────────────────


class TestVerify:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def _seed_previous_advisory(self, tmp_path):
        """Write a minimal previous advisory for verify to read."""
        prev = tmp_path / "previous_advisory.json"
        prev.write_text(json.dumps({
            "generated_at": "2026-02-20T10:00:00Z",
            "changes": [{"family": "git", "metric": "dispersion"}],
        }))
        return str(prev)

    def test_verify_happy(self, runner, tmp_path):
        """Prints verification text and resolution summary."""
        prev = self._seed_previous_advisory(tmp_path)

        mock_phase5 = MagicMock()
        mock_phase5.verify.return_value = {
            "status": "verified",
            "verification_text": "Verification: 1 resolved, 0 persisting",
            "verification": {
                "summary": {
                    "total_before": 1,
                    "resolved": 1,
                    "persisting": 0,
                    "new": 0,
                },
            },
        }

        with patch("evolution.phase5_engine.Phase5Engine", return_value=mock_phase5):
            result = runner.invoke(main, [
                "verify", prev, "--path", str(tmp_path),
            ])

        assert result.exit_code == 0
        assert "Verification:" in result.output
        assert "All findings resolved" in result.output

    def test_verify_quiet_issues_exits_1(self, runner, tmp_path):
        """--quiet + persisting issues → exit 1."""
        prev = self._seed_previous_advisory(tmp_path)

        mock_phase5 = MagicMock()
        mock_phase5.verify.return_value = {
            "status": "verified",
            "verification_text": "Verification: 0 resolved, 1 persisting",
            "verification": {
                "summary": {
                    "total_before": 1,
                    "resolved": 0,
                    "persisting": 1,
                    "new": 0,
                },
            },
        }

        with patch("evolution.phase5_engine.Phase5Engine", return_value=mock_phase5):
            result = runner.invoke(main, [
                "verify", prev, "--path", str(tmp_path), "--quiet",
            ])

        assert result.exit_code == 1
