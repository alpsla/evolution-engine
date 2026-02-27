"""
Tests for the telemetry module (evolution/telemetry.py).
"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from evolution.telemetry import (
    _get_anon_id,
    _is_enabled,
    prompt_consent,
    track_event,
    track_analyze,
    track_investigate,
    track_fix,
    track_verify,
    track_accept,
    track_sources,
    track_license_check,
    track_adapter_execution,
    track_pattern_sync,
    track_error,
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


class TestTypedHelpers:
    """Test typed telemetry helper functions."""

    @patch("evolution.telemetry.track_event")
    def test_track_analyze(self, mock_track):
        """track_analyze sends analyze_complete with correct schema."""
        track_analyze(
            license_tier="pro",
            duration_seconds=12.345,
            total_events=100,
            active_families_count=3,
            patterns_matched=5,
            significant_changes_count=2,
            gated_families_count=1,
            has_diagnostics=True,
            run_number=7,
        )
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "analyze_complete"
        assert props["license_tier"] == "pro"
        assert props["duration_seconds"] == 12.3  # rounded to 1 decimal
        assert props["total_events"] == 100
        assert props["active_families_count"] == 3
        assert props["patterns_matched"] == 5
        assert props["significant_changes_count"] == 2
        assert props["gated_families_count"] == 1
        assert props["has_diagnostics"] is True
        assert props["run_number"] == 7

    @patch("evolution.telemetry.track_event")
    def test_track_investigate(self, mock_track):
        """track_investigate sends investigate with correct schema."""
        track_investigate(
            agent="anthropic",
            duration_seconds=5.678,
            success=True,
            finding_count=3,
        )
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "investigate"
        assert props["agent"] == "anthropic"
        assert props["duration_seconds"] == 5.7
        assert props["success"] is True
        assert props["finding_count"] == 3

    @patch("evolution.telemetry.track_event")
    def test_track_fix(self, mock_track):
        """track_fix sends fix with correct schema."""
        track_fix(
            iterations=3,
            resolved=2,
            status="partial",
            duration_seconds=45.123,
            termination_reason="max_iterations",
            dry_run=False,
        )
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "fix"
        assert props["iterations"] == 3
        assert props["resolved"] == 2
        assert props["status"] == "partial"
        assert props["duration_seconds"] == 45.1
        assert props["dry_run"] is False

    @patch("evolution.telemetry.track_event")
    def test_track_verify(self, mock_track):
        """track_verify sends verify with correct schema."""
        track_verify(
            duration_seconds=2.999,
            changes_resolved=5,
            changes_persisting=1,
            changes_new=0,
        )
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "verify"
        assert props["duration_seconds"] == 3.0  # rounded
        assert props["changes_resolved"] == 5
        assert props["changes_persisting"] == 1
        assert props["changes_new"] == 0

    @patch("evolution.telemetry.track_event")
    def test_track_accept(self, mock_track):
        """track_accept sends accept with correct schema."""
        track_accept(scope="permanent", count=2, family="ci,deployment")
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "accept"
        assert props["scope"] == "permanent"
        assert props["count"] == 2
        assert props["family"] == "ci,deployment"

    @patch("evolution.telemetry.track_event")
    def test_track_sources(self, mock_track):
        """track_sources sends sources with correct schema."""
        track_sources(families_detected=4, tier2_available=2)
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "sources"
        assert props["families_detected"] == 4
        assert props["tier2_available"] == 2

    @patch("evolution.telemetry.track_event")
    def test_track_license_check(self, mock_track):
        """track_license_check sends license_check with correct schema."""
        track_license_check(
            tier="pro", source="config", valid=True, days_to_expiry=28,
        )
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "license_check"
        assert props["tier"] == "pro"
        assert props["valid"] is True
        assert props["days_to_expiry"] == 28

    @patch("evolution.telemetry.track_event")
    def test_track_adapter_execution(self, mock_track):
        """track_adapter_execution sends adapter_execution with correct schema."""
        track_adapter_execution(
            family="ci", tier=2, event_count=150,
            duration_ms=1234, success=True,
        )
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "adapter_execution"
        assert props["family"] == "ci"
        assert props["tier"] == 2
        assert props["event_count"] == 150
        assert props["duration_ms"] == 1234
        assert props["success"] is True

    @patch("evolution.telemetry.track_event")
    def test_track_pattern_sync(self, mock_track):
        """track_pattern_sync sends pattern_sync with correct schema."""
        track_pattern_sync(
            action="pull", count=12, rejected=1, source="registry",
        )
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "pattern_sync"
        assert props["action"] == "pull"
        assert props["count"] == 12
        assert props["rejected"] == 1

    @patch("evolution.telemetry.track_event")
    def test_track_error_class_name_only(self, mock_track):
        """track_error sends only exception class name, never paths or traces."""
        track_error(
            error_type="evolution.orchestrator.PipelineError",
            command="analyze",
        )
        mock_track.assert_called_once()
        name, props = mock_track.call_args[0]
        assert name == "error"
        # Module path should be stripped — class name only
        assert props["error_type"] == "PipelineError"
        assert props["command"] == "analyze"
        # Ensure no stack trace or file path fields
        assert "traceback" not in props
        assert "file" not in props
        assert "path" not in props

    @patch("evolution.telemetry.track_event")
    def test_track_error_simple_name(self, mock_track):
        """track_error preserves simple class names without dots."""
        track_error(error_type="ValueError", command="fix")
        name, props = mock_track.call_args[0]
        assert props["error_type"] == "ValueError"

    @patch("evolution.telemetry.track_event")
    def test_duration_rounding(self, mock_track):
        """Duration values should be rounded to 1 decimal place."""
        track_analyze(duration_seconds=1.999)
        props = mock_track.call_args[0][1]
        assert props["duration_seconds"] == 2.0

        mock_track.reset_mock()
        track_fix(duration_seconds=0.04)
        props = mock_track.call_args[0][1]
        assert props["duration_seconds"] == 0.0

    @patch("evolution.telemetry._is_enabled", return_value=True)
    @patch("evolution.telemetry.threading.Thread")
    def test_user_agent_header(self, mock_thread_cls, mock_enabled):
        """HTTP request should include evo-cli User-Agent header."""
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        track_event("test_event", {"key": "value"})

        # Get the target function that would run in the thread
        call_kwargs = mock_thread_cls.call_args
        target_fn = call_kwargs[1]["target"] if "target" in call_kwargs[1] else call_kwargs[0][0]

        # Execute the target to verify the request is built correctly
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch("evolution.telemetry._get_anon_id", return_value="test-id"), \
             patch("evolution.telemetry._get_version", return_value="0.2.2"):
            target_fn()
            req = mock_urlopen.call_args[0][0]
            assert "evo-cli/" in req.get_header("User-agent")
