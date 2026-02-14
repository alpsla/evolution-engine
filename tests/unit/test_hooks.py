"""Tests for evolution.hooks — git hook management."""

import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from evolution.config import EvoConfig
from evolution.hooks import (
    HookManager,
    _MARKER_START,
    _MARKER_END,
    _VALID_TRIGGERS,
    _THRESHOLD_MAP,
    _STATUS_RANK,
    _build_hook_script,
    _strip_evo_block,
    _find_git_dir,
    _hooks_dir,
)


# ──────────────── Helpers ────────────────

def _init_git_repo(repo_path: Path) -> Path:
    """Create a minimal git repository structure at repo_path."""
    git_dir = repo_path / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    return git_dir


def _make_config(tmp_path: Path, **overrides) -> EvoConfig:
    """Create an EvoConfig with optional overrides."""
    cfg = EvoConfig(path=tmp_path / "config.toml")
    for key, value in overrides.items():
        cfg.set(key, value)
    return cfg


def _read_hook(hook_path: Path) -> str:
    """Read a hook file's content."""
    return hook_path.read_text()


# ──────────────── TestBuildHookScript ────────────────


class TestBuildHookScript:
    def test_contains_markers(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        assert _MARKER_START in script
        assert _MARKER_END in script

    def test_markers_are_first_and_last_meaningful_lines(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        lines = [ln.strip() for ln in script.strip().splitlines() if ln.strip()]
        assert lines[0] == _MARKER_START
        assert lines[-1] == _MARKER_END

    def test_background_flag_appends_ampersand(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        assert "_evo_hook_run &" in script

    def test_foreground_no_ampersand(self):
        script = _build_hook_script(
            background=False, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        # Should have the call without &
        assert "_evo_hook_run\n" in script
        # Make sure no background suffix
        assert "_evo_hook_run &" not in script

    def test_families_flag_included(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="git,ci",
        )
        assert "--families git,ci" in script

    def test_families_flag_absent_when_empty(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        assert "--families" not in script

    def test_auto_open_includes_report_command(self):
        script = _build_hook_script(
            background=True, auto_open=True, notify=False,
            min_severity="concern", families="",
        )
        assert "evo report" in script
        assert "--open" in script

    def test_auto_open_disabled_no_report(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        assert "evo report" not in script

    def test_notify_includes_notification_block(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=True,
            min_severity="concern", families="",
        )
        # macOS notification
        assert "osascript" in script
        # Linux notification
        assert "notify-send" in script

    def test_notify_disabled_no_notification(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        assert "osascript" not in script
        assert "notify-send" not in script

    def test_min_severity_threshold_embedded(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="critical", families="",
        )
        # The min_rank for critical should be 3 (action_required)
        expected_rank = _STATUS_RANK[_THRESHOLD_MAP["critical"]]
        assert str(expected_rank) in script

    def test_evo_check_before_run(self):
        """Script should verify evo is on PATH before running."""
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        assert "command -v evo" in script

    def test_uses_evo_analyze_json_quiet(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="concern", families="",
        )
        assert "evo analyze . --json --quiet" in script

    def test_config_comment_present(self):
        script = _build_hook_script(
            background=False, auto_open=True, notify=True,
            min_severity="watch", families="git",
        )
        assert "min_severity=watch" in script
        assert "background=False" in script

    def test_all_severity_levels(self):
        """All valid severity levels should produce a script without error."""
        for severity in _THRESHOLD_MAP:
            script = _build_hook_script(
                background=True, auto_open=False, notify=False,
                min_severity=severity, families="",
            )
            assert _MARKER_START in script
            assert _MARKER_END in script

    def test_unknown_severity_uses_fallback(self):
        script = _build_hook_script(
            background=True, auto_open=False, notify=False,
            min_severity="nonexistent", families="",
        )
        # Should default to needs_attention (rank 2)
        assert _MARKER_START in script


# ──────────────── TestStripEvoBlock ────────────────


class TestStripEvoBlock:
    def test_removes_markers_and_content(self):
        content = f"before\n{_MARKER_START}\nsome hook code\n{_MARKER_END}\nafter\n"
        result = _strip_evo_block(content)
        assert _MARKER_START not in result
        assert _MARKER_END not in result
        assert "some hook code" not in result

    def test_preserves_surrounding_content(self):
        content = f"#!/bin/sh\necho hello\n{_MARKER_START}\nevo stuff\n{_MARKER_END}\necho bye\n"
        result = _strip_evo_block(content)
        assert "echo hello" in result
        assert "echo bye" in result

    def test_no_markers_returns_unchanged(self):
        content = "#!/bin/sh\necho hello\n"
        result = _strip_evo_block(content)
        assert result == content

    def test_empty_block(self):
        content = f"before\n{_MARKER_START}\n{_MARKER_END}\nafter\n"
        result = _strip_evo_block(content)
        assert "before" in result
        assert "after" in result
        assert _MARKER_START not in result

    def test_trims_trailing_blank_lines(self):
        content = f"before\n{_MARKER_START}\ncode\n{_MARKER_END}\n\n\n\n"
        result = _strip_evo_block(content)
        assert not result.endswith("\n\n\n")

    def test_only_markers(self):
        content = f"{_MARKER_START}\ncode\n{_MARKER_END}\n"
        result = _strip_evo_block(content)
        assert _MARKER_START not in result
        assert "code" not in result


# ──────────────── TestFindGitDir ────────────────


class TestFindGitDir:
    def test_regular_repo(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        result = _find_git_dir(tmp_path)
        assert result == git_dir

    def test_no_git_dir(self, tmp_path):
        result = _find_git_dir(tmp_path)
        assert result is None

    def test_worktree_file(self, tmp_path):
        """When .git is a file pointing to a worktree gitdir."""
        actual_gitdir = tmp_path / "main-repo" / ".git" / "worktrees" / "wt1"
        actual_gitdir.mkdir(parents=True)
        worktree = tmp_path / "worktree1"
        worktree.mkdir()
        dot_git = worktree / ".git"
        dot_git.write_text(f"gitdir: {actual_gitdir}")
        result = _find_git_dir(worktree)
        assert result == actual_gitdir

    def test_worktree_relative_path(self, tmp_path):
        """Worktree .git file with a relative gitdir path."""
        actual_gitdir = tmp_path / "main" / ".git" / "worktrees" / "wt"
        actual_gitdir.mkdir(parents=True)
        worktree = tmp_path / "main" / "wt"
        worktree.mkdir(parents=True)
        dot_git = worktree / ".git"
        # Relative path from worktree to the gitdir
        dot_git.write_text("gitdir: ../.git/worktrees/wt")
        result = _find_git_dir(worktree)
        assert result is not None
        assert result.resolve() == actual_gitdir.resolve()

    def test_git_file_with_bad_content(self, tmp_path):
        """A .git file that doesn't start with gitdir: returns None."""
        dot_git = tmp_path / ".git"
        dot_git.write_text("not a valid gitdir reference")
        result = _find_git_dir(tmp_path)
        assert result is None


# ──────────────── TestHooksDir ────────────────


class TestHooksDir:
    def test_default_hooks_dir(self, tmp_path):
        """Without core.hooksPath, returns git_dir/hooks."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        # Mock subprocess to simulate no core.hooksPath
        with patch("evolution.hooks.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="",
            )
            result = _hooks_dir(git_dir)
        assert result == git_dir / "hooks"

    def test_custom_hooks_path_absolute(self, tmp_path):
        """core.hooksPath with an absolute path."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        custom_hooks = tmp_path / "my-hooks"
        custom_hooks.mkdir()
        with patch("evolution.hooks.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=str(custom_hooks) + "\n", stderr="",
            )
            result = _hooks_dir(git_dir)
        assert result == custom_hooks

    def test_custom_hooks_path_relative(self, tmp_path):
        """core.hooksPath with a relative path resolves from repo root."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        custom_hooks = tmp_path / "custom-hooks"
        custom_hooks.mkdir()
        with patch("evolution.hooks.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="custom-hooks\n", stderr="",
            )
            result = _hooks_dir(git_dir)
        # Relative path resolved against git_dir.parent (repo root)
        assert result == (git_dir.parent / "custom-hooks").resolve()

    def test_subprocess_exception_falls_back(self, tmp_path):
        """If git config fails with an exception, fall back to default."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        with patch("evolution.hooks.subprocess.run", side_effect=OSError("no git")):
            result = _hooks_dir(git_dir)
        assert result == git_dir / "hooks"


# ──────────────── TestHookManagerInstall ────────────────


class TestHookManagerInstall:
    def test_creates_hook_file(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install(trigger="post-commit")
        assert result["ok"] is True
        hook_path = Path(result["hook_path"])
        assert hook_path.exists()
        assert result["trigger"] == "post-commit"

    def test_hook_content_has_shebang(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        content = _read_hook(hook_path)
        assert content.startswith("#!/bin/sh")

    def test_hook_content_has_markers(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        content = _read_hook(hook_path)
        assert _MARKER_START in content
        assert _MARKER_END in content

    def test_hook_is_executable(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        mode = hook_path.stat().st_mode
        assert mode & stat.S_IXUSR
        assert mode & stat.S_IXGRP
        assert mode & stat.S_IXOTH

    def test_no_git_dir_returns_error(self, tmp_path):
        """Install on a directory without .git should fail gracefully."""
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install(trigger="post-commit")
        assert result["ok"] is False
        assert "Not a git repository" in result["error"]

    def test_invalid_trigger_returns_error(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install(trigger="pre-rebase")
        assert result["ok"] is False
        assert "Invalid trigger" in result["error"]

    def test_preserves_existing_hook_content(self, tmp_path):
        """When a hook file already exists, EE appends its block."""
        _init_git_repo(tmp_path)
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        hook_path.write_text("#!/bin/sh\necho 'existing hook logic'\n")
        hook_path.chmod(0o755)

        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install(trigger="post-commit")
        assert result["ok"] is True
        content = _read_hook(hook_path)
        assert "existing hook logic" in content
        assert _MARKER_START in content

    def test_replaces_previous_ee_block_on_reinstall(self, tmp_path):
        """Re-installing replaces the old EE block, not duplicates it."""
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)

        # Install twice
        hm.install(trigger="post-commit")
        hm.install(trigger="post-commit")

        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        content = _read_hook(hook_path)
        # Only one start marker should be present
        assert content.count(_MARKER_START) == 1
        assert content.count(_MARKER_END) == 1

    def test_default_trigger_from_config(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg", **{"hooks.trigger": "pre-push"})
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install()
        assert result["ok"] is True
        assert result["trigger"] == "pre-push"
        hook_path = tmp_path / ".git" / "hooks" / "pre-push"
        assert hook_path.exists()

    def test_default_trigger_post_commit(self, tmp_path):
        """Without config override, default trigger is post-commit."""
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install()
        assert result["trigger"] == "post-commit"

    def test_pre_push_trigger(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install(trigger="pre-push")
        assert result["ok"] is True
        assert result["trigger"] == "pre-push"
        hook_path = tmp_path / ".git" / "hooks" / "pre-push"
        assert hook_path.exists()

    def test_hooks_dir_created_if_missing(self, tmp_path):
        """Install should create the hooks directory if it does not exist."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        # Deliberately do NOT create hooks/ subdir
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install(trigger="post-commit")
        assert result["ok"] is True
        assert (tmp_path / ".git" / "hooks" / "post-commit").exists()

    def test_config_values_reflected_in_script(self, tmp_path):
        """Config options should affect the generated hook script."""
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg", **{
            "hooks.background": False,
            "hooks.auto_open": False,
            "hooks.notify": False,
            "hooks.min_severity": "critical",
            "hooks.families": "git,ci",
        })
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        content = _read_hook(hook_path)
        assert "--families git,ci" in content
        assert "background=False" in content
        assert "min_severity=critical" in content
        # No notification block
        assert "osascript" not in content

    def test_existing_hook_without_newline_at_end(self, tmp_path):
        """Existing hook that doesn't end with newline should still work."""
        _init_git_repo(tmp_path)
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        hook_path.write_text("#!/bin/sh\necho hello")  # no trailing newline
        hook_path.chmod(0o755)

        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.install(trigger="post-commit")
        assert result["ok"] is True
        content = _read_hook(hook_path)
        assert "echo hello" in content
        assert _MARKER_START in content


# ──────────────── TestHookManagerUninstall ────────────────


class TestHookManagerUninstall:
    def test_removes_ee_block(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        result = hm.uninstall()
        assert result["ok"] is True
        assert len(result["removed"]) == 1

    def test_keeps_other_hook_content(self, tmp_path):
        _init_git_repo(tmp_path)
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        hook_path.write_text("#!/bin/sh\necho 'user hook'\n")
        hook_path.chmod(0o755)

        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hm.uninstall()
        # File should still exist with user content
        assert hook_path.exists()
        content = _read_hook(hook_path)
        assert "user hook" in content
        assert _MARKER_START not in content

    def test_deletes_empty_hook_file(self, tmp_path):
        """If only EE content was in the hook, the file should be deleted."""
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        assert hook_path.exists()
        hm.uninstall()
        # File that only had shebang + EE block should be deleted
        assert not hook_path.exists()

    def test_deletes_shebang_only_file(self, tmp_path):
        """A file with only #!/bin/sh after block removal should be deleted."""
        _init_git_repo(tmp_path)
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        hook_path.write_text(
            f"#!/bin/sh\n{_MARKER_START}\nsome code\n{_MARKER_END}\n"
        )
        hook_path.chmod(0o755)

        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.uninstall()
        assert not hook_path.exists()

    def test_no_hooks_returns_empty_removed(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.uninstall()
        assert result["ok"] is True
        assert result["removed"] == []

    def test_no_git_dir_returns_error(self, tmp_path):
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.uninstall()
        assert result["ok"] is False
        assert "Not a git repository" in result["error"]

    def test_uninstall_both_triggers(self, tmp_path):
        """If both post-commit and pre-push have EE blocks, both are cleaned."""
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hm.install(trigger="pre-push")
        result = hm.uninstall()
        assert result["ok"] is True
        assert len(result["removed"]) == 2

    def test_hook_without_markers_not_touched(self, tmp_path):
        """Hook files without EE markers should be left alone."""
        _init_git_repo(tmp_path)
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        original = "#!/bin/sh\necho 'not evo'\n"
        hook_path.write_text(original)
        hook_path.chmod(0o755)

        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        result = hm.uninstall()
        assert result["removed"] == []
        assert _read_hook(hook_path) == original


# ──────────────── TestHookManagerIsInstalled ────────────────


class TestHookManagerIsInstalled:
    def test_true_after_install(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        assert hm.is_installed() is True

    def test_false_before_install(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        assert hm.is_installed() is False

    def test_false_after_uninstall(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hm.uninstall()
        assert hm.is_installed() is False

    def test_false_without_git_dir(self, tmp_path):
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        assert hm.is_installed() is False

    def test_detects_pre_push(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="pre-push")
        assert hm.is_installed() is True

    def test_detects_manually_placed_marker(self, tmp_path):
        """A manually written hook with EE markers should be detected."""
        _init_git_repo(tmp_path)
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        hook_path.write_text(f"#!/bin/sh\n{_MARKER_START}\n# custom\n{_MARKER_END}\n")
        hook_path.chmod(0o755)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        assert hm.is_installed() is True


# ──────────────── TestHookManagerStatus ────────────────


class TestHookManagerStatus:
    def test_status_shape(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        s = hm.status()
        assert "installed" in s
        assert "trigger" in s
        assert "hook_path" in s
        assert "config" in s
        assert isinstance(s["config"], dict)

    def test_not_installed_status(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        s = hm.status()
        assert s["installed"] is False
        assert s["trigger"] is None
        assert s["hook_path"] is None

    def test_installed_status(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        s = hm.status()
        assert s["installed"] is True
        assert s["trigger"] == "post-commit"
        assert s["hook_path"] is not None
        assert "post-commit" in s["hook_path"]

    def test_config_snapshot_keys(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        s = hm.status()
        config_keys = s["config"]
        assert "trigger" in config_keys
        assert "auto_open" in config_keys
        assert "notify" in config_keys
        assert "min_severity" in config_keys
        assert "families" in config_keys
        assert "background" in config_keys

    def test_status_without_git_dir(self, tmp_path):
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        s = hm.status()
        assert s["installed"] is False
        assert s["trigger"] is None

    def test_status_reflects_pre_push_trigger(self, tmp_path):
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="pre-push")
        s = hm.status()
        assert s["trigger"] == "pre-push"

    def test_status_returns_first_installed_trigger(self, tmp_path):
        """When both triggers are installed, status returns the first match."""
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)
        hm.install(trigger="post-commit")
        hm.install(trigger="pre-push")
        s = hm.status()
        # _VALID_TRIGGERS order is ("post-commit", "pre-push")
        assert s["trigger"] == "post-commit"


# ──────────────── TestHookManagerDefaults ────────────────


class TestHookManagerDefaults:
    def test_default_config_loaded(self, tmp_path):
        """HookManager creates a default EvoConfig if none provided."""
        _init_git_repo(tmp_path)
        hm = HookManager(tmp_path)
        assert hm.config is not None

    def test_repo_path_resolved(self, tmp_path):
        _init_git_repo(tmp_path)
        hm = HookManager(str(tmp_path))
        assert hm.repo_path == tmp_path.resolve()


# ──────────────── TestConstants ────────────────


class TestConstants:
    def test_valid_triggers(self):
        assert "post-commit" in _VALID_TRIGGERS
        assert "pre-push" in _VALID_TRIGGERS
        assert len(_VALID_TRIGGERS) == 2

    def test_threshold_map_keys(self):
        assert set(_THRESHOLD_MAP.keys()) == {"critical", "concern", "watch", "info"}

    def test_threshold_map_values_in_status_rank(self):
        for level in _THRESHOLD_MAP.values():
            assert level in _STATUS_RANK

    def test_status_rank_ordering(self):
        assert _STATUS_RANK["all_clear"] < _STATUS_RANK["worth_monitoring"]
        assert _STATUS_RANK["worth_monitoring"] < _STATUS_RANK["needs_attention"]
        assert _STATUS_RANK["needs_attention"] < _STATUS_RANK["action_required"]

    def test_markers_are_comments(self):
        assert _MARKER_START.startswith("#")
        assert _MARKER_END.startswith("#")


# ──────────────── TestHooksDirRealGit ────────────────


class TestHooksDirWithCustomPath:
    def test_custom_hooks_path_used_by_install(self, tmp_path):
        """Install should respect core.hooksPath when placing hooks."""
        _init_git_repo(tmp_path)
        custom_hooks = tmp_path / "my-custom-hooks"
        custom_hooks.mkdir()

        cfg = _make_config(tmp_path / "cfg")

        with patch("evolution.hooks.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=str(custom_hooks) + "\n", stderr="",
            )
            hm = HookManager(tmp_path, config=cfg)
            result = hm.install(trigger="post-commit")

        assert result["ok"] is True
        assert custom_hooks.name in result["hook_path"]
        assert (custom_hooks / "post-commit").exists()


# ──────────────── TestRoundTrip ────────────────


class TestRoundTrip:
    def test_install_uninstall_cycle(self, tmp_path):
        """Full install -> verify -> uninstall -> verify cycle."""
        _init_git_repo(tmp_path)
        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)

        # Start clean
        assert hm.is_installed() is False

        # Install
        result = hm.install(trigger="post-commit")
        assert result["ok"] is True
        assert hm.is_installed() is True

        # Uninstall
        result = hm.uninstall()
        assert result["ok"] is True
        assert hm.is_installed() is False

    def test_install_reinstall_preserves_user_content(self, tmp_path):
        """User content survives multiple install/reinstall cycles."""
        _init_git_repo(tmp_path)
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        hook_path.write_text("#!/bin/sh\necho 'my custom hook'\n")
        hook_path.chmod(0o755)

        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)

        # First install
        hm.install(trigger="post-commit")
        content_after_first = _read_hook(hook_path)
        assert "my custom hook" in content_after_first
        assert content_after_first.count(_MARKER_START) == 1

        # Second install (re-install)
        hm.install(trigger="post-commit")
        content_after_second = _read_hook(hook_path)
        assert "my custom hook" in content_after_second
        assert content_after_second.count(_MARKER_START) == 1

    def test_install_uninstall_with_user_content(self, tmp_path):
        """After uninstall, user content remains; re-install adds block back."""
        _init_git_repo(tmp_path)
        hook_path = tmp_path / ".git" / "hooks" / "post-commit"
        hook_path.write_text("#!/bin/sh\necho 'preserved'\n")
        hook_path.chmod(0o755)

        cfg = _make_config(tmp_path / "cfg")
        hm = HookManager(tmp_path, config=cfg)

        hm.install(trigger="post-commit")
        hm.uninstall()
        content = _read_hook(hook_path)
        assert "preserved" in content
        assert _MARKER_START not in content

        # Re-install
        hm.install(trigger="post-commit")
        content = _read_hook(hook_path)
        assert "preserved" in content
        assert _MARKER_START in content
