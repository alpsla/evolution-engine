"""
Unit tests for adapter blocklist + trust tier mechanism (evolution/registry.py).

Tests blocklist loading, merging, filtering, block/unblock operations,
and trust level auto-assignment for all 4 tiers.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from evolution.registry import AdapterRegistry, AdapterConfig


@pytest.fixture
def repo_with_git(tmp_path):
    """Create a minimal repo with .git/ for detection."""
    (tmp_path / ".git").mkdir()
    return tmp_path


# ─── Blocklist Loading ───


class TestBlocklistLoading:
    def test_empty_blocklist_allows_all(self, repo_with_git):
        registry = AdapterRegistry(repo_with_git)
        configs = registry.detect()
        # Git should be detected without blocklist interference
        assert any(c.adapter_name == "git" for c in configs)

    def test_bundled_blocklist_filters_adapters(self, repo_with_git, tmp_path, monkeypatch):
        """Local blocklist.json blocks matching adapters from detection."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        blocklist_path = tmp_path / ".evo" / "blocklist.json"
        blocklist_path.parent.mkdir(parents=True, exist_ok=True)
        blocklist_path.write_text(json.dumps([{"name": "git", "reason": "test block"}]))

        registry = AdapterRegistry(repo_with_git)
        configs = registry.detect()
        assert not any(c.adapter_name == "git" for c in configs)

    def test_local_blocklist_filters_adapters(self, repo_with_git, tmp_path, monkeypatch):
        """Local ~/.evo/blocklist.json filters matching adapters."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        blocklist_path = tmp_path / ".evo" / "blocklist.json"
        blocklist_path.parent.mkdir(parents=True, exist_ok=True)
        blocklist_path.write_text(json.dumps([{"name": "git", "reason": "blocked for testing"}]))

        registry = AdapterRegistry(repo_with_git)
        configs = registry.detect()

        # git should not appear in detected
        assert not any(c.adapter_name == "git" for c in configs)

        # But should appear in blocked
        blocked = registry.get_blocked()
        assert any(b["adapter_name"] == "git" for b in blocked)


# ─── Block/Unblock Operations ───


class TestBlockUnblock:
    def test_block_adds_to_local_blocklist(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = AdapterRegistry.block_adapter("test-adapter", reason="malicious")
        assert result is True

        blocklist_path = tmp_path / ".evo" / "blocklist.json"
        assert blocklist_path.exists()
        data = json.loads(blocklist_path.read_text())
        assert len(data) == 1
        assert data[0]["name"] == "test-adapter"
        assert data[0]["reason"] == "malicious"

    def test_block_duplicate_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        AdapterRegistry.block_adapter("test-adapter")
        result = AdapterRegistry.block_adapter("test-adapter")
        assert result is False

    def test_unblock_removes_from_blocklist(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        AdapterRegistry.block_adapter("test-adapter", reason="test")
        result = AdapterRegistry.unblock_adapter("test-adapter")
        assert result is True

        blocklist_path = tmp_path / ".evo" / "blocklist.json"
        data = json.loads(blocklist_path.read_text())
        assert len(data) == 0

    def test_unblock_nonexistent_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = AdapterRegistry.unblock_adapter("nonexistent")
        assert result is False

    def test_block_unblock_roundtrip(self, repo_with_git, tmp_path, monkeypatch):
        """Block then unblock restores original detection."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        registry = AdapterRegistry(repo_with_git)

        # Initially git is detected
        configs = registry.detect()
        assert any(c.adapter_name == "git" for c in configs)

        # Block it
        AdapterRegistry.block_adapter("git", reason="testing")
        registry2 = AdapterRegistry(repo_with_git)
        configs2 = registry2.detect()
        assert not any(c.adapter_name == "git" for c in configs2)

        # Unblock it
        AdapterRegistry.unblock_adapter("git")
        registry3 = AdapterRegistry(repo_with_git)
        configs3 = registry3.detect()
        assert any(c.adapter_name == "git" for c in configs3)


# ─── Trust Levels ───


class TestTrustLevels:
    def test_tier1_adapters_are_builtin(self, repo_with_git):
        registry = AdapterRegistry(repo_with_git)
        configs = registry.detect()
        for c in configs:
            if c.tier == 1:
                assert c.trust_level == "built-in"

    def test_tier2_adapters_are_builtin(self, repo_with_git, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        registry = AdapterRegistry(repo_with_git)
        configs = registry.detect()
        for c in configs:
            if c.tier == 2:
                assert c.trust_level == "built-in"

    def test_get_blocked_includes_reason(self, repo_with_git, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        blocklist_path = tmp_path / ".evo" / "blocklist.json"
        blocklist_path.parent.mkdir(parents=True, exist_ok=True)
        blocklist_path.write_text(json.dumps([{"name": "git", "reason": "security issue"}]))

        registry = AdapterRegistry(repo_with_git)
        registry.detect()
        blocked = registry.get_blocked()
        assert len(blocked) >= 1
        assert blocked[0]["reason"] == "security issue"


# ─── Trust Level Auto-Assignment (all 4 tiers) ───


class TestTrustLevelAutoAssignment:
    """Test the _determine_trust_level logic for Tier 3 plugins."""

    def test_verified_when_in_verified_list(self, repo_with_git, tmp_path, monkeypatch):
        """Tier 3 plugin in verified_adapters.json gets 'verified' badge."""
        # Write a verified list that includes our test plugin
        verified_path = tmp_path / "verified_adapters.json"
        verified_path.write_text(json.dumps(["evo-adapter-jenkins"]))

        registry = AdapterRegistry(repo_with_git)
        # Override _load_verified to use our test file
        registry._verified = {"evo-adapter-jenkins"}

        trust = registry._determine_trust_level("evo-adapter-jenkins", registry._verified)
        assert trust == "verified"

    def test_community_when_has_pypi_version(self, repo_with_git):
        """Tier 3 plugin with version metadata gets 'community' badge."""
        registry = AdapterRegistry(repo_with_git)
        verified_set = set()

        # evolution-engine itself has version metadata — simulate a plugin with it
        with patch("importlib.metadata.version", return_value="1.0.0"):
            trust = registry._determine_trust_level("some-published-pkg", verified_set)
        assert trust == "community"

    def test_local_when_no_pypi_version(self, repo_with_git):
        """Tier 3 plugin without version metadata gets 'local' badge."""
        registry = AdapterRegistry(repo_with_git)
        verified_set = set()

        import importlib.metadata
        with patch("importlib.metadata.version",
                   side_effect=importlib.metadata.PackageNotFoundError("nope")):
            trust = registry._determine_trust_level("dev-only-pkg", verified_set)
        assert trust == "local"

    def test_local_when_no_plugin_name(self, repo_with_git):
        """Tier 3 plugin with empty plugin_name gets 'local' badge."""
        registry = AdapterRegistry(repo_with_git)
        trust = registry._determine_trust_level("", set())
        assert trust == "local"

    def test_verified_takes_precedence_over_community(self, repo_with_git):
        """Verified list check happens before PyPI version check."""
        registry = AdapterRegistry(repo_with_git)
        verified_set = {"my-pkg"}

        # Even if it has a PyPI version, verified should win
        with patch("importlib.metadata.version", return_value="2.0.0"):
            trust = registry._determine_trust_level("my-pkg", verified_set)
        assert trust == "verified"

    def test_tier3_plugin_gets_trust_in_detect(self, repo_with_git, monkeypatch):
        """Full detect() assigns trust_level to Tier 3 plugin configs."""
        # Create a Jenkinsfile so the plugin's file pattern matches
        (repo_with_git / "Jenkinsfile").write_text("pipeline {}")

        # Mock plugin discovery to return a fake plugin
        fake_plugins = [{
            "pattern": "Jenkinsfile",
            "adapter_name": "jenkins",
            "family": "ci",
            "adapter_class": "evo_jenkins.JenkinsAdapter",
            "_plugin_name": "evo-adapter-jenkins",
        }]
        registry = AdapterRegistry(repo_with_git)
        registry._plugin_detectors = fake_plugins

        # Mock: not verified, no PyPI version → local
        import importlib.metadata
        with patch("importlib.metadata.version",
                   side_effect=importlib.metadata.PackageNotFoundError("nope")):
            configs = registry.detect()

        jenkins = [c for c in configs if c.adapter_name == "jenkins"]
        assert len(jenkins) == 1
        assert jenkins[0].trust_level == "local"
        assert jenkins[0].tier == 3
