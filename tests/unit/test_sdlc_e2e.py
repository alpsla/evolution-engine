"""
End-to-end integration tests covering the full SDLC user journey.

Tests six paths through the Evolution Engine lifecycle:
  1. CLI Explorer — detect env, setup, analyze, status, report
  2. Hooks — install, status, script validation, uninstall
  3. GitHub Action — workflow generation with families
  4. Fix loop — residual prompts, resolution tracking
  5. Config + Setup — config groups, hook config integration
  6. Watcher — threshold checks, daemon status
"""

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from evolution.config import EvoConfig, config_groups, config_keys_for_group
from evolution.friendly import advisory_status, status_meets_threshold
from evolution.hooks import HookManager, _build_hook_script
from evolution.init import ProjectInit
from evolution.watcher import CommitWatcher


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _make_git_repo(tmp_path: Path) -> Path:
    """Create a minimal mock .git directory at *tmp_path*."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir()
    return tmp_path


def _mock_advisory(
    *,
    changes: list[dict] | None = None,
    scope: str = "test-repo",
) -> dict:
    """Build a synthetic advisory dict suitable for Phase 5 output."""
    if changes is None:
        changes = [
            {
                "family": "git",
                "metric": "files_touched",
                "current": 42,
                "normal": {"median": 5, "mad": 2.0},
                "deviation_stddev": 5.5,
            },
            {
                "family": "ci",
                "metric": "run_duration",
                "current": 600,
                "normal": {"median": 120, "mad": 30.0},
                "deviation_stddev": 3.2,
            },
            {
                "family": "dependency",
                "metric": "dependency_count",
                "current": 150,
                "normal": {"median": 80, "mad": 10.0},
                "deviation_stddev": 2.1,
            },
        ]
    return {
        "scope": scope,
        "advisory_id": "adv-test-001",
        "generated_at": "2026-02-14T12:00:00+00:00",
        "period": {"from": "2026-02-01T00:00:00Z", "to": "2026-02-14T00:00:00Z"},
        "summary": {
            "significant_changes": len(changes),
            "families_affected": list({c["family"] for c in changes}),
            "known_patterns_matched": 0,
            "new_observations": 0,
        },
        "changes": changes,
        "pattern_matches": [],
        "candidate_patterns": [],
    }


# ──────────────────────────────────────────────────────────────
# Path 1 — CLI Explorer Journey
# ──────────────────────────────────────────────────────────────

class TestPath1CLIExplorer:
    """Detect environment -> setup CLI -> mock analyze -> status -> report."""

    def test_detect_environment_finds_git_repo(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        pi = ProjectInit(repo_path=repo)
        env = pi.detect_environment()

        assert env["is_git_repo"] is True
        assert env["has_evo"] is False
        # With a .git dir present, suggestion should be "hooks"
        assert env["suggested_path"] == "hooks"

    def test_detect_environment_no_git(self, tmp_path):
        pi = ProjectInit(repo_path=tmp_path)
        env = pi.detect_environment()

        assert env["is_git_repo"] is False
        assert env["suggested_path"] == "cli"
        assert env["remote_url"] is None

    def test_setup_cli_creates_evo_dir(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        evo_dir = tmp_path / ".evo"
        config_path = tmp_path / "evo_config.toml"
        cfg = EvoConfig(path=config_path)

        pi = ProjectInit(repo_path=repo, evo_dir=evo_dir, config=cfg)
        result = pi.setup("cli")

        assert result["ok"] is True
        assert result["path"] == "cli"
        assert evo_dir.is_dir()
        assert cfg.get("init.integration") == "cli"

    def test_advisory_status_action_required(self):
        advisory = _mock_advisory()
        status = advisory_status(advisory)

        assert status["level"] == "action_required"
        assert status["label"] == "Action Required"

    def test_advisory_status_needs_attention(self):
        advisory = _mock_advisory(changes=[
            {
                "family": "ci",
                "metric": "run_duration",
                "current": 200,
                "normal": {"median": 120, "mad": 30.0},
                "deviation_stddev": 2.5,
            },
        ])
        status = advisory_status(advisory)

        assert status["level"] == "needs_attention"
        assert status["label"] == "Needs Attention"

    def test_advisory_status_all_clear(self):
        advisory = _mock_advisory(changes=[])
        status = advisory_status(advisory)

        assert status["level"] == "all_clear"

    def test_report_generation_from_advisory(self, tmp_path):
        """Mock the advisory JSON on disk and call generate_report."""
        from evolution.report_generator import generate_report

        evo_dir = tmp_path / ".evo"
        phase5_dir = evo_dir / "phase5"
        phase5_dir.mkdir(parents=True)

        advisory = _mock_advisory()
        (phase5_dir / "advisory.json").write_text(json.dumps(advisory))

        html = generate_report(evo_dir=evo_dir, title="Test Report")

        assert "<!DOCTYPE html>" in html
        assert "Test Report" in html
        assert "test-repo" in html
        assert "Files Changed" in html
        assert "Build Duration" in html

    def test_report_generation_missing_advisory_raises(self, tmp_path):
        from evolution.report_generator import generate_report

        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            generate_report(evo_dir=evo_dir)

    def test_first_run_hint_returns_hint_then_stops(self, tmp_path):
        config_path = tmp_path / "cfg.toml"
        cfg = EvoConfig(path=config_path)
        cfg.set("init.integration", "cli")
        cfg.set("init.first_run_count", 0)

        repo = _make_git_repo(tmp_path)
        pi = ProjectInit(repo_path=repo, config=cfg)

        # First 3 calls should return a hint
        for i in range(3):
            hint = pi.first_run_hint()
            assert hint is not None
            assert "evo init" in hint

        # Fourth call should return None
        assert pi.first_run_hint() is None


# ──────────────────────────────────────────────────────────────
# Path 2 — Hooks Journey
# ──────────────────────────────────────────────────────────────

class TestPath2Hooks:
    """Install hook -> verify installed -> status -> validate script -> uninstall."""

    @patch("evolution.hooks.subprocess.run")
    def test_setup_hooks_installs_hook(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        config_path = tmp_path / "cfg.toml"
        cfg = EvoConfig(path=config_path)

        pi = ProjectInit(repo_path=repo, config=cfg)
        result = pi.setup("hooks")

        assert result["ok"] is True
        assert any("hook" in a.lower() for a in result["actions"])

    @patch("evolution.hooks.subprocess.run")
    def test_hook_manager_install_and_is_installed(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        config_path = tmp_path / "cfg.toml"
        cfg = EvoConfig(path=config_path)

        hm = HookManager(repo_path=repo, config=cfg)
        result = hm.install()

        assert result["ok"] is True
        assert result["trigger"] == "post-commit"
        assert hm.is_installed() is True

    @patch("evolution.hooks.subprocess.run")
    def test_hook_manager_status(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        config_path = tmp_path / "cfg.toml"
        cfg = EvoConfig(path=config_path)

        hm = HookManager(repo_path=repo, config=cfg)
        hm.install()
        status = hm.status()

        assert status["installed"] is True
        assert status["trigger"] == "post-commit"
        assert status["hook_path"] is not None

    def test_build_hook_script_contains_evo_command(self):
        script = _build_hook_script(
            background=True,
            auto_open=True,
            notify=True,
            min_severity="concern",
            families="",
        )

        assert "evo analyze" in script
        assert "--json" in script
        assert "--quiet" in script
        assert "# evo-hook-start" in script
        assert "# evo-hook-end" in script

    def test_build_hook_script_with_families(self):
        script = _build_hook_script(
            background=False,
            auto_open=False,
            notify=False,
            min_severity="critical",
            families="git,ci",
        )

        assert "--families git,ci" in script
        # With background=False, the run command should NOT end with &
        assert "_evo_hook_run\n" in script

    def test_build_hook_script_background_suffix(self):
        script = _build_hook_script(
            background=True,
            auto_open=False,
            notify=False,
            min_severity="info",
            families="",
        )

        assert "_evo_hook_run &" in script

    @patch("evolution.hooks.subprocess.run")
    def test_uninstall_removes_hook(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        config_path = tmp_path / "cfg.toml"
        cfg = EvoConfig(path=config_path)

        hm = HookManager(repo_path=repo, config=cfg)
        hm.install()
        assert hm.is_installed() is True

        result = hm.uninstall()
        assert result["ok"] is True
        assert hm.is_installed() is False

    @patch("evolution.hooks.subprocess.run")
    def test_hook_file_is_executable(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")

        hm = HookManager(repo_path=repo, config=cfg)
        result = hm.install()
        hook_path = Path(result["hook_path"])

        mode = hook_path.stat().st_mode
        assert mode & stat.S_IXUSR, "Hook file should be user-executable"

    def test_install_on_non_git_repo_fails(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "cfg.toml")
        hm = HookManager(repo_path=tmp_path, config=cfg)
        result = hm.install()

        assert result["ok"] is False
        assert "Not a git repository" in result["error"]


# ──────────────────────────────────────────────────────────────
# Path 3 — GitHub Action Journey
# ──────────────────────────────────────────────────────────────

class TestPath3GitHubAction:
    """Setup action -> verify YAML structure -> families param."""

    @patch("evolution.hooks.subprocess.run")
    def test_setup_action_creates_workflow(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")

        pi = ProjectInit(repo_path=repo, config=cfg)
        result = pi.setup("action")

        assert result["ok"] is True
        wf_path = repo / ".github" / "workflows" / "evolution.yml"
        assert wf_path.exists()

    @patch("evolution.hooks.subprocess.run")
    def test_workflow_yaml_structure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")

        pi = ProjectInit(repo_path=repo, config=cfg)
        pi.setup("action")

        wf_path = repo / ".github" / "workflows" / "evolution.yml"
        content = wf_path.read_text()

        assert "on:" in content
        assert "pull_request:" in content
        assert "uses: codequal/evolution-engine-action@v1" in content
        assert "actions/checkout@v4" in content
        assert "permissions:" in content

    def test_generate_workflow_without_families(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")
        pi = ProjectInit(repo_path=repo, config=cfg)

        yaml = pi.generate_workflow()

        assert "families:" not in yaml
        assert "codequal/evolution-engine-action@v1" in yaml

    def test_generate_workflow_with_families(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")
        pi = ProjectInit(repo_path=repo, config=cfg)

        yaml = pi.generate_workflow(families="git,ci,dependency")

        assert 'families: "git,ci,dependency"' in yaml

    def test_generate_workflow_with_license_key(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")
        pi = ProjectInit(repo_path=repo, config=cfg)

        yaml = pi.generate_workflow(license_key="EVO_LICENSE_KEY")

        assert "EVO_LICENSE_KEY" in yaml

    @patch("evolution.hooks.subprocess.run")
    def test_setup_action_with_families(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")

        pi = ProjectInit(repo_path=repo, config=cfg)
        result = pi.setup("action", families="git,ci")

        assert result["ok"] is True

        wf_path = repo / ".github" / "workflows" / "evolution.yml"
        content = wf_path.read_text()
        assert 'families: "git,ci"' in content

    def test_setup_invalid_path(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")
        pi = ProjectInit(repo_path=repo, config=cfg)

        result = pi.setup("invalid_path")

        assert result["ok"] is False
        assert "Invalid path" in result["error"]


# ──────────────────────────────────────────────────────────────
# Path 4 — Fix Loop Journey
# ──────────────────────────────────────────────────────────────

class TestPath4FixLoop:
    """Build residual prompt -> resolution progress tracking."""

    def test_build_residual_prompt_contains_details(self, tmp_path):
        from evolution.fixer import Fixer

        evo_dir = tmp_path / ".evo"
        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)

        previous_advisory = _mock_advisory(changes=[
            {"family": "git", "metric": "files_touched", "current": 42,
             "normal": {"median": 5}, "deviation_stddev": 5.5},
            {"family": "ci", "metric": "run_duration", "current": 600,
             "normal": {"median": 120}, "deviation_stddev": 3.2},
            {"family": "dependency", "metric": "dependency_count", "current": 150,
             "normal": {"median": 80}, "deviation_stddev": 2.1},
        ])

        # Current advisory: one finding resolved (dependency_count gone)
        current_advisory = _mock_advisory(changes=[
            {"family": "git", "metric": "files_touched", "current": 42,
             "normal": {"median": 5}, "deviation_stddev": 5.5},
            {"family": "ci", "metric": "run_duration", "current": 600,
             "normal": {"median": 120}, "deviation_stddev": 3.2},
        ])

        investigation_text = "Investigation: high files_touched and run_duration detected."

        prompt = fixer._build_residual_prompt(
            current_advisory, previous_advisory, investigation_text,
        )

        # Resolved section should mention dependency_count
        assert "dependency" in prompt.lower()
        # Persisting section should mention files_touched and run_duration
        assert "files_touched" in prompt
        assert "run_duration" in prompt
        # Investigation text should be embedded
        assert investigation_text in prompt
        # It should use the RESIDUAL_PROMPT_TEMPLATE structure
        assert "ITERATION" in prompt
        assert "Still Drifting" in prompt
        assert "Already Resolved" in prompt

    def test_resolution_progress_calculation(self, tmp_path):
        from evolution.fixer import Fixer

        evo_dir = tmp_path / ".evo"
        phase5_dir = evo_dir / "phase5"
        phase5_dir.mkdir(parents=True)

        # Write investigation text
        inv_dir = evo_dir / "investigation"
        inv_dir.mkdir()
        (inv_dir / "investigation.txt").write_text("Test investigation report.")

        # Previous advisory: 3 findings
        previous_advisory = _mock_advisory(changes=[
            {"family": "git", "metric": "files_touched", "current": 42,
             "normal": {"median": 5}, "deviation_stddev": 5.5},
            {"family": "ci", "metric": "run_duration", "current": 600,
             "normal": {"median": 120}, "deviation_stddev": 3.2},
            {"family": "dependency", "metric": "dependency_count", "current": 150,
             "normal": {"median": 80}, "deviation_stddev": 2.1},
        ])
        (phase5_dir / "advisory_previous.json").write_text(
            json.dumps(previous_advisory)
        )

        # Current advisory: 1 finding resolved (dependency gone)
        current_advisory = _mock_advisory(changes=[
            {"family": "git", "metric": "files_touched", "current": 42,
             "normal": {"median": 5}, "deviation_stddev": 5.5},
            {"family": "ci", "metric": "run_duration", "current": 600,
             "normal": {"median": 120}, "deviation_stddev": 3.2},
        ])
        (phase5_dir / "advisory.json").write_text(
            json.dumps(current_advisory)
        )

        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)

        investigation_text = "Test investigation report."
        result = fixer._run_residual_dry_run(investigation_text)

        assert result is not None
        assert result.status == "dry_run_residual"
        assert result.dry_run is True

        # 1 resolved, 2 persisting, 0 new
        assert result.resolved_count == 1
        assert result.persisting_count == 2
        assert result.new_count == 0

        # Progress: 1 of 3 = ~33%
        total_original = result.resolved_count + result.persisting_count + result.new_count
        progress_pct = (result.resolved_count / total_original) * 100
        assert 33 <= progress_pct <= 34

    def test_format_residual_shows_correct_sections(self):
        from evolution.fixer import Fixer

        verification = {
            "verification": {
                "persisting": [
                    {"family": "git", "metric": "files_touched",
                     "after_deviation": 4.2, "improved": True},
                ],
                "new": [
                    {"family": "ci", "metric": "run_failed",
                     "deviation": 1.5},
                ],
                "regressions": [],
                "resolved": [
                    {"family": "dependency", "metric": "dependency_count"},
                ],
            }
        }

        text = Fixer._format_residual(verification)

        assert "STILL FLAGGED" in text
        assert "files_touched" in text
        assert "NEW ISSUES" in text
        assert "run_failed" in text
        assert "ALREADY RESOLVED" in text
        assert "1 item(s)" in text

    def test_fix_iteration_all_clear_property(self):
        from evolution.fixer import FixIteration

        # All clear when nothing persisting/new/regressed
        it = FixIteration(
            iteration=1,
            agent_response="fixes applied",
            resolved=3,
            persisting=0,
            new_issues=0,
            regressions=0,
        )
        assert it.all_clear is True

        # Not all clear when something persists
        it2 = FixIteration(
            iteration=1,
            agent_response="partial fix",
            resolved=2,
            persisting=1,
            new_issues=0,
            regressions=0,
        )
        assert it2.all_clear is False

    def test_fix_result_to_dict(self):
        from evolution.fixer import FixResult, FixIteration

        iteration = FixIteration(
            iteration=1,
            agent_response="test response",
            resolved=1,
            persisting=2,
        )
        result = FixResult(
            status="partial",
            iterations=[iteration],
            branch="evo/fix-test",
            total_resolved=1,
            total_remaining=2,
        )

        d = result.to_dict()

        assert d["status"] == "partial"
        assert d["branch"] == "evo/fix-test"
        assert d["total_resolved"] == 1
        assert d["total_remaining"] == 2
        assert d["iterations_count"] == 1
        assert d["iterations"][0]["resolved"] == 1

    def test_save_previous_advisory(self, tmp_path):
        from evolution.fixer import Fixer

        evo_dir = tmp_path / ".evo"
        phase5_dir = evo_dir / "phase5"
        phase5_dir.mkdir(parents=True)

        advisory = _mock_advisory()
        (phase5_dir / "advisory.json").write_text(json.dumps(advisory))

        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)
        saved = fixer.save_previous_advisory()

        assert saved is True
        prev_path = phase5_dir / "advisory_previous.json"
        assert prev_path.exists()
        loaded = json.loads(prev_path.read_text())
        assert loaded["scope"] == "test-repo"

    def test_save_previous_advisory_no_current(self, tmp_path):
        from evolution.fixer import Fixer

        evo_dir = tmp_path / ".evo"
        (evo_dir / "phase5").mkdir(parents=True)

        fixer = Fixer(repo_path=tmp_path, evo_dir=evo_dir)
        assert fixer.save_previous_advisory() is False


# ──────────────────────────────────────────────────────────────
# Path 5 — Config + Setup Journey
# ──────────────────────────────────────────────────────────────

class TestPath5ConfigSetup:
    """Config creation, values, hook integration, group/key consistency."""

    def test_config_set_and_get(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")

        cfg.set("hooks.trigger", "pre-push")
        cfg.set("hooks.min_severity", "critical")

        assert cfg.get("hooks.trigger") == "pre-push"
        assert cfg.get("hooks.min_severity") == "critical"

    def test_config_defaults(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")

        assert cfg.get("hooks.trigger") == "post-commit"
        assert cfg.get("hooks.min_severity") == "concern"
        assert cfg.get("hooks.background") is True

    def test_config_persists_to_disk(self, tmp_path):
        config_path = tmp_path / "config.toml"
        cfg1 = EvoConfig(path=config_path)
        cfg1.set("hooks.trigger", "pre-push")

        # Reload from disk
        cfg2 = EvoConfig(path=config_path)
        assert cfg2.get("hooks.trigger") == "pre-push"

    @patch("evolution.hooks.subprocess.run")
    def test_hook_manager_uses_config_trigger(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        repo = _make_git_repo(tmp_path)
        cfg = EvoConfig(path=tmp_path / "cfg.toml")
        cfg.set("hooks.trigger", "pre-push")

        hm = HookManager(repo_path=repo, config=cfg)
        result = hm.install()

        assert result["ok"] is True
        assert result["trigger"] == "pre-push"
        # The hook file should be at pre-push, not post-commit
        hook_file = repo / ".git" / "hooks" / "pre-push"
        assert hook_file.exists()

    def test_config_groups_ordered(self):
        groups = config_groups()

        labels = list(groups.keys())
        # analyze (order=1) should come before hooks (order=2)
        assert labels.index("analyze") < labels.index("hooks")
        # hooks (order=2) should come before sync (order=3)
        assert labels.index("hooks") < labels.index("sync")

    def test_config_keys_for_group_hooks(self):
        keys = config_keys_for_group("hooks")

        assert "hooks.trigger" in keys
        assert "hooks.min_severity" in keys
        assert "hooks.auto_open" in keys
        assert "hooks.notify" in keys
        assert "hooks.background" in keys

    def test_config_keys_for_group_excludes_internal(self):
        keys = config_keys_for_group("init", include_internal=False)
        assert len(keys) == 0

        keys_with_internal = config_keys_for_group("init", include_internal=True)
        assert "init.integration" in keys_with_internal

    def test_config_groups_and_keys_consistent(self):
        """Every key returned by config_keys_for_group should belong to its group."""
        groups = config_groups()
        for group_name in groups:
            keys = config_keys_for_group(group_name, include_internal=True)
            for key in keys:
                assert key.startswith(f"{group_name}."), (
                    f"Key {key!r} does not start with group prefix {group_name!r}"
                )

    def test_config_delete(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("hooks.trigger", "pre-push")
        assert cfg.get("hooks.trigger") == "pre-push"

        deleted = cfg.delete("hooks.trigger")
        assert deleted is True
        # Falls back to default after deletion
        assert cfg.get("hooks.trigger") == "post-commit"

    def test_config_all_merges_defaults(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("hooks.trigger", "pre-push")

        all_config = cfg.all()
        assert all_config["hooks.trigger"] == "pre-push"
        # Default values should also be present
        assert "sync.privacy_level" in all_config


# ──────────────────────────────────────────────────────────────
# Path 6 — Watcher Journey
# ──────────────────────────────────────────────────────────────

class TestPath6Watcher:
    """CommitWatcher threshold checks and daemon status."""

    def test_check_threshold_critical_meets_critical(self):
        watcher = CommitWatcher(min_severity="critical")
        advisory = {
            "advisory": {
                "status": {"level": "action_required"},
            },
        }
        assert watcher._check_threshold(advisory) is True

    def test_check_threshold_critical_skips_lower(self):
        watcher = CommitWatcher(min_severity="critical")
        advisory = {
            "advisory": {
                "status": {"level": "needs_attention"},
            },
        }
        assert watcher._check_threshold(advisory) is False

    def test_check_threshold_concern_includes_action_required(self):
        watcher = CommitWatcher(min_severity="concern")
        advisory = {
            "advisory": {
                "status": {"level": "action_required"},
            },
        }
        assert watcher._check_threshold(advisory) is True

    def test_check_threshold_concern_includes_needs_attention(self):
        watcher = CommitWatcher(min_severity="concern")
        advisory = {
            "advisory": {
                "status": {"level": "needs_attention"},
            },
        }
        assert watcher._check_threshold(advisory) is True

    def test_check_threshold_concern_skips_worth_monitoring(self):
        watcher = CommitWatcher(min_severity="concern")
        advisory = {
            "advisory": {
                "status": {"level": "worth_monitoring"},
            },
        }
        assert watcher._check_threshold(advisory) is False

    def test_check_threshold_watch_includes_worth_monitoring(self):
        watcher = CommitWatcher(min_severity="watch")
        advisory = {
            "advisory": {
                "status": {"level": "worth_monitoring"},
            },
        }
        assert watcher._check_threshold(advisory) is True

    def test_check_threshold_info_includes_all_clear(self):
        watcher = CommitWatcher(min_severity="info")
        advisory = {
            "advisory": {
                "status": {"level": "all_clear"},
            },
        }
        assert watcher._check_threshold(advisory) is True

    def test_check_threshold_missing_status_returns_false(self):
        watcher = CommitWatcher(min_severity="concern")
        advisory = {}
        assert watcher._check_threshold(advisory) is False

    def test_daemon_status_not_running(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()

        status = CommitWatcher.daemon_status(
            str(tmp_path), str(evo_dir),
        )
        assert status["running"] is False
        assert status["pid"] is None

    def test_daemon_status_stale_pid(self, tmp_path):
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir()
        # Write a PID that definitely doesn't exist
        pid_file = evo_dir / "watch.pid"
        pid_file.write_text("999999999")

        status = CommitWatcher.daemon_status(
            str(tmp_path), str(evo_dir),
        )
        assert status["running"] is False

    def test_watcher_invalid_severity_defaults_to_concern(self):
        watcher = CommitWatcher(min_severity="nonexistent")
        assert watcher.min_severity == "concern"

    def test_watcher_interval_minimum(self):
        watcher = CommitWatcher(interval=0)
        assert watcher.interval >= 1

        watcher2 = CommitWatcher(interval=-5)
        assert watcher2.interval >= 1


# ──────────────────────────────────────────────────────────────
# Cross-cutting: status_meets_threshold exhaustive checks
# ──────────────────────────────────────────────────────────────

class TestStatusMeetsThreshold:
    """Verify the threshold logic used by both hooks and watcher."""

    @pytest.mark.parametrize(
        "status_level,min_severity,expected",
        [
            # critical threshold: only action_required passes
            ("action_required", "critical", True),
            ("needs_attention", "critical", False),
            ("worth_monitoring", "critical", False),
            ("all_clear", "critical", False),
            # concern threshold: action_required + needs_attention
            ("action_required", "concern", True),
            ("needs_attention", "concern", True),
            ("worth_monitoring", "concern", False),
            ("all_clear", "concern", False),
            # watch threshold: action_required + needs_attention + worth_monitoring
            ("action_required", "watch", True),
            ("needs_attention", "watch", True),
            ("worth_monitoring", "watch", True),
            ("all_clear", "watch", False),
            # info threshold: everything
            ("action_required", "info", True),
            ("needs_attention", "info", True),
            ("worth_monitoring", "info", True),
            ("all_clear", "info", True),
        ],
    )
    def test_threshold_matrix(self, status_level, min_severity, expected):
        assert status_meets_threshold(status_level, min_severity) is expected
