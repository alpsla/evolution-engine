"""Tests for evolution.init — guided project initialization."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from evolution.config import EvoConfig
from evolution.init import ProjectInit, _WORKFLOW_TEMPLATE, _GITLAB_CI_TEMPLATE, _VALID_PATHS


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

    def test_has_gitlab(self, git_repo, config):
        """Repo with .gitlab-ci.yml: has_gitlab=True."""
        (git_repo / ".gitlab-ci.yml").write_text("stages:\n  - test\n")
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_gitlab"] is True

    def test_has_evo_gitlab(self, git_repo, config):
        """.gitlab-ci.yml with 'evolution' keyword: has_evo_gitlab=True."""
        (git_repo / ".gitlab-ci.yml").write_text(
            "stages:\n  - analyze\nevo-analyze:\n  script: pip install evolution-engine\n"
        )
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_evo_gitlab"] is True

    def test_no_gitlab(self, git_repo, config):
        """No .gitlab-ci.yml: has_gitlab=False."""
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["has_gitlab"] is False
        assert env["has_evo_gitlab"] is False

    def test_ci_provider_github_only(self, git_repo, config):
        """.github/ without .gitlab-ci.yml -> ci_provider='github'."""
        (git_repo / ".github").mkdir()
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["ci_provider"] == "github"

    def test_ci_provider_gitlab_only(self, git_repo, config):
        """.gitlab-ci.yml without .github/ -> ci_provider='gitlab'."""
        (git_repo / ".gitlab-ci.yml").write_text("stages:\n  - test\n")
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["ci_provider"] == "gitlab"

    def test_ci_provider_both_prefers_remote(self, git_repo, config):
        """Both CI files + gitlab remote -> ci_provider='gitlab'."""
        (git_repo / ".github").mkdir()
        (git_repo / ".gitlab-ci.yml").write_text("stages:\n  - test\n")
        subprocess.run(
            ["git", "remote", "add", "origin", "https://gitlab.com/owner/repo.git"],
            cwd=str(git_repo),
            capture_output=True,
            timeout=10,
        )
        pi = ProjectInit(repo_path=git_repo, config=config)
        env = pi.detect_environment()
        assert env["ci_provider"] == "gitlab"

    def test_ci_provider_none(self, tmp_path, config):
        """Neither CI file nor remote -> ci_provider=None."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        env = pi.detect_environment()
        assert env["ci_provider"] is None


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

    def test_action_setup_gitlab(self, git_repo, config):
        """Action setup with GitLab CI provider generates .gitlab-ci.yml."""
        (git_repo / ".gitlab-ci.yml").write_text("stages:\n  - test\n")
        pi = ProjectInit(repo_path=git_repo, config=config)
        result = pi.setup(path="action")
        assert result["ok"] is True
        content = (git_repo / ".gitlab-ci.yml").read_text()
        assert "evolution" in content.lower()
        assert "evo-analyze" in content

    def test_action_setup_gitlab_appends(self, git_repo, config):
        """Action setup appends EE jobs to existing .gitlab-ci.yml."""
        existing = "stages:\n  - test\n\nmy-job:\n  script: echo hello\n"
        (git_repo / ".gitlab-ci.yml").write_text(existing)
        pi = ProjectInit(repo_path=git_repo, config=config)
        result = pi.setup(path="action")
        assert result["ok"] is True
        content = (git_repo / ".gitlab-ci.yml").read_text()
        # Original content preserved
        assert "my-job:" in content
        # EE content appended
        assert "evo-analyze" in content

    def test_action_setup_gitlab_skips_if_present(self, git_repo, config):
        """Action setup skips when EE already in .gitlab-ci.yml."""
        (git_repo / ".gitlab-ci.yml").write_text(
            "stages:\n  - analyze\nevo-analyze:\n  script: pip install evolution-engine\n"
        )
        pi = ProjectInit(repo_path=git_repo, config=config)
        result = pi.setup(path="action")
        assert result["ok"] is True
        assert any("skipped" in a.lower() for a in result["actions"])


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


# ─── TestGenerateGitLabCI ───

class TestGenerateGitLabCI:
    def test_basic_gitlab_ci(self, tmp_path, config):
        """Generated GitLab CI contains expected structure."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        assert "stages:" in yaml
        assert "evo-analyze:" in yaml
        assert "evo-comment:" in yaml
        assert "GITLAB_TOKEN" in yaml
        assert "merge_request_event" in yaml

    def test_gitlab_ci_with_families(self, tmp_path, config):
        """Families filter is embedded in the pipeline."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci(families="git,ci")
        assert "--families git,ci" in yaml

    def test_gitlab_ci_has_cache(self, tmp_path, config):
        """Cache config is present in GitLab CI."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        assert "cache:" in yaml
        assert "evo-$CI_MERGE_REQUEST_IID" in yaml

    def test_gitlab_ci_has_api_posting(self, tmp_path, config):
        """GitLab API posting is present (CI_PROJECT_ID, notes endpoint)."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        assert "CI_PROJECT_ID" in yaml
        assert "CI_MERGE_REQUEST_IID" in yaml
        assert "notes" in yaml

    def test_gitlab_ci_has_acceptance_webhook(self, tmp_path, config):
        """Acceptance webhook reference is present."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        assert "EVO_WEBHOOK_URL" in yaml
        assert "accepted.json" in yaml

    def test_gitlab_ci_with_version_pin(self, tmp_path, config):
        """Version pin is embedded in pip install."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci(version_pin="0.2.0")
        assert "evolution-engine==0.2.0" in yaml

    def test_gitlab_ci_without_families(self, tmp_path, config):
        """No families flag when not specified."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        assert "--families" not in yaml

    def test_gitlab_ci_has_verification(self, tmp_path, config):
        """Verification step is present (advisory.json.prev + evo verify)."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        assert "advisory.json.prev" in yaml
        assert "evo verify" in yaml
        assert "verification.json" in yaml

    def test_gitlab_ci_has_sources(self, tmp_path, config):
        """Sources collection is present (evo sources --json)."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        assert "evo sources --json" in yaml
        assert "sources.json" in yaml

    def test_gitlab_ci_has_acceptance_push(self, tmp_path, config):
        """Acceptance push to webhook is present."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        # Should push permanent acceptances, not just pull
        assert "permanent" in yaml
        assert "POST" in yaml

    def test_gitlab_ci_has_pro_comments(self, tmp_path, config):
        """Pro features section is present as comments."""
        pi = ProjectInit(repo_path=tmp_path, config=config)
        yaml = pi.generate_gitlab_ci()
        assert "Pro Features" in yaml
        assert "investigate" in yaml
        assert "ANTHROPIC_API_KEY" in yaml


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
