"""
Tests for license gating in the orchestrator.
"""

import os
from pathlib import Path

import pytest


class TestOrchestratorLicenseGating:
    """Test that the orchestrator properly gates features based on license."""

    def test_free_tier_blocks_llm(self, tmp_path, monkeypatch):
        """Free tier should disable LLM even if requested."""
        from evolution.orchestrator import Orchestrator

        # Ensure free tier
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)

        # Create a minimal git repo
        repo = tmp_path / "repo"
        repo.mkdir()
        git_dir = repo / ".git"
        git_dir.mkdir()

        # Try to enable LLM
        orch = Orchestrator(
            repo_path=str(repo),
            enable_llm=True,  # user requested LLM
        )

        # Should be disabled by license gate
        assert orch.enable_llm is False
        assert orch.license.tier == "free"

    def test_pro_tier_allows_llm(self, tmp_path, monkeypatch):
        """Pro tier should allow LLM when requested."""
        from evolution.orchestrator import Orchestrator

        # Set Pro trial license
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")

        # Create a minimal git repo
        repo = tmp_path / "repo"
        repo.mkdir()
        git_dir = repo / ".git"
        git_dir.mkdir()

        # Request LLM
        orch = Orchestrator(
            repo_path=str(repo),
            enable_llm=True,
        )

        # Should be enabled
        assert orch.enable_llm is True
        assert orch.license.tier == "pro"

    def test_free_tier_blocks_tier2_adapters(self, tmp_path, monkeypatch):
        """Free tier should block Tier 2 adapters even with token."""
        from evolution.orchestrator import Orchestrator

        # Ensure free tier
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)

        # Create a minimal git repo
        repo = tmp_path / "repo"
        repo.mkdir()
        git_dir = repo / ".git"
        git_dir.mkdir()

        # Provide GitHub token but on free tier
        orch = Orchestrator(
            repo_path=str(repo),
            tokens={"github_token": "fake_token"},
        )

        # Tier 2 should be blocked
        assert not orch._has_tier2("ci")
        assert not orch._has_tier2("deployment")
        assert not orch._has_tier2("security")

    def test_pro_tier_allows_tier2_adapters(self, tmp_path, monkeypatch):
        """Pro tier should allow Tier 2 adapters with token."""
        from evolution.orchestrator import Orchestrator

        # Set Pro trial license
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")

        # Create a minimal git repo
        repo = tmp_path / "repo"
        repo.mkdir()
        git_dir = repo / ".git"
        git_dir.mkdir()

        # Provide GitHub token on Pro tier
        orch = Orchestrator(
            repo_path=str(repo),
            tokens={"github_token": "fake_token"},
        )

        # Tier 2 should be allowed (token is present)
        assert orch._has_tier2("ci")
        assert orch._has_tier2("deployment")
        assert orch._has_tier2("security")

    def test_license_loaded_from_repo_evo_dir(self, tmp_path, monkeypatch):
        """Orchestrator should check for license in repo .evo directory."""
        import json

        from evolution.orchestrator import Orchestrator

        # Ensure no env var
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        # Ensure no home license
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        # Create repo with license in .evo
        repo = tmp_path / "repo"
        repo.mkdir()
        git_dir = repo / ".git"
        git_dir.mkdir()
        evo_dir = repo / ".evo"
        evo_dir.mkdir()
        license_file = evo_dir / "license.json"
        license_file.write_text(json.dumps({"license_key": "pro-trial"}))

        # Orchestrator should detect Pro tier
        orch = Orchestrator(repo_path=str(repo))
        assert orch.license.tier == "pro"
        assert orch.license.is_pro()
