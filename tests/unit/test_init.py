"""Tests for evolution.init — guided project initialization."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from evolution.config import EvoConfig
from evolution.init import ProjectInit, _WORKFLOW_TEMPLATE, _VALID_PATHS


# ─── Fixtures ───

@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repo in tmp_path."""
    subprocess.run(
        ["git", "init"],
        cwd=str(tmp_path),
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path),
        capture_output=True,
        timeout=10,
    )
    return tmp_path


@pytest.fixture
def config(tmp_path):
    """Create an EvoConfig pointing at a temp file."""
    return EvoConfig(path=tmp_path / "evo_cfg" / "config.toml")


# ─── TestDetectEnvironment ───

class TestDetectEnvironment:
    def test_no_git(self, tmp_path, config):
        """Non-git directory: is_git_repo=False, suggested_path=cli."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        env = pi.detect_environment()
        assert env["is_git_repo"] is False
        assert env["has_github"] is False
        assert env["has_workflows"] is False
        assert env["has_evo"] is False
        assert env["has_evo_action"] is False
        assert env["remote_url"] is None
        assert env["repo_name"] == tmp_path.name
        assert env["suggested_path"] == "cli"

    def test_with_git(self, git_repo, config):
        """Git repo: is_git_repo=True, suggested_path=hooks."""
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["is_git_repo"] is True
        assert env["suggested_path"] == "hooks"

    def test_with_github_dir(self, git_repo, config):
        """Git repo with .github/: has_github=True."""
        (git_repo / ".github").mkdir()
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_github"] is True
        assert env["has_workflows"] is False

    def test_with_workflows_dir(self, git_repo, config):
        """Git repo with .github/workflows/: has_workflows=True."""
        (git_repo / ".github" / "workflows").mkdir(parents=True)
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_github"] is True
        assert env["has_workflows"] is True
        assert env["has_evo_action"] is False

    def test_has_evo_action(self, git_repo, config):
        """Workflow file mentioning evolution detected."""
        wf_dir = git_repo / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\nuses: alpsla/evolution-engine@v1\n"
        )
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_evo_action"] is True

    def test_has_evo_action_case_insensitive(self, git_repo, config):
        """Workflow file with capitalized 'Evolution' is detected."""
        wf_dir = git_repo / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yaml").write_text(
            "name: CI\n# Evolution Engine workflow\n"
        )
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_evo_action"] is True

    def test_no_evo_action_without_keyword(self, git_repo, config):
        """Workflow file without 'evolution' is not flagged."""
        wf_dir = git_repo / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\njobs:\n  test:\n")
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_evo_action"] is False

    def test_has_evo_dir(self, git_repo, config):
        """Existing .evo/ directory detected."""
        (git_repo / ".evo").mkdir()
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_evo"] is True

    def test_remote_url_extracted(self, git_repo, config):
        """Remote URL is returned when origin is set."""
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/owner/my-repo.git"],
            cwd=str(git_repo),
            capture_output=True,
            timeout=10,
        )
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["remote_url"] == "https://github.com/owner/my-repo.git"
        assert env["repo_name"] == "my-repo"

    def test_repo_name_from_ssh_url(self, git_repo, config):
        """SSH-style remote URL is parsed correctly."""
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:owner/cool-project.git"],
            cwd=str(git_repo),
            capture_output=True,
            timeout=10,
        )
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["repo_name"] == "cool-project"

    def test_repo_name_fallback_to_dirname(self, tmp_path, config):
        """Without a remote, repo_name falls back to directory name."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        env = pi.detect_environment()
        assert env["repo_name"] == tmp_path.name


# ─── TestSetup ───

class TestSetup:
    def test_invalid_path(self, tmp_path, config):
        """Invalid path returns error."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        result = pi.setup(path="invalid")
        assert result["ok"] is False
        assert "Invalid path" in result["error"]

    def test_cli_setup(self, tmp_path, config):
        """CLI setup creates .evo dir and saves config."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        result = pi.setup(path="cli")
        assert result["ok"] is True
        assert result["path"] == "cli"
        assert (tmp_path / ".evo").is_dir()
        assert config.get("init.integration") == "cli"
        assert config.get("init.first_run_count") == 0
        assert any("Created" in a for a in result["actions"])
        assert any("config" in a.lower() for a in result["actions"])

    def test_hooks_setup(self, git_repo, config):
        """Hooks setup creates .evo dir and installs hook."""
        pi = ProjectInit(repo_path=git_repo, config=config)
        result = pi.setup(path="hooks")
        assert result["ok"] is True
        assert result["path"] == "hooks"
        assert (git_repo / ".evo").is_dir()
        assert config.get("init.integration") == "hooks"
        assert any("hook" in a.lower() for a in result["actions"])

    def test_hooks_setup_no_git(self, tmp_path, config):
        """Hooks setup in non-git directory fails gracefully."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        result = pi.setup(path="hooks")
        assert result["ok"] is False
        assert "Hook install failed" in result["error"]

    def test_action_setup(self, git_repo, config):
        """Action setup creates .evo dir and workflow file."""
        pi = ProjectInit(repo_path=git_repo, config=config)
        result = pi.setup(path="action")
        assert result["ok"] is True
        assert result["path"] == "action"
        assert (git_repo / ".evo").is_dir()
        assert (git_repo / ".github" / "workflows" / "evolution.yml").exists()
        assert config.get("init.integration") == "action"

    def test_action_setup_with_families(self, git_repo, config):
        """Action setup embeds families in the workflow."""
        pi = ProjectInit(repo_path=git_repo, config=config)
        result = pi.setup(path="action", families="git,ci")
        assert result["ok"] is True
        wf_content = (git_repo / ".github" / "workflows" / "evolution.yml").read_text()
        assert "git,ci" in wf_content

    def test_all_setup(self, git_repo, config):
        """All setup creates .evo dir, installs hook, and writes workflow."""
        pi = ProjectInit(repo_path=git_repo, config=config)
        result = pi.setup(path="all")
        assert result["ok"] is True
        assert result["path"] == "all"
        assert (git_repo / ".evo").is_dir()
        assert (git_repo / ".github" / "workflows" / "evolution.yml").exists()
        assert config.get("init.integration") == "all"
        # Should have multiple actions
        assert len(result["actions"]) >= 3

    def test_setup_creates_nested_evo_dir(self, tmp_path, config):
        """Custom evo_dir is created if it doesn't exist."""
        custom_evo = tmp_path / "deep" / "nested" / ".evo"
        pi = ProjectInit(repo_path=tmp_path, evo_dir=custom_evo, config=config)
        result = pi.setup(path="cli")
        assert result["ok"] is True
        assert custom_evo.is_dir()


# ─── TestGenerateWorkflow ───

class TestGenerateWorkflow:
    def test_basic_workflow(self, tmp_path, config):
        """Generated workflow contains expected keys."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_workflow()
        assert "name: Evolution Engine" in yaml
        assert "pull_request:" in yaml
        assert "push:" in yaml
        assert "branches: [main]" in yaml
        assert "alpsla/evolution-engine@v1" in yaml
        assert "GITHUB_TOKEN" in yaml
        assert "actions/checkout@v4" in yaml

    def test_workflow_with_families(self, tmp_path, config):
        """Families filter is embedded in the workflow."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_workflow(families="git,ci,dependency")
        assert 'families: "git,ci,dependency"' in yaml

    def test_workflow_without_families(self, tmp_path, config):
        """No families line when not specified."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_workflow()
        assert "families:" not in yaml

    def test_workflow_with_license_key(self, tmp_path, config):
        """License key secret is embedded in the workflow."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_workflow(license_key="EVO_LICENSE_KEY")
        assert "EVO_LICENSE_KEY" in yaml

    def test_workflow_without_license_key(self, tmp_path, config):
        """No license key env when not specified."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_workflow()
        # Should not have a standalone EVO_LICENSE_KEY line (it's in the pro comment section)
        lines = yaml.split("\n")
        non_comment_lines = [l for l in lines if not l.strip().startswith("#")]
        env_lines = [l for l in non_comment_lines if "EVO_LICENSE_KEY" in l]
        # The template has EVO_LICENSE_KEY in the commented-out pro section only
        assert len(env_lines) == 0

    def test_workflow_has_pro_comments(self, tmp_path, config):
        """Pro features section is present as comments."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_workflow()
        assert "Pro Features" in yaml
        assert "investigate" in yaml
        assert "suggest-fixes" in yaml

    def test_workflow_is_valid_yaml_structure(self, tmp_path, config):
        """The generated workflow has proper YAML structure."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml_content = pi.generate_workflow()
        # Should start with a comment, not invalid YAML
        assert yaml_content.startswith("#")
        # Should have standard workflow keys
        assert "on:" in yaml_content
        assert "jobs:" in yaml_content
        assert "runs-on:" in yaml_content
        assert "steps:" in yaml_content


# ─── TestFirstRunHint ───

class TestFirstRunHint:
    def test_hint_returns_string_for_uninitialized(self, tmp_path, config):
        """Before setup, hint suggests running evo init."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        hint = pi.first_run_hint()
        assert hint is not None
        assert "evo init" in hint

    def test_hint_for_cli_suggests_hooks(self, tmp_path, config):
        """After CLI setup, hint suggests hooks."""
        config.set("init.integration", "cli")
        config.set("init.first_run_count", 0)
        pi = ProjectInit(repo_path=tmp_path, config=config)
        hint = pi.first_run_hint()
        assert hint is not None
        assert "hooks" in hint

    def test_hint_for_hooks_suggests_action(self, tmp_path, config):
        """After hooks setup, hint suggests action."""
        config.set("init.integration", "hooks")
        config.set("init.first_run_count", 0)
        pi = ProjectInit(repo_path=tmp_path, config=config)
        hint = pi.first_run_hint()
        assert hint is not None
        assert "action" in hint

    def test_hint_for_action_suggests_hooks(self, tmp_path, config):
        """After action setup, hint suggests hooks."""
        config.set("init.integration", "action")
        config.set("init.first_run_count", 0)
        pi = ProjectInit(repo_path=tmp_path, config=config)
        hint = pi.first_run_hint()
        assert hint is not None
        assert "hooks" in hint

    def test_hint_increments_count(self, tmp_path, config):
        """Each call increments first_run_count."""
        config.set("init.integration", "cli")
        config.set("init.first_run_count", 0)
        pi = ProjectInit(repo_path=tmp_path, config=config)

        pi.first_run_hint()
        assert config.get("init.first_run_count") == 1

        pi.first_run_hint()
        assert config.get("init.first_run_count") == 2

        pi.first_run_hint()
        assert config.get("init.first_run_count") == 3

    def test_hint_returns_none_after_three(self, tmp_path, config):
        """After 3 calls, first_run_hint returns None."""
        config.set("init.integration", "cli")
        config.set("init.first_run_count", 0)
        pi = ProjectInit(repo_path=tmp_path, config=config)

        assert pi.first_run_hint() is not None  # count 0 -> 1
        assert pi.first_run_hint() is not None  # count 1 -> 2
        assert pi.first_run_hint() is not None  # count 2 -> 3
        assert pi.first_run_hint() is None      # count 3 -> stays 3

    def test_hint_none_when_count_already_3(self, tmp_path, config):
        """If count is already >= 3, hint is None immediately."""
        config.set("init.integration", "cli")
        config.set("init.first_run_count", 5)
        pi = ProjectInit(repo_path=tmp_path, config=config)
        assert pi.first_run_hint() is None

    def test_hint_for_all_path(self, tmp_path, config):
        """The 'all' path returns a hint about trying analyze."""
        config.set("init.integration", "all")
        config.set("init.first_run_count", 0)
        pi = ProjectInit(repo_path=tmp_path, config=config)
        hint = pi.first_run_hint()
        assert hint is not None
        assert "evo analyze" in hint

    def test_setup_resets_count(self, tmp_path, config):
        """Setup resets first_run_count to 0."""
        config.set("init.first_run_count", 5)
        pi = ProjectInit(repo_path=tmp_path, config=config)
        pi.setup(path="cli")
        assert config.get("init.first_run_count") == 0
