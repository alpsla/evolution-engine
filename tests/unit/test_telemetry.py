"""
Tests for the telemetry module (evolution/telemetry.py).
"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from evolution.telemetry import (
    _get_anon_id,
    _is_enabled,
    prompt_consent,
    track_event,
)


class TestTelemetryEnabled:
    """Test telemetry enabled/disabled logic."""

    def test_disabled_by_default(self, monkeypatch, tmp_path):
        """Telemetry should be disabled by default."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / ".evo"))
        assert _is_enabled() is False

    def test_respects_do_not_track(self, monkeypatch, tmp_path):
        """DO_NOT_TRACK=1 should disable telemetry even if config says enabled."""
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("telemetry.enabled = true\n")
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        assert _is_enabled() is False

    def test_enabled_when_configured(self, monkeypatch, tmp_path):
        """Telemetry should be enabled when config says so."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("telemetry.enabled = true\n")
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        assert _is_enabled() is True

    def test_disabled_when_configured_false(self, monkeypatch, tmp_path):
        """Telemetry should be disabled when config explicitly false."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("telemetry.enabled = false\n")
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        assert _is_enabled() is False


class TestAnonId:
    """Test anonymous ID generation."""

    def test_generates_uuid(self, monkeypatch, tmp_path):
        """Should generate a valid UUID4."""
        config_dir = tmp_path / ".evo"
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        anon_id = _get_anon_id()
        assert len(anon_id) == 36  # UUID4 format
        assert "-" in anon_id

    def test_persists_across_calls(self, monkeypatch, tmp_path):
        """Same ID should be returned on subsequent calls."""
        config_dir = tmp_path / ".evo"
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        id1 = _get_anon_id()
        id2 = _get_anon_id()
        assert id1 == id2

    def test_reads_existing_id(self, monkeypatch, tmp_path):
        """Should read an existing anon_id file."""
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        (config_dir / "anon_id").write_text("test-id-12345")
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        assert _get_anon_id() == "test-id-12345"


class TestTrackEvent:
    """Test event tracking."""

    def test_no_op_when_disabled(self, monkeypatch, tmp_path):
        """track_event should be a no-op when disabled."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / ".evo"))
        # Should not raise
        track_event("test_event", {"key": "value"})

    @patch("evolution.telemetry._is_enabled", return_value=True)
    @patch("evolution.telemetry.threading.Thread")
    def test_fires_background_thread_when_enabled(self, mock_thread_cls, mock_enabled):
        """Should start a background thread when enabled."""
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread
        track_event("test_event", {"key": "value"})
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    def test_non_blocking_on_network_failure(self, monkeypatch, tmp_path):
        """track_event should never block or raise on network failure."""
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("telemetry.enabled = true\n")
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)

        # Patch urlopen to raise
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            # Should not raise
            track_event("test_event", {"key": "value"})


class TestPromptConsent:
    """Test consent prompting."""

    def test_skips_when_do_not_track(self, monkeypatch, tmp_path):
        """Should skip prompt when DO_NOT_TRACK is set."""
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / ".evo"))
        # Should not prompt
        prompt_consent()

    def test_skips_when_not_interactive(self, monkeypatch, tmp_path):
        """Should skip prompt when not in interactive terminal."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / ".evo"))
        # Mock stdin.isatty() to return False (non-interactive)
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            prompt_consent()

    def test_skips_when_already_prompted(self, monkeypatch, tmp_path):
        """Should not prompt again if already prompted."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("telemetry.prompted = true\n")
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        with patch("sys.stdin") as mock_stdin, \
             patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = True
            # Should not call input()
            with patch("builtins.input", side_effect=AssertionError("should not be called")):
                prompt_consent()

    def test_prompt_yes_enables(self, monkeypatch, tmp_path):
        """Answering 'y' should enable telemetry."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        with patch("sys.stdin") as mock_stdin, \
             patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = True
            with patch("builtins.input", return_value="y"), \
                 patch("builtins.print"):
                prompt_consent()

        from evolution.config import EvoConfig
        cfg = EvoConfig(path=config_dir / "config.toml")
        assert cfg.get("telemetry.enabled") is True
        assert cfg.get("telemetry.prompted") is True

    def test_prompt_no_disables(self, monkeypatch, tmp_path):
        """Answering 'N' (default) should disable telemetry."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        with patch("sys.stdin") as mock_stdin, \
             patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = True
            with patch("builtins.input", return_value=""), \
                 patch("builtins.print"):
                prompt_consent()

        from evolution.config import EvoConfig
        cfg = EvoConfig(path=config_dir / "config.toml")
        assert cfg.get("telemetry.enabled") is False
        assert cfg.get("telemetry.prompted") is True

    def test_eof_marks_prompted(self, monkeypatch, tmp_path):
        """EOFError (non-interactive pipe) should mark as prompted, leave disabled."""
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        config_dir = tmp_path / ".evo"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("EVO_CONFIG_DIR", str(config_dir))
        with patch("sys.stdin") as mock_stdin, \
             patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = True
            with patch("builtins.input", side_effect=EOFError), \
                 patch("builtins.print"):
                prompt_consent()

        from evolution.config import EvoConfig
        cfg = EvoConfig(path=config_dir / "config.toml")
        assert cfg.get("telemetry.prompted") is True
        assert cfg.get("telemetry.enabled", False) is False
