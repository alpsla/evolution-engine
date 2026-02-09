"""Unit tests for adapter registry auto-detection and plugin discovery."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from evolution.registry import AdapterRegistry, AdapterConfig


@pytest.fixture
def mock_repo(tmp_path):
    """Create a mock repository with common files."""
    # Git
    (tmp_path / ".git").mkdir()

    # Python
    (tmp_path / "requirements.txt").write_text("flask==2.0\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")

    # GitHub Actions
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")

    return tmp_path


@pytest.fixture
def minimal_repo(tmp_path):
    """Create a minimal repo with just git."""
    (tmp_path / ".git").mkdir()
    return tmp_path


class TestTier1Detection:
    def test_detects_git(self, mock_repo):
        registry = AdapterRegistry(mock_repo)
        configs = registry.detect()
        families = [c.family for c in configs]
        assert "version_control" in families

    def test_detects_python_dependency(self, mock_repo):
        registry = AdapterRegistry(mock_repo)
        configs = registry.detect()
        dep_configs = [c for c in configs if c.family == "dependency"]
        assert len(dep_configs) >= 1
        assert dep_configs[0].adapter_name == "pip"

    def test_detects_github_actions_local(self, mock_repo):
        registry = AdapterRegistry(mock_repo)
        configs = registry.detect()
        ci_configs = [c for c in configs if c.family == "ci"]
        assert len(ci_configs) >= 1
        assert ci_configs[0].adapter_name == "github_actions_local"

    def test_deduplicates_same_adapter(self, mock_repo):
        """requirements.txt and pyproject.toml should only produce one pip adapter."""
        registry = AdapterRegistry(mock_repo)
        configs = registry.detect()
        pip_configs = [c for c in configs if c.adapter_name == "pip"]
        assert len(pip_configs) == 1

    def test_minimal_repo_detects_git_only(self, minimal_repo):
        registry = AdapterRegistry(minimal_repo)
        configs = registry.detect()
        assert len(configs) == 1
        assert configs[0].family == "version_control"

    def test_npm_detection(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "package-lock.json").write_text("{}\n")
        registry = AdapterRegistry(tmp_path)
        configs = registry.detect()
        npm = [c for c in configs if c.adapter_name == "npm"]
        assert len(npm) == 1

    def test_go_detection(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "go.mod").write_text("module test\n")
        registry = AdapterRegistry(tmp_path)
        configs = registry.detect()
        go = [c for c in configs if c.adapter_name == "go"]
        assert len(go) == 1

    def test_cargo_detection(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "Cargo.lock").write_text("")
        registry = AdapterRegistry(tmp_path)
        configs = registry.detect()
        cargo = [c for c in configs if c.adapter_name == "cargo"]
        assert len(cargo) == 1

    def test_terraform_detection(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "main.tf").write_text("resource \"aws_s3_bucket\" {}\n")
        registry = AdapterRegistry(tmp_path)
        configs = registry.detect()
        tf = [c for c in configs if c.adapter_name == "terraform"]
        assert len(tf) == 1

    def test_docker_detection(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "Dockerfile").write_text("FROM python:3.11\n")
        registry = AdapterRegistry(tmp_path)
        configs = registry.detect()
        docker = [c for c in configs if c.adapter_name == "docker"]
        assert len(docker) == 1


class TestTier2Detection:
    def test_github_token_unlocks_tier2(self, mock_repo, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        registry = AdapterRegistry(mock_repo)
        configs = registry.detect(tokens={"github_token": "ghp_test123"})
        tier2 = [c for c in configs if c.tier == 2]
        assert len(tier2) >= 1
        tier2_families = set(c.family for c in tier2)
        assert "ci" in tier2_families
        assert "deployment" in tier2_families
        assert "security" in tier2_families

    def test_no_token_no_tier2(self, mock_repo, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        registry = AdapterRegistry(mock_repo)
        configs = registry.detect()
        tier2 = [c for c in configs if c.tier == 2]
        assert len(tier2) == 0

    def test_env_var_token(self, mock_repo, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
        registry = AdapterRegistry(mock_repo)
        configs = registry.detect()
        tier2 = [c for c in configs if c.tier == 2]
        assert len(tier2) >= 1


class TestExplainMissing:
    def test_shows_missing_github_token(self, mock_repo, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        registry = AdapterRegistry(mock_repo)
        messages = registry.explain_missing()
        assert len(messages) >= 1
        assert any("GITHUB_TOKEN" in m for m in messages)

    def test_no_messages_when_all_tokens_present(self, mock_repo, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("GITLAB_TOKEN", "glpat_test")
        monkeypatch.setenv("JENKINS_URL", "http://jenkins")
        registry = AdapterRegistry(mock_repo)
        messages = registry.explain_missing()
        assert len(messages) == 0


class TestPluginDetection:
    """Test Tier 3 plugin discovery via entry_points."""

    def _make_mock_plugin(self, descriptors, name="test_plugin"):
        """Create a mock entry point that returns descriptors."""
        ep = MagicMock()
        ep.name = name
        ep.load.return_value = lambda: descriptors
        return ep

    def test_plugin_file_pattern_detected(self, tmp_path, monkeypatch):
        """Plugin with file pattern detected when file exists."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "bitbucket-pipelines.yml").write_text("image: python:3.11\n")

        plugin_descriptors = [{
            "pattern": "bitbucket-pipelines.yml",
            "adapter_name": "bitbucket_pipelines",
            "family": "ci",
            "adapter_class": "evo_bitbucket.BitbucketAdapter",
        }]

        mock_ep = self._make_mock_plugin(plugin_descriptors, "evo-adapter-bitbucket")

        with patch("evolution.registry.entry_points", return_value=[mock_ep]):
            registry = AdapterRegistry(tmp_path)
            configs = registry.detect()
            plugin_configs = [c for c in configs if c.tier == 3]
            assert len(plugin_configs) == 1
            assert plugin_configs[0].adapter_name == "bitbucket_pipelines"
            assert plugin_configs[0].family == "ci"
            assert plugin_configs[0].adapter_class == "evo_bitbucket.BitbucketAdapter"
            assert plugin_configs[0].plugin_name == "evo-adapter-bitbucket"

    def test_plugin_file_pattern_not_detected(self, tmp_path, monkeypatch):
        """Plugin with file pattern NOT detected when file doesn't exist."""
        (tmp_path / ".git").mkdir()

        plugin_descriptors = [{
            "pattern": "bitbucket-pipelines.yml",
            "adapter_name": "bitbucket_pipelines",
            "family": "ci",
        }]

        mock_ep = self._make_mock_plugin(plugin_descriptors)

        with patch("evolution.registry.entry_points", return_value=[mock_ep]):
            registry = AdapterRegistry(tmp_path)
            configs = registry.detect()
            plugin_configs = [c for c in configs if c.tier == 3]
            assert len(plugin_configs) == 0

    def test_plugin_token_detected(self, tmp_path, monkeypatch):
        """Plugin with token requirement detected when token provided."""
        (tmp_path / ".git").mkdir()
        monkeypatch.setenv("BITBUCKET_TOKEN", "bb_test123")

        plugin_descriptors = [{
            "token_key": "bitbucket_token",
            "adapter_name": "bitbucket_api",
            "family": "ci",
            "adapter_class": "evo_bitbucket.BitbucketAPIAdapter",
        }]

        mock_ep = self._make_mock_plugin(plugin_descriptors)

        with patch("evolution.registry.entry_points", return_value=[mock_ep]):
            registry = AdapterRegistry(tmp_path)
            configs = registry.detect()
            plugin_configs = [c for c in configs if c.tier == 3]
            assert len(plugin_configs) == 1
            assert plugin_configs[0].adapter_name == "bitbucket_api"

    def test_plugin_token_missing(self, tmp_path, monkeypatch):
        """Plugin with token requirement NOT detected when token missing."""
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)

        plugin_descriptors = [{
            "token_key": "bitbucket_token",
            "adapter_name": "bitbucket_api",
            "family": "ci",
        }]

        mock_ep = self._make_mock_plugin(plugin_descriptors)

        with patch("evolution.registry.entry_points", return_value=[mock_ep]):
            registry = AdapterRegistry(tmp_path)
            configs = registry.detect()
            plugin_configs = [c for c in configs if c.tier == 3]
            assert len(plugin_configs) == 0

    def test_plugin_dedup_with_builtin(self, mock_repo):
        """Plugin adapter doesn't duplicate a built-in adapter."""
        # "pip" + "dependency" already detected by built-in Tier 1
        plugin_descriptors = [{
            "pattern": "requirements.txt",
            "adapter_name": "pip",
            "family": "dependency",
        }]

        mock_ep = self._make_mock_plugin(plugin_descriptors)

        with patch("evolution.registry.entry_points", return_value=[mock_ep]):
            registry = AdapterRegistry(mock_repo)
            configs = registry.detect()
            pip_configs = [c for c in configs if c.adapter_name == "pip"]
            # Should still be 1, not 2
            assert len(pip_configs) == 1
            assert pip_configs[0].tier == 1  # built-in wins

    def test_plugin_bad_return_type(self, tmp_path):
        """Plugin that returns non-list is skipped gracefully."""
        (tmp_path / ".git").mkdir()

        ep = MagicMock()
        ep.name = "bad_plugin"
        ep.load.return_value = lambda: "not a list"

        with patch("evolution.registry.entry_points", return_value=[ep]):
            registry = AdapterRegistry(tmp_path)
            configs = registry.detect()
            plugin_configs = [c for c in configs if c.tier == 3]
            assert len(plugin_configs) == 0

    def test_plugin_missing_required_fields(self, tmp_path):
        """Plugin descriptor without adapter_name/family is skipped."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "something.yml").write_text("test\n")

        plugin_descriptors = [{"pattern": "something.yml"}]  # missing adapter_name, family
        mock_ep = self._make_mock_plugin(plugin_descriptors)

        with patch("evolution.registry.entry_points", return_value=[mock_ep]):
            registry = AdapterRegistry(tmp_path)
            configs = registry.detect()
            plugin_configs = [c for c in configs if c.tier == 3]
            assert len(plugin_configs) == 0

    def test_plugin_load_failure(self, tmp_path):
        """Plugin that raises on load is skipped gracefully."""
        (tmp_path / ".git").mkdir()

        ep = MagicMock()
        ep.name = "broken_plugin"
        ep.load.side_effect = ImportError("missing dep")

        with patch("evolution.registry.entry_points", return_value=[ep]):
            registry = AdapterRegistry(tmp_path)
            configs = registry.detect()
            # Should not crash — just skip the broken plugin
            assert any(c.family == "version_control" for c in configs)

    def test_list_plugins(self, tmp_path):
        """list_plugins() returns installed plugin info."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "bitbucket-pipelines.yml").write_text("test\n")

        plugin_descriptors = [{
            "pattern": "bitbucket-pipelines.yml",
            "adapter_name": "bitbucket_pipelines",
            "family": "ci",
            "adapter_class": "evo_bitbucket.BitbucketAdapter",
        }]

        mock_ep = self._make_mock_plugin(plugin_descriptors, "evo-adapter-bitbucket")

        with patch("evolution.registry.entry_points", return_value=[mock_ep]):
            registry = AdapterRegistry(tmp_path)
            plugins = registry.list_plugins()
            assert len(plugins) == 1
            assert plugins[0]["plugin_name"] == "evo-adapter-bitbucket"
            assert plugins[0]["adapter_name"] == "bitbucket_pipelines"
            assert plugins[0]["detected"] is True

    def test_explain_missing_includes_plugins(self, tmp_path, monkeypatch):
        """explain_missing() reports token needs from plugins too."""
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)

        plugin_descriptors = [{
            "token_key": "bitbucket_token",
            "adapter_name": "bitbucket_api",
            "family": "ci",
        }]

        mock_ep = self._make_mock_plugin(plugin_descriptors, "evo-adapter-bitbucket")

        with patch("evolution.registry.entry_points", return_value=[mock_ep]):
            registry = AdapterRegistry(tmp_path)
            messages = registry.explain_missing()
            assert any("BITBUCKET_TOKEN" in m for m in messages)


class TestSummary:
    def test_summary_structure(self, mock_repo, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        registry = AdapterRegistry(mock_repo)
        summary = registry.summary()
        assert "repo_path" in summary
        assert "adapters_detected" in summary
        assert "families" in summary
        assert "tier1_count" in summary
        assert "tier2_count" in summary
        assert "plugin_count" in summary
        assert summary["tier1_count"] > 0

    def test_self_detection(self):
        """Registry should detect adapters in the evolution-engine repo itself."""
        repo_path = Path(__file__).resolve().parent.parent.parent
        registry = AdapterRegistry(repo_path)
        configs = registry.detect()
        families = set(c.family for c in configs)
        assert "version_control" in families
        assert "dependency" in families  # pyproject.toml
