"""
Unit tests for `evo setup` CLI command and setup UI integration.

Covers:
  - --ui flag launches SetupUI.serve() with correct port
  - Terminal wizard: Enter keeps value, 's' skips group, 'q' saves & quits
  - Setting boolean and choice values through the wizard
  - --reset flag clears user overrides
  - CLI and UI both write to the same EvoConfig instance

Uses Click's CliRunner for isolated command testing.
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
    """Redirect EvoConfig to a temp directory via EVO_CONFIG_DIR env var.

    Returns the path to the config.toml that will be used.
    """
    config_dir = tmp_path / "evo_home"
    config_dir.mkdir()
    monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
    return config_dir / "config.toml"


def _total_wizard_prompts():
    """Count how many prompts the wizard will show (non-internal keys)."""
    groups = config_groups()
    return sum(len(config_keys_for_group(gid)) for gid in groups)


# ─── evo setup --ui ───


class TestSetupUI:
    """Tests for `evo setup --ui` launching the browser-based settings page."""

    def test_ui_flag_calls_serve(self, runner, tmp_path, isolated_config):
        """--ui should instantiate SetupUI and call .serve()."""
        with patch("evolution.setup_ui.SetupUI.serve") as mock_serve:
            result = runner.invoke(main, ["setup", str(tmp_path), "--ui"])

        assert result.exit_code == 0
        mock_serve.assert_called_once()

    def test_ui_default_port(self, runner, tmp_path, isolated_config):
        """Default port should be 8484 when --port is not specified."""
        with patch("evolution.setup_ui.SetupUI.__init__", return_value=None) as mock_init, \
             patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, ["setup", str(tmp_path), "--ui"])

        assert result.exit_code == 0
        call_kwargs = mock_init.call_args
        assert call_kwargs[1].get("port") == 8484

    def test_ui_custom_port(self, runner, tmp_path, isolated_config):
        """--ui --port 9090 should pass port=9090 to SetupUI."""
        with patch("evolution.setup_ui.SetupUI.__init__", return_value=None) as mock_init, \
             patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, [
                "setup", str(tmp_path), "--ui", "--port", "9090",
            ])

        assert result.exit_code == 0
        call_kwargs = mock_init.call_args
        assert call_kwargs[1].get("port") == 9090

    def test_ui_output_messages(self, runner, tmp_path, isolated_config):
        """--ui should print opening and saved messages."""
        with patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, ["setup", str(tmp_path), "--ui"])

        assert "Opening settings in browser" in result.output
        assert "Settings saved" in result.output

    def test_ui_port_in_output_message(self, runner, tmp_path, isolated_config):
        """Output message should mention the correct port."""
        with patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, [
                "setup", str(tmp_path), "--ui", "--port", "7777",
            ])

        assert "7777" in result.output

    def test_ui_returns_before_wizard(self, runner, tmp_path, isolated_config):
        """--ui should return immediately after serve(); no wizard prompts."""
        with patch("evolution.setup_ui.SetupUI.serve"):
            result = runner.invoke(main, ["setup", str(tmp_path), "--ui"])

        assert result.exit_code == 0
        # Wizard header should NOT appear
        assert "=" * 40 not in result.output
        assert "Press Enter to keep" not in result.output


# ─── evo setup terminal wizard ───


class TestSetupWizardEnterKeepsValue:
    """Pressing Enter on every prompt should keep all current values unchanged."""

    def test_enter_keeps_defaults(self, runner, tmp_path, isolated_config):
        """Pressing Enter for every prompt should not change any settings."""
        prompt_count = _total_wizard_prompts()
        input_lines = "\n" * (prompt_count + 10)

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        assert "0 setting(s) changed" in result.output

    def test_enter_preserves_existing_override(self, runner, tmp_path, isolated_config):
        """If a value was previously set, Enter should keep it."""
        cfg = EvoConfig(path=isolated_config)
        cfg.set("llm.model", "gpt-4-turbo")

        prompt_count = _total_wizard_prompts()
        input_lines = "\n" * (prompt_count + 10)

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg2 = EvoConfig(path=isolated_config)
        assert cfg2.get("llm.model") == "gpt-4-turbo"


class TestSetupWizardSkipGroup:
    """Typing 's' at a prompt should skip the rest of that group."""

    def test_skip_first_group(self, runner, tmp_path, isolated_config):
        """Typing 's' at the first prompt in the first group should skip it."""
        prompt_count = _total_wizard_prompts()
        input_lines = "s\n" + ("\n" * (prompt_count + 10))

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        assert "0 setting(s) changed" in result.output

    def test_skip_does_not_modify_skipped_keys(self, runner, tmp_path, isolated_config):
        """Skipping a group should leave its keys at defaults."""
        # Skip first group ('analyze'), then quit
        input_lines = "s\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("analyze.families") == _DEFAULTS["analyze.families"]
        assert cfg.get("analyze.json_output") == _DEFAULTS["analyze.json_output"]


class TestSetupWizardQuitEarly:
    """Typing 'q' should save changes made so far and exit."""

    def test_quit_immediately(self, runner, tmp_path, isolated_config):
        """Typing 'q' at the first prompt should exit with 0 changes."""
        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input="q\n",
        )

        assert result.exit_code == 0
        assert "Saved 0 change(s)" in result.output

    def test_quit_after_one_change(self, runner, tmp_path, isolated_config):
        """Set a value, then quit. The change should be saved."""
        # First group is 'analyze'. First key is analyze.families (str type).
        # Type a value, then quit on the next prompt.
        input_lines = "git,ci\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        assert "Saved 1 change(s)" in result.output
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("analyze.families") == "git,ci"

    def test_quit_preserves_prior_changes(self, runner, tmp_path, isolated_config):
        """Changes made before 'q' should persist on disk."""
        input_lines = "git,ci\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        # Reload config from disk
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("analyze.families") == "git,ci"


class TestSetupWizardBoolValue:
    """Test setting boolean values through the wizard."""

    def test_set_bool_true(self, runner, tmp_path, isolated_config):
        """Typing 'yes' on a bool prompt should set it to True."""
        # First key in 'analyze' group is analyze.families (str),
        # second is analyze.json_output (bool).
        # Skip families with Enter, set json_output to yes, then quit.
        input_lines = "\nyes\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("analyze.json_output") is True

    def test_set_bool_false_from_true(self, runner, tmp_path, isolated_config):
        """Typing 'no' on a bool prompt currently True should set it to False."""
        cfg = EvoConfig(path=isolated_config)
        cfg.set("analyze.json_output", True)

        input_lines = "\nno\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg2 = EvoConfig(path=isolated_config)
        assert cfg2.get("analyze.json_output") is False

    def test_bool_y_shorthand(self, runner, tmp_path, isolated_config):
        """Typing 'y' should be treated as True."""
        input_lines = "\ny\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("analyze.json_output") is True

    def test_bool_true_string(self, runner, tmp_path, isolated_config):
        """Typing 'true' should be treated as True."""
        input_lines = "\ntrue\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("analyze.json_output") is True


class TestSetupWizardChoiceValue:
    """Test setting choice values through the wizard."""

    def test_select_choice_by_number(self, runner, tmp_path, isolated_config):
        """Selecting a numbered choice option should set the value."""
        # 'analyze' group: families (str), json_output (bool) => 2 prompts
        # 'hooks' group: trigger (choice) is first key
        # hooks.trigger allowed = ["post-commit", "pre-push"]
        # Default is "post-commit" (index 0). Selecting 2 => "pre-push".
        # Skip analyze group (2 keys), then choose "2" for hooks.trigger.
        input_lines = "\n\n" + "2\n" + "q\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("hooks.trigger") == "pre-push"

    def test_choice_enter_keeps_current(self, runner, tmp_path, isolated_config):
        """Pressing Enter on a choice prompt should keep the current value."""
        original = _DEFAULTS["hooks.trigger"]

        # Skip analyze (2 keys), Enter on hooks.trigger, then quit
        input_lines = "\n\n" + "\n" + "q\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("hooks.trigger") == original

    def test_choice_invalid_number_ignored(self, runner, tmp_path, isolated_config):
        """Invalid choice number should not change the value."""
        original = _DEFAULTS["hooks.trigger"]

        # Skip analyze (2), type "99" for hooks.trigger (invalid), then quit
        input_lines = "\n\n" + "99\n" + "q\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("hooks.trigger") == original

    def test_choice_displays_options(self, runner, tmp_path, isolated_config):
        """Choice prompts should display numbered options."""
        # Skip analyze, then quit at first hooks prompt
        input_lines = "\n\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        # hooks.trigger choices are shown before the quit
        assert "post-commit" in result.output
        assert "pre-push" in result.output

    def test_choice_marks_current(self, runner, tmp_path, isolated_config):
        """Current choice value should be marked with '<-'."""
        input_lines = "\n\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        # Default trigger is post-commit, should be marked
        assert "<-" in result.output


class TestSetupWizardReset:
    """Test the --reset flag clears user overrides."""

    def test_reset_clears_overrides(self, runner, tmp_path, isolated_config):
        """--reset should remove all user-set values, reverting to defaults."""
        cfg = EvoConfig(path=isolated_config)
        cfg.set("llm.model", "gpt-4")
        cfg.set("sync.privacy_level", 2)
        cfg.set("report.theme", "light")

        assert cfg.get("llm.model") == "gpt-4"

        # 'y' to confirm reset, then quit the wizard immediately
        input_lines = "y\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path), "--reset"],
            input=input_lines,
        )

        assert result.exit_code == 0
        assert "reset to defaults" in result.output.lower()
        # Reload and verify overrides are cleared
        cfg2 = EvoConfig(path=isolated_config)
        assert cfg2.user_overrides() == {}
        assert cfg2.get("llm.model") == _DEFAULTS["llm.model"]
        assert cfg2.get("sync.privacy_level") == _DEFAULTS["sync.privacy_level"]
        assert cfg2.get("report.theme") == _DEFAULTS["report.theme"]

    def test_reset_decline(self, runner, tmp_path, isolated_config):
        """Declining --reset confirmation should keep overrides."""
        cfg = EvoConfig(path=isolated_config)
        cfg.set("llm.model", "gpt-4")

        # 'n' to decline reset, then quit
        input_lines = "n\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path), "--reset"],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg2 = EvoConfig(path=isolated_config)
        assert cfg2.get("llm.model") == "gpt-4"

    def test_reset_then_set_new_values(self, runner, tmp_path, isolated_config):
        """After reset, the wizard should allow setting new values."""
        cfg = EvoConfig(path=isolated_config)
        cfg.set("analyze.families", "git")

        # 'y' to reset, set new analyze.families, then quit
        input_lines = "y\ndependency,ci\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path), "--reset"],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg2 = EvoConfig(path=isolated_config)
        assert cfg2.get("analyze.families") == "dependency,ci"


# ─── Wizard output format ───


class TestSetupWizardOutput:
    """Test the wizard displays correct headers and summaries."""

    def test_header_displayed(self, runner, tmp_path, isolated_config):
        """Wizard should show the header and instructions."""
        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input="q\n",
        )

        assert "Evolution Engine Setup" in result.output
        assert "=" * 40 in result.output
        assert "Press Enter to keep current value" in result.output

    def test_group_labels_displayed(self, runner, tmp_path, isolated_config):
        """All non-empty groups should display their labels."""
        prompt_count = _total_wizard_prompts()
        input_lines = "\n" * (prompt_count + 10)

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        groups = config_groups()
        for gid, info in groups.items():
            keys = config_keys_for_group(gid)
            if keys:
                assert info["label"] in result.output

    def test_completion_message(self, runner, tmp_path, isolated_config):
        """Wizard should show completion message with change count."""
        prompt_count = _total_wizard_prompts()
        input_lines = "\n" * (prompt_count + 10)

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert "Setup complete" in result.output
        assert "setting(s) changed" in result.output
        assert "evo config list" in result.output

    def test_config_path_in_output(self, runner, tmp_path, isolated_config):
        """Wizard should show the config file path at the end."""
        prompt_count = _total_wizard_prompts()
        input_lines = "\n" * (prompt_count + 10)

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert "Config file:" in result.output


# ─── CLI and UI share the same config ───


class TestSetupCLIAndUIShareConfig:
    """Verify CLI and UI both read/write the same EvoConfig."""

    def test_ui_changes_visible_in_config(self, tmp_path):
        """Changes made via SetupUI should be visible when reading EvoConfig."""
        from evolution.setup_ui import SetupUI

        cfg = EvoConfig(path=tmp_path / "config.toml")
        ui = SetupUI(port=0, config=cfg, timeout=0)

        # Simulate a POST to the UI
        body = json.dumps({"llm.model": "claude-opus-4"}).encode("utf-8")
        handler = MagicMock()
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        handler.wfile = BytesIO()
        written = []
        handler.wfile.write = lambda d: written.append(d)

        ui._handle_post(handler)

        # Same config instance should reflect the change
        assert cfg.get("llm.model") == "claude-opus-4"

        # New config instance reading from same file should also see it
        cfg2 = EvoConfig(path=tmp_path / "config.toml")
        assert cfg2.get("llm.model") == "claude-opus-4"

    def test_cli_changes_visible_in_ui(self, tmp_path):
        """Changes made via CLI wizard should be readable by SetupUI."""
        from evolution.setup_ui import SetupUI

        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("report.theme", "light")

        # SetupUI with same config should see the change
        ui = SetupUI(port=0, config=cfg, timeout=0)

        handler = MagicMock()
        handler.headers = {}
        handler.wfile = BytesIO()
        written = []
        handler.wfile.write = lambda d: written.append(d)

        ui._handle_status(handler)

        response = json.loads(b"".join(written))
        assert response["report.theme"] == "light"

    def test_shared_config_object(self, tmp_path):
        """UI and CLI should work with the same EvoConfig class."""
        from evolution.setup_ui import SetupUI

        cfg = EvoConfig(path=tmp_path / "config.toml")

        # CLI sets a value
        cfg.set("sync.privacy_level", 2)

        # UI reads same config
        ui = SetupUI(port=0, config=cfg, timeout=0)
        assert ui.config.get("sync.privacy_level") == 2

        # UI sets a value
        ui.config.set("hooks.trigger", "pre-push")
        assert cfg.get("hooks.trigger") == "pre-push"

    def test_disk_persistence_across_instances(self, tmp_path):
        """Changes from either CLI or UI should persist on disk."""
        from evolution.setup_ui import SetupUI

        cfg_path = tmp_path / "config.toml"

        # Simulate CLI setting
        cfg1 = EvoConfig(path=cfg_path)
        cfg1.set("llm.enabled", True)

        # Simulate UI POST with a separate config instance
        cfg2 = EvoConfig(path=cfg_path)
        ui = SetupUI(port=0, config=cfg2, timeout=0)

        body = json.dumps({"report.theme": "light"}).encode("utf-8")
        handler = MagicMock()
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        handler.wfile = BytesIO()
        handler.wfile.write = lambda d: None

        ui._handle_post(handler)

        # Fresh config should see both changes
        cfg3 = EvoConfig(path=cfg_path)
        assert cfg3.get("llm.enabled") is True
        assert cfg3.get("report.theme") == "light"


# ─── String value handling ───


class TestSetupWizardStringValue:
    """Test setting string values through the wizard."""

    def test_set_string_value(self, runner, tmp_path, isolated_config):
        """Typing a new value on a str prompt should set it."""
        # analyze.families is the first prompt (str type)
        input_lines = "git,ci,dependency\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("analyze.families") == "git,ci,dependency"

    def test_string_same_as_current_no_change(self, runner, tmp_path, isolated_config):
        """Typing the same value as current should not count as a change."""
        cfg = EvoConfig(path=isolated_config)
        cfg.set("analyze.families", "git")

        # Type same value, then quit
        input_lines = "git\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        assert "Saved 0 change(s)" in result.output


# ─── Edge cases ───


class TestSetupEdgeCases:
    """Edge case tests for the setup command."""

    def test_skip_then_continue(self, runner, tmp_path, isolated_config):
        """Skipping one group should move to the next group."""
        # Skip first group (analyze), then see the hooks group header
        # and quit there
        input_lines = "s\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        # Should have reached the hooks group
        assert "Hooks" in result.output

    def test_multiple_changes_counted(self, runner, tmp_path, isolated_config):
        """Multiple setting changes should be counted correctly."""
        # Set analyze.families (str), then analyze.json_output (bool = yes),
        # then quit
        input_lines = "git\nyes\nq\n"

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        assert result.exit_code == 0
        assert "Saved 2 change(s)" in result.output
        cfg = EvoConfig(path=isolated_config)
        assert cfg.get("analyze.families") == "git"
        assert cfg.get("analyze.json_output") is True

    def test_setup_without_flags_shows_wizard(self, runner, tmp_path, isolated_config):
        """Running setup without --ui should show the terminal wizard."""
        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input="q\n",
        )

        assert "Evolution Engine Setup" in result.output
        assert "=" * 40 in result.output

    def test_group_descriptions_shown(self, runner, tmp_path, isolated_config):
        """Group descriptions should appear in the wizard output."""
        prompt_count = _total_wizard_prompts()
        input_lines = "\n" * (prompt_count + 10)

        result = runner.invoke(
            main,
            ["setup", str(tmp_path)],
            input=input_lines,
        )

        # Check at least one group description appears
        assert "What to analyze and output format" in result.output
