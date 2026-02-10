"""Tests for evolution.kb_sync — community pattern sync."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, create_autospec

from evolution.config import EvoConfig
from evolution.kb_sync import KBSync, SyncResult


@pytest.fixture
def evo_dir(tmp_path):
    """Create a minimal .evo directory structure."""
    evo = tmp_path / ".evo"
    evo.mkdir()
    (evo / "phase4").mkdir()
    (evo / "phase5").mkdir()
    return evo


@pytest.fixture
def config(tmp_path):
    """Create a test config."""
    return EvoConfig(path=tmp_path / "config.toml")


class TestKBSyncInit:
    def test_default_privacy_level(self, evo_dir, config):
        sync = KBSync(evo_dir=evo_dir, config=config)
        assert sync.privacy_level == 0

    def test_custom_privacy_level(self, evo_dir, config):
        config.set("sync.privacy_level", 2)
        sync = KBSync(evo_dir=evo_dir, config=config)
        assert sync.privacy_level == 2

    def test_registry_url_from_config(self, evo_dir, config):
        config.set("sync.registry_url", "https://custom.dev/v1")
        sync = KBSync(evo_dir=evo_dir, config=config)
        assert sync.registry_url == "https://custom.dev/v1"

    def test_registry_url_override(self, evo_dir, config):
        sync = KBSync(evo_dir=evo_dir, config=config, registry_url="https://override.dev/v1")
        assert sync.registry_url == "https://override.dev/v1"


class TestPull:
    def test_pull_no_db(self, evo_dir, config):
        """Pull fails gracefully when no knowledge base exists."""
        sync = KBSync(evo_dir=evo_dir, config=config)
        result = sync.pull()
        assert not result.success
        assert "No knowledge base" in result.error

    def test_pull_network_error(self, evo_dir, config):
        """Pull handles network errors gracefully."""
        (evo_dir / "phase4" / "knowledge.db").touch()
        sync = KBSync(evo_dir=evo_dir, config=config)

        with patch.object(sync, "_fetch_patterns", side_effect=ConnectionError("timeout")):
            result = sync.pull()
        assert not result.success
        assert "timeout" in result.error

    def test_pull_empty_response(self, evo_dir, config):
        """Pull succeeds with empty pattern list."""
        (evo_dir / "phase4" / "knowledge.db").touch()
        sync = KBSync(evo_dir=evo_dir, config=config)

        with patch.object(sync, "_fetch_patterns", return_value=[]):
            result = sync.pull()
        assert result.success
        assert result.pulled == 0

    def test_pull_with_patterns(self, evo_dir, config):
        """Pull imports patterns through secure pipeline."""
        (evo_dir / "phase4" / "knowledge.db").touch()
        sync = KBSync(evo_dir=evo_dir, config=config)

        mock_patterns = [{"fingerprint": "abc", "sources": ["git"], "metrics": ["files_touched"]}]

        with patch.object(sync, "_fetch_patterns", return_value=mock_patterns), \
             patch("evolution.kb_export.import_patterns", return_value={
                 "imported": 1, "skipped": 0, "rejected": 0, "errors": []
             }):
            result = sync.pull()
        assert result.success
        assert result.pulled == 1

    def test_pull_updates_sync_state(self, evo_dir, config):
        """Pull updates the sync state file."""
        (evo_dir / "phase4" / "knowledge.db").touch()
        sync = KBSync(evo_dir=evo_dir, config=config)

        with patch.object(sync, "_fetch_patterns", return_value=[{"x": 1}]), \
             patch("evolution.kb_export.import_patterns", return_value={
                 "imported": 3, "skipped": 0, "rejected": 0, "errors": []
             }):
            sync.pull()

        state_path = evo_dir / "sync_state.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert state["total_pulled"] == 3
        assert "last_pull_at" in state


class TestPush:
    def test_push_blocked_at_level_0(self, evo_dir, config):
        """Push is blocked when privacy_level=0."""
        sync = KBSync(evo_dir=evo_dir, config=config)
        result = sync.push()
        assert not result.success
        assert "privacy_level=0" in result.error

    def test_push_no_db(self, evo_dir, config):
        """Push fails when no KB exists."""
        config.set("sync.privacy_level", 2)
        sync = KBSync(evo_dir=evo_dir, config=config)
        result = sync.push()
        assert not result.success
        assert "No knowledge base" in result.error

    def test_push_level_1_metadata(self, evo_dir, config):
        """Level 1 push sends metadata only."""
        config.set("sync.privacy_level", 1)
        (evo_dir / "phase4" / "knowledge.db").touch()
        advisory = {
            "summary": {
                "families_affected": ["git", "ci"],
                "significant_changes": 3,
                "known_patterns_matched": 1,
            }
        }
        (evo_dir / "phase5" / "advisory.json").write_text(json.dumps(advisory))

        sync = KBSync(evo_dir=evo_dir, config=config)

        uploaded_payload = None
        def capture_upload(payload):
            nonlocal uploaded_payload
            uploaded_payload = payload
            return 0

        with patch.object(sync, "_upload_patterns", side_effect=capture_upload):
            result = sync.push()

        assert result.success
        assert uploaded_payload["level"] == 1
        assert "metadata" in uploaded_payload
        assert "patterns" not in uploaded_payload

    def test_push_level_2_patterns(self, evo_dir, config):
        """Level 2 push sends anonymized patterns."""
        config.set("sync.privacy_level", 2)
        (evo_dir / "phase4" / "knowledge.db").touch()

        sync = KBSync(evo_dir=evo_dir, config=config)

        uploaded_payload = None
        def capture_upload(payload):
            nonlocal uploaded_payload
            uploaded_payload = payload
            return 5

        with patch("evolution.kb_export.export_patterns", return_value=[
            {"fingerprint": "abc", "sources": ["git"], "metrics": ["dispersion"]},
        ]), patch.object(sync, "_upload_patterns", side_effect=capture_upload):
            result = sync.push()

        assert result.success
        assert result.pushed == 5
        assert uploaded_payload["level"] == 2
        assert "patterns" in uploaded_payload
        assert "instance_id" in uploaded_payload

    def test_push_network_error(self, evo_dir, config):
        """Push handles network errors."""
        config.set("sync.privacy_level", 2)
        (evo_dir / "phase4" / "knowledge.db").touch()

        sync = KBSync(evo_dir=evo_dir, config=config)

        with patch("evolution.kb_export.export_patterns", return_value=[]), \
             patch.object(sync, "_upload_patterns", side_effect=ConnectionError("refused")):
            result = sync.push()
        assert not result.success
        assert "refused" in result.error


class TestStatus:
    def test_status_no_state(self, evo_dir, config):
        sync = KBSync(evo_dir=evo_dir, config=config)
        result = sync.status()
        assert result.success
        assert result.pulled == 0
        assert result.pushed == 0

    def test_status_with_state(self, evo_dir, config):
        state = {"total_pulled": 10, "total_pushed": 5, "last_pull_at": "2026-02-09T00:00:00Z"}
        (evo_dir / "sync_state.json").write_text(json.dumps(state))

        sync = KBSync(evo_dir=evo_dir, config=config)
        result = sync.status()
        assert result.pulled == 10
        assert result.pushed == 5


class TestSyncResult:
    def test_to_dict(self):
        result = SyncResult(
            action="pull", success=True,
            pulled=3, skipped=1, rejected=0,
            registry_url="https://example.com",
            privacy_level=0,
        )
        d = result.to_dict()
        assert d["action"] == "pull"
        assert d["pulled"] == 3
        assert d["success"] is True
