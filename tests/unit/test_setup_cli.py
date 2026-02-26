"""
Unit tests for `evo setup` CLI command and setup UI integration.

Covers:
  - --ui flag launches SetupUI.serve() with correct port
  - Smart wizard: auto-detect sources, ask token + preferences
  - --reset flag clears user overrides
  - CLI and UI both write to the same EvoConfig instance
"""

import json
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from evolution.cli import main
from evolution.config import (
    EvoConfig,
    _DEFAULTS,
    _METADATA,
    config_groups,
    config_keys_for_group,
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirect EvoConfig to a temp directory via EVO_CONFIG_DIR env var."""
    config_dir = tmp_path / "evo_home"
    config_dir.mkdir()
    monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
    return config_dir / "config.toml"


# ─── evo setup --ui ───


class TestSetupUI:
    """Tests for `evo setup --ui` launching the browser-based settings page."""

    def test_ui_flag_calls_serve(self, runner, tmp_path, isolated_config):
        with patch("evolution.setup_ui.SetupUI.serve") as mock_serve:
            result = runner.invoke(main, ["setup", str(tmp_path), "--ui"])
        assert result.exit_code == 0
        mock_serve.assert_called_once()

    def test_ui_default_port(self, runner, tmp_path, isolated_config):
        with patch("evolution.setup_ui.SetupUI.__init__", return_value=None) as mock_init, \
             patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, ["setup", str(tmp_path), "--ui"])
        assert result.exit_code == 0
        call_kwargs = mock_init.call_args
        assert call_kwargs[1].get("port") == 8484

    def test_ui_custom_port(self, runner, tmp_path, isolated_config):
        with patch("evolution.setup_ui.SetupUI.__init__", return_value=None) as mock_init, \
             patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, [
                "setup", str(tmp_path), "--ui", "--port", "9090",
            ])
        assert result.exit_code == 0
        call_kwargs = mock_init.call_args
        assert call_kwargs[1].get("port") == 9090

    def test_ui_output_messages(self, runner, tmp_path, isolated_config):
        with patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, ["setup", str(tmp_path), "--ui"])
        assert "Opening settings in browser" in result.output
        assert "Settings saved" in result.output

    def test_ui_returns_before_wizard(self, runner, tmp_path, isolated_config):
        with patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, ["setup", str(tmp_path), "--ui"])
        assert result.exit_code == 0
        assert "Detecting signal sources" not in result.output


# ─── Smart wizard ───


class TestSmartWizard:
    """Tests for the smart auto-detect setup wizard."""

    def test_header_displayed(self, runner, tmp_path, isolated_config):
        result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n\n\n")
        assert "Evolution Engine Setup" in result.output
        assert "=" * 40 in result.output

    def test_auto_detect_runs(self, runner, tmp_path, isolated_config):
        result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n\n\n")
        assert "Detecting signal sources" in result.output

    def test_github_token_prompt_shown(self, runner, tmp_path, isolated_config, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with patch("dotenv.load_dotenv", return_value=None):
            result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n\n\n")
        assert "GitHub token" in result.output

    def test_github_token_detected(self, runner, tmp_path, isolated_config, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n\n")
        assert "GITHUB_TOKEN detected" in result.output

    def test_enter_keeps_defaults(self, runner, tmp_path, isolated_config):
        result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n\n\n\n")
        assert result.exit_code == 0
        assert "0 setting(s) changed" in result.output

    def test_completion_message(self, runner, tmp_path, isolated_config):
        result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n\n\n\n")
        assert "Setup complete" in result.output
        assert "evo config list" in result.output


class TestSmartWizardReset:
    """Test the --reset flag clears user overrides."""

    def test_reset_clears_overrides(self, runner, tmp_path, isolated_config):
        cfg = EvoConfig(path=isolated_config)
        cfg.set("analyze.families", "git,ci")
        cfg.set("sync.privacy_level", 1)
        cfg.set("hooks.trigger", "pre-push")

        # 'y' to confirm reset, then Enter through wizard prompts
        result = runner.invoke(main, ["setup", str(tmp_path), "--reset"], input="y\n\n\n\n\n\n")

        assert result.exit_code == 0
        assert "reset to defaults" in result.output.lower()
        cfg2 = EvoConfig(path=isolated_config)
        assert cfg2.user_overrides() == {}

    def test_reset_decline(self, runner, tmp_path, isolated_config):
        cfg = EvoConfig(path=isolated_config)
        cfg.set("analyze.families", "git,ci")

        result = runner.invoke(main, ["setup", str(tmp_path), "--reset"], input="n\n\n\n\n\n\n")

        assert result.exit_code == 0
        cfg2 = EvoConfig(path=isolated_config)
        assert cfg2.get("analyze.families") == "git,ci"


# ─── CLI and UI share the same config ───


class TestSetupCLIAndUIShareConfig:
    """Verify CLI and UI both read/write the same EvoConfig."""

    def test_ui_changes_visible_in_config(self, tmp_path):
        from evolution.setup_ui import SetupUI

        cfg = EvoConfig(path=tmp_path / "config.toml")
        ui = SetupUI(port=0, config=cfg, timeout=0)

        body = json.dumps({"analyze.families": "git,ci"}).encode("utf-8")
        handler = MagicMock()
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        handler.wfile = BytesIO()
        written = []
        handler.wfile.write = lambda d: written.append(d)

        ui._handle_post(handler)

        assert cfg.get("analyze.families") == "git,ci"
        cfg2 = EvoConfig(path=tmp_path / "config.toml")
        assert cfg2.get("analyze.families") == "git,ci"

    def test_cli_changes_visible_in_ui(self, tmp_path):
        from evolution.setup_ui import SetupUI

        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("hooks.trigger", "pre-push")

        ui = SetupUI(port=0, config=cfg, timeout=0)
        handler = MagicMock()
        handler.headers = {}
        handler.wfile = BytesIO()
        written = []
        handler.wfile.write = lambda d: written.append(d)

        ui._handle_status(handler)
        response = json.loads(b"".join(written))
        assert response["hooks.trigger"] == "pre-push"

    def test_shared_config_object(self, tmp_path):
        from evolution.setup_ui import SetupUI

        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("sync.privacy_level", 1)

        ui = SetupUI(port=0, config=cfg, timeout=0)
        assert ui.config.get("sync.privacy_level") == 1

        ui.config.set("hooks.trigger", "pre-push")
        assert cfg.get("hooks.trigger") == "pre-push"

    def test_disk_persistence_across_instances(self, tmp_path):
        from evolution.setup_ui import SetupUI

        cfg_path = tmp_path / "config.toml"
        cfg1 = EvoConfig(path=cfg_path)
        cfg1.set("hooks.notify", False)

        cfg2 = EvoConfig(path=cfg_path)
        ui = SetupUI(port=0, config=cfg2, timeout=0)

        body = json.dumps({"hooks.trigger": "pre-push"}).encode("utf-8")
        handler = MagicMock()
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        handler.wfile = BytesIO()
        handler.wfile.write = lambda d: None

        ui._handle_post(handler)

        cfg3 = EvoConfig(path=cfg_path)
        assert cfg3.get("hooks.notify") is False
        assert cfg3.get("hooks.trigger") == "pre-push"


# ─── Task #47: Config key fixes ───


class TestSetupAutoOpenKey:
    """The setup wizard should read/write hooks.auto_open, not report.auto_open."""

    def test_setup_auto_open_uses_hooks_key(self, runner, tmp_path, isolated_config):
        """Typing 'no' for auto-open writes to hooks.auto_open."""
        cfg = EvoConfig(path=isolated_config)
        # Defaults: hooks.auto_open = True
        assert cfg.get("hooks.auto_open") is True

        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_fake"}, clear=False):
            # Enter through privacy, then type 'no' for auto-open
            result = runner.invoke(main, ["setup", str(tmp_path)], input="\nno\n")

        assert result.exit_code == 0
        cfg2 = EvoConfig(path=isolated_config)
        assert cfg2.get("hooks.auto_open") is False

    def test_setup_privacy_fallback_binary(self, runner, tmp_path, isolated_config):
        """Privacy options should only show 0 and 1 (binary), not 2."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_fake"}, clear=False):
            result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n")

        assert result.exit_code == 0
        # Should show "0." and "1." options but NOT "2."
        assert "0." in result.output
        assert "1." in result.output
        # Check that no "2. " line exists in the privacy section
        lines = result.output.split("\n")
        assert not any(line.strip().startswith("2.") for line in lines), \
            "Privacy level 2 should not appear as an option"


class TestSetupSourcesHint:
    """Task #48: setup should show 'evo sources' hint after detected tools."""

    def test_setup_shows_sources_hint(self, runner, tmp_path, isolated_config):
        """When prescan detects tools, show 'evo sources' hint."""
        from evolution.prescan import DetectedService

        mock_services = [
            DetectedService(
                service="sentry",
                display_name="Sentry",
                family="error_tracking",
                adapter="evo-adapter-sentry",
                detection_layers=["config"],
                evidence=[".sentryclirc found"],
            ),
        ]

        with patch("evolution.prescan.SourcePrescan") as mock_cls, \
             patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_fake"}, clear=False):
            mock_cls.return_value.scan.return_value = mock_services
            result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n")

        assert result.exit_code == 0
        assert "evo sources" in result.output

    def test_setup_no_sources_hint_when_nothing_detected(self, runner, tmp_path, isolated_config):
        """When no tools detected, don't show the sources hint."""
        with patch("evolution.prescan.SourcePrescan") as mock_cls, \
             patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_fake"}, clear=False):
            mock_cls.return_value.scan.return_value = []
            result = runner.invoke(main, ["setup", str(tmp_path)], input="\n\n")

        assert result.exit_code == 0
        assert "evo sources" not in result.output
