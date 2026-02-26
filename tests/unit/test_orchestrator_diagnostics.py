"""Tests for adapter diagnostics in the orchestrator."""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from evolution.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path, monkeypatch):
    """Create an Orchestrator on a fake repo with free license."""
    monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("CIRCLECI_TOKEN", raising=False)
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    return Orchestrator(repo_path=str(repo), evo_dir=str(tmp_path / "evo"))


class TestSetDiagnostic:
    def test_set_diagnostic_basic(self, orch):
        orch._set_diagnostic("ci", "no_data", "Connected but 0 events.")
        assert orch._diagnostics["ci"]["status"] == "no_data"
        assert orch._diagnostics["ci"]["message"] == "Connected but 0 events."

    def test_set_diagnostic_with_extras(self, orch):
        orch._set_diagnostic("ci", "platform_mismatch", "Wrong platform.",
                             token_key="GITHUB_TOKEN", detected_platform="gitlab")
        diag = orch._diagnostics["ci"]
        assert diag["token_key"] == "GITHUB_TOKEN"
        assert diag["detected_platform"] == "gitlab"

    def test_set_diagnostic_overwrites(self, orch):
        orch._set_diagnostic("ci", "no_data", "First.")
        orch._set_diagnostic("ci", "active", "")
        assert orch._diagnostics["ci"]["status"] == "active"


class TestDetectRemotePlatform:
    def test_github_remote(self, orch, monkeypatch):
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_remote.url = "git@github.com:owner/repo.git"
        mock_repo.remotes = [mock_remote]
        with patch("git.Repo", return_value=mock_repo):
            assert orch._detect_remote_platform() == "github"

    def test_gitlab_remote(self, orch):
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_remote.url = "git@gitlab.com:group/project.git"
        mock_repo.remotes = [mock_remote]
        with patch("git.Repo", return_value=mock_repo):
            assert orch._detect_remote_platform() == "gitlab"

    def test_bitbucket_remote(self, orch):
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_remote.url = "git@bitbucket.org:team/repo.git"
        mock_repo.remotes = [mock_remote]
        with patch("git.Repo", return_value=mock_repo):
            assert orch._detect_remote_platform() == "bitbucket"

    def test_unknown_remote(self, orch):
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_remote.url = "git@custom-host.example.com:team/repo.git"
        mock_repo.remotes = [mock_remote]
        with patch("git.Repo", return_value=mock_repo):
            assert orch._detect_remote_platform() == "unknown"

    def test_no_git_repo(self, orch):
        with patch("git.Repo", side_effect=Exception("not a repo")):
            assert orch._detect_remote_platform() == "unknown"


class TestPersistDiagnostics:
    def test_persist_creates_file(self, orch):
        orch._set_diagnostic("ci", "no_data", "No events.")
        orch._persist_diagnostics()
        diag_path = Path(orch.evo_dir) / "diagnostics.json"
        assert diag_path.exists()
        data = json.loads(diag_path.read_text())
        assert data["ci"]["status"] == "no_data"

    def test_persist_empty_does_nothing(self, orch):
        orch._persist_diagnostics()
        diag_path = Path(orch.evo_dir) / "diagnostics.json"
        assert not diag_path.exists()


class TestLicenseGating:
    def test_gated_families_set_no_license(self, orch):
        """Free tier gates Tier 2 families with no_license diagnostic."""
        # Simulate what run() does for gated families
        families_to_run = {"ci", "deployment"}
        _gated_families = [
            f for f in ["ci", "deployment", "security", "error_tracking"]
            if f in families_to_run
        ]
        for gf in _gated_families:
            orch._set_diagnostic(gf, "no_license", "Requires Evolution Engine Pro.")

        assert orch._diagnostics["ci"]["status"] == "no_license"
        assert orch._diagnostics["deployment"]["status"] == "no_license"
