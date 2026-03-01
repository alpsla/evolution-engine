"""
Unit tests for secondary CLI commands: watch, license, notifications, patterns.

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


# ──────────────── TestWatch ────────────────


class TestWatch:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_watch_no_pro_exits_1(self, runner, tmp_path):
        """require_pro raises → exit 1."""
        with patch("evolution.license.require_pro",
                    side_effect=ProFeatureError("Commit Watcher")):
            result = runner.invoke(main, ["watch", str(tmp_path)])

        assert result.exit_code == 1
        assert "Pro" in result.output

    def test_watch_status_running(self, runner, tmp_path):
        """--status → 'Watcher running (PID ...)'."""
        with patch("evolution.license.require_pro"), \
             patch("evolution.watcher.CommitWatcher") as MockWatcher:
            MockWatcher.daemon_status.return_value = {"running": True, "pid": 12345}
            result = runner.invoke(main, ["watch", str(tmp_path), "--status"])

        assert result.exit_code == 0
        assert "Watcher running (PID 12345)" in result.output

    def test_watch_status_not_running(self, runner, tmp_path):
        """--status → 'Watcher not running'."""
        with patch("evolution.license.require_pro"), \
             patch("evolution.watcher.CommitWatcher") as MockWatcher:
            MockWatcher.daemon_status.return_value = {"running": False}
            result = runner.invoke(main, ["watch", str(tmp_path), "--status"])

        assert result.exit_code == 0
        assert "Watcher not running" in result.output

    def test_watch_stop(self, runner, tmp_path):
        """--stop → 'Watcher stopped'."""
        with patch("evolution.license.require_pro"), \
             patch("evolution.watcher.CommitWatcher") as MockWatcher:
            MockWatcher.stop_daemon.return_value = {"ok": True, "pid": 12345}
            result = runner.invoke(main, ["watch", str(tmp_path), "--stop"])

        assert result.exit_code == 0
        assert "Watcher stopped" in result.output


# ──────────────── TestLicenseStatus ────────────────


class TestLicenseStatus:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def _make_license(self, tier="free", valid=True, source="default", **kwargs):
        lic = MagicMock()
        lic.tier = tier
        lic.valid = valid
        lic.source = source
        lic.email = kwargs.get("email")
        lic.issued = kwargs.get("issued")
        lic.expires = kwargs.get("expires")
        if tier == "free":
            lic.features = {
                "tier1_adapters": True,
                "tier2_adapters": False,
                "llm_explanations": False,
            }
        else:
            lic.features = {
                "tier1_adapters": True,
                "tier2_adapters": True,
                "llm_explanations": True,
            }
        return lic

    def test_license_status_free(self, runner):
        """Free tier → shows 'free', upgrade prompt."""
        lic = self._make_license(tier="free")

        with patch("evolution.license.get_license", return_value=lic):
            result = runner.invoke(main, ["license", "status"])

        assert result.exit_code == 0
        assert "License: FREE" in result.output
        assert "Upgrade to Pro" in result.output

    def test_license_status_pro(self, runner):
        """Pro tier → shows 'pro', features."""
        lic = self._make_license(tier="pro", source="file")

        with patch("evolution.license.get_license", return_value=lic):
            result = runner.invoke(main, ["license", "status"])

        assert result.exit_code == 0
        assert "License: PRO" in result.output
        assert "Upgrade" not in result.output


# ──────────────── TestLicenseActivate ────────────────


class TestLicenseActivate:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))
        # Redirect ~/.evo to tmp_path to avoid touching real home
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    def test_license_activate_valid(self, runner, tmp_path):
        """Valid key → 'License activated', writes file."""
        mock_result = {"success": True, "tier": "pro", "source": "server"}

        with patch("evolution.license.activate_license", return_value=mock_result):
            result = runner.invoke(main, ["license", "activate", "pro_test_key_123"])

        assert result.exit_code == 0
        assert "License activated: PRO" in result.output

    def test_license_activate_invalid(self, runner):
        """Invalid key → exit 1, activation failed."""
        mock_result = {"success": False, "error": "Invalid or expired license key"}

        with patch("evolution.license.activate_license", return_value=mock_result):
            result = runner.invoke(main, ["license", "activate", "bad_key"])

        assert result.exit_code == 1
        assert "Activation failed" in result.output


# ──────────────── TestNotificationsList ────────────────


class TestNotificationsList:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_notifications_list_empty(self, runner):
        """No pending → 'No pending notifications'."""
        with patch("evolution.notifications.get_pending", return_value=[]):
            result = runner.invoke(main, ["notifications", "list"])

        assert result.exit_code == 0
        assert "No pending notifications" in result.output

    def test_notifications_list_has_items(self, runner):
        """Items → shows type and message."""
        pending = [
            {"type": "update", "message": "New version available: 0.3.0"},
            {"type": "adapter", "message": "New adapter: jest-cov"},
        ]

        with patch("evolution.notifications.get_pending", return_value=pending):
            result = runner.invoke(main, ["notifications", "list"])

        assert result.exit_code == 0
        assert "2 notification" in result.output
        assert "[update]" in result.output
        assert "New version available" in result.output
        assert "[adapter]" in result.output


# ──────────────── TestNotificationsDismiss ────────────────


class TestNotificationsDismiss:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_notifications_dismiss_all(self, runner):
        """'all' → 'All notifications dismissed'."""
        with patch("evolution.notifications.dismiss_all") as mock_dismiss:
            result = runner.invoke(main, ["notifications", "dismiss"])

        assert result.exit_code == 0
        assert "All notifications dismissed" in result.output
        mock_dismiss.assert_called_once()


# ──────────────── TestPatternsList ────────────────


class TestPatternsList:
    def test_patterns_list_no_kb(self, runner, tmp_path):
        """No knowledge.db → 'No knowledge base found'."""
        result = runner.invoke(main, ["patterns", "list", str(tmp_path)])

        assert result.exit_code == 0
        assert "No knowledge base found" in result.output


# ──────────────── TestPatternsPull ────────────────


class TestPatternsPull:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_patterns_pull_success(self, runner, tmp_path):
        """sync.pull() succeeds → prints pulled/skipped."""
        mock_sync = MagicMock()
        mock_sync.registry_url = "https://codequal.dev/api/patterns"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.pulled = 5
        mock_result.skipped = 3
        mock_result.rejected = 0
        mock_sync.pull.return_value = mock_result

        with patch("evolution.kb_sync.KBSync", return_value=mock_sync):
            result = runner.invoke(main, ["patterns", "pull", str(tmp_path)])

        assert result.exit_code == 0
        assert "Pulling from" in result.output
        assert "New patterns: 5" in result.output
        assert "Already present: 3" in result.output

    def test_patterns_pull_failure(self, runner, tmp_path):
        """sync.pull() fails → exit 1."""
        mock_sync = MagicMock()
        mock_sync.registry_url = "https://codequal.dev/api/patterns"
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Connection timeout"
        mock_sync.pull.return_value = mock_result

        with patch("evolution.kb_sync.KBSync", return_value=mock_sync):
            result = runner.invoke(main, ["patterns", "pull", str(tmp_path)])

        assert result.exit_code == 1
        assert "Connection timeout" in result.output


# ──────────────── TestPatternsPush ────────────────


class TestPatternsPush:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_patterns_push_success(self, runner, tmp_path):
        """privacy_level >= 1, push succeeds → prints count."""
        mock_sync = MagicMock()
        mock_sync.registry_url = "https://codequal.dev/api/patterns"
        mock_sync.privacy_level = 1
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.pushed = 7
        mock_sync.push.return_value = mock_result

        with patch("evolution.kb_sync.KBSync", return_value=mock_sync):
            result = runner.invoke(main, ["patterns", "push", str(tmp_path)])

        assert result.exit_code == 0
        assert "Patterns shared: 7" in result.output

    def test_patterns_push_disabled(self, runner, tmp_path):
        """privacy_level < 1 → exit 1."""
        mock_sync = MagicMock()
        mock_sync.privacy_level = 0

        with patch("evolution.kb_sync.KBSync", return_value=mock_sync):
            result = runner.invoke(main, ["patterns", "push", str(tmp_path)])

        assert result.exit_code == 1
        assert "Sharing is disabled" in result.output


# ──────────────── TestPatternsNew ────────────────


class TestPatternsNew:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_patterns_new_scaffold(self, runner):
        """Returns package info → prints name, path."""
        scaffold_result = {
            "package_name": "evo-patterns-web-security",
            "path": "/tmp/evo-patterns-web-security",
            "module_name": "evo_patterns_web_security",
            "files_created": ["pyproject.toml", "evo_patterns_web_security/patterns.json"],
        }

        with patch("evolution.pattern_scaffold.scaffold_pattern_pack",
                    return_value=scaffold_result):
            result = runner.invoke(main, ["patterns", "new", "web-security"])

        assert result.exit_code == 0
        assert "evo-patterns-web-security" in result.output
        assert "Files: 2" in result.output
        assert "Next steps:" in result.output


# ──────────────── TestPatternsSourceOps ────────────────


class TestPatternsSourceOps:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_patterns_add(self, runner):
        """'Added ... to pattern sources'."""
        with patch("evolution.pattern_registry.add_pattern_source", return_value=True):
            result = runner.invoke(main, ["patterns", "add", "evo-patterns-test"])

        assert result.exit_code == 0
        assert "Added evo-patterns-test to pattern sources" in result.output

    def test_patterns_remove(self, runner):
        """'Removed ... from pattern sources'."""
        with patch("evolution.pattern_registry.remove_pattern_source", return_value=True):
            result = runner.invoke(main, ["patterns", "remove", "evo-patterns-test"])

        assert result.exit_code == 0
        assert "Removed evo-patterns-test from pattern sources" in result.output

    def test_patterns_block(self, runner):
        """'Blocked pattern package: ...'."""
        with patch("evolution.pattern_registry.block_pattern_package", return_value=True):
            result = runner.invoke(main, [
                "patterns", "block", "bad-pkg", "--reason", "malicious",
            ])

        assert result.exit_code == 0
        assert "Blocked pattern package: bad-pkg" in result.output
        assert "Reason: malicious" in result.output

    def test_patterns_unblock(self, runner):
        """'Unblocked pattern package: ...'."""
        with patch("evolution.pattern_registry.unblock_pattern_package", return_value=True):
            result = runner.invoke(main, ["patterns", "unblock", "prev-blocked-pkg"])

        assert result.exit_code == 0
        assert "Unblocked pattern package: prev-blocked-pkg" in result.output


# ──────────────── TestPatternsPackages ────────────────


class TestPatternsPackages:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    def test_patterns_packages_none(self, runner):
        """Empty list → 'No pattern packages'."""
        with patch("evolution.pattern_registry.list_pattern_packages", return_value=[]):
            result = runner.invoke(main, ["patterns", "packages"])

        assert result.exit_code == 0
        assert "No pattern packages" in result.output
