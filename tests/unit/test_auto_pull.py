"""Tests for auto-pull community patterns in orchestrator."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.orchestrator import Orchestrator


@pytest.fixture
def evo_dir(tmp_path):
    """Create a minimal .evo directory structure."""
    evo = tmp_path / ".evo"
    evo.mkdir()
    (evo / "phase4").mkdir()
    return evo


def _mock_log(*args, **kwargs):
    pass


class TestAutoPullCommunityPatterns:
    """Tests for Orchestrator._auto_pull_community_patterns()."""

    def test_skipped_when_disabled(self, evo_dir, tmp_path):
        """Auto-pull does nothing when sync.auto_pull is False (default)."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.evo_dir = evo_dir

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = False  # auto_pull disabled

        with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.kb_sync.KBSync") as MockSync:
            orch._auto_pull_community_patterns(_mock_log)
            MockSync.assert_not_called()

    def test_pulls_when_enabled_and_no_recent_check(self, evo_dir):
        """Auto-pull calls KBSync.pull() when enabled and no recent check."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.evo_dir = evo_dir

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = True  # auto_pull enabled

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.pulled = 3

        with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.kb_sync.KBSync") as MockSync:
            MockSync.return_value.pull.return_value = mock_result
            messages = []
            orch._auto_pull_community_patterns(lambda msg: messages.append(msg))
            MockSync.return_value.pull.assert_called_once()
            assert any("3" in m for m in messages)

    def test_throttled_within_24h(self, evo_dir):
        """Auto-pull skips when last pull was within 24 hours."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.evo_dir = evo_dir

        # Write a recent sync state
        sync_state = {
            "last_pull_at": datetime.now(timezone.utc).isoformat(),
        }
        (evo_dir / "sync_state.json").write_text(json.dumps(sync_state))

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = True  # auto_pull enabled

        with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.kb_sync.KBSync") as MockSync:
            orch._auto_pull_community_patterns(_mock_log)
            MockSync.assert_not_called()  # Should be throttled

    def test_pulls_after_24h(self, evo_dir):
        """Auto-pull proceeds when last pull was more than 24 hours ago."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.evo_dir = evo_dir

        # Write an old sync state (>24h ago)
        old_time = "2025-01-01T00:00:00+00:00"
        sync_state = {"last_pull_at": old_time}
        (evo_dir / "sync_state.json").write_text(json.dumps(sync_state))

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = True

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.pulled = 0

        with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.kb_sync.KBSync") as MockSync:
            MockSync.return_value.pull.return_value = mock_result
            orch._auto_pull_community_patterns(_mock_log)
            MockSync.return_value.pull.assert_called_once()

    def test_failure_is_silent(self, evo_dir):
        """Auto-pull failures are logged but don't raise."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.evo_dir = evo_dir

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = True

        with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.kb_sync.KBSync", side_effect=Exception("network error")):
            # Should not raise
            orch._auto_pull_community_patterns(_mock_log)

    def test_no_sync_state_file(self, evo_dir):
        """Auto-pull works when sync_state.json doesn't exist yet."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.evo_dir = evo_dir

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = True

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.pulled = 5

        with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.kb_sync.KBSync") as MockSync:
            MockSync.return_value.pull.return_value = mock_result
            messages = []
            orch._auto_pull_community_patterns(lambda msg: messages.append(msg))
            MockSync.return_value.pull.assert_called_once()
            assert any("5" in m for m in messages)
