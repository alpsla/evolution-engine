"""
Git hook management for Evolution Engine.

Installs/uninstalls git hooks that run ``evo analyze`` automatically
on commit or push, with threshold-based notifications.

Usage:
    from evolution.hooks import HookManager
    hm = HookManager(repo_path)
    hm.install()          # Install hook based on config
    hm.uninstall()        # Remove EE hooks
    hm.is_installed()     # Check if hooks are present
    hm.status()           # Return dict with hook state
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from evolution.config import EvoConfig

# ─── Marker comments ───
# These delimit the Evolution Engine section inside a hook script.
# They allow install/uninstall to operate on EE's block without
# disturbing any other hook logic already present in the file.

_MARKER_START = "# evo-hook-start"
_MARKER_END = "# evo-hook-end"

_VALID_TRIGGERS = ("post-commit", "pre-push")

# Threshold → minimum advisory level name used in the inline Python
# filter inside the generated shell script.  The mapping mirrors
# ``evolution.friendly.status_meets_threshold`` but is evaluated inside
# the hook without importing the engine, keeping the hook lightweight.
_THRESHOLD_MAP = {
    "critical": "action_required",
    "concern": "needs_attention",
    "watch": "worth_monitoring",
    "info": "all_clear",
}

# Severity rank used inside the hook script's Python one-liner.
_STATUS_RANK = {
    "all_clear": 0,
    "worth_monitoring": 1,
    "needs_attention": 2,
    "action_required": 3,
}


# ─── Hook Script Template ───

def _resolve_evo_path() -> str:
    """Find the full path to the ``evo`` executable.

    Checks (in order):
    1. Same bin directory as the running Python (venv-aware)
    2. ``shutil.which("evo")`` (system PATH)
    3. Falls back to ``"evo"`` (bare command)
    """
    # Check alongside the current Python (handles venv installs)
    bin_dir = Path(sys.executable).parent
    candidate = bin_dir / "evo"
    if candidate.exists():
        return str(candidate)
    # Fall back to PATH lookup
    found = shutil.which("evo")
    if found:
        return found
    return "evo"


def _build_hook_script(
    *,
    background: bool,
    auto_open: bool,
    notify: bool,
    min_severity: str,
    families: str,
    evo_path: str = "",
) -> str:
    """Return the shell snippet to embed inside a git hook file.

    The snippet is self-contained: it uses the resolved path to ``evo``,
    runs analysis, and optionally triggers notifications or opens a
    report in the browser, depending on the configured threshold.
    """

    evo_cmd = evo_path or _resolve_evo_path()

    min_level = _THRESHOLD_MAP.get(min_severity, "needs_attention")
    min_rank = _STATUS_RANK.get(min_level, 2)

    families_flag = f" --families {families}" if families else ""

    # Notification command differs per platform.
    if notify:
        notify_block = _notify_block()
    else:
        notify_block = ""

    bg_suffix = " &" if background else ""

    script = f"""{_MARKER_START}
# Evolution Engine — auto-analysis hook
# Installed by: evo hooks install
# Config: min_severity={min_severity}, background={background}
_EVO_CMD="{evo_cmd}"
_evo_hook_run() {{
    _evo_out=$("$_EVO_CMD" analyze . --json --quiet{families_flag} 2>/dev/null)
    _evo_rc=$?

    if [ $_evo_rc -ne 0 ]; then
        return 0  # analysis failed — do not block the user
    fi

    # Extract advisory status level, check threshold, and detect resolution progress
    _evo_level=$(echo "$_evo_out" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    level = data.get('advisory', {{}}).get('status', {{}}).get('level', 'all_clear')
    rank = {_STATUS_RANK}
    if rank.get(level, 0) >= {min_rank}:
        res = data.get('resolution')
        if res:
            resolved = res.get('resolved', 0)
            total = res.get('total_before', 0)
            remaining = res.get('persisting', 0) + res.get('new', 0) + res.get('regressions', 0)
            if total > 0:
                print('resolved ' + str(resolved) + ' of ' + str(total) + '|' + level)
            else:
                print(level)
        else:
            print(level)
except Exception:
    pass
" 2>/dev/null)

    if [ -z "$_evo_level" ]; then
        return 0  # below threshold or parse error
    fi
{_indent(notify_block, 4)}
{_indent(_open_block(auto_open, families_flag), 4)}
}}

if [ -x "$_EVO_CMD" ] || command -v "$_EVO_CMD" >/dev/null 2>&1; then
    _evo_hook_run{bg_suffix}
fi
{_MARKER_END}
"""
    return script


def _notify_block() -> str:
    """Return shell lines that send a desktop notification."""
    return """
# Parse resolution info (format: "resolved X of Y|level" or just "level")
_evo_resolution=$(echo "$_evo_level" | cut -d'|' -f1)
_evo_raw_level=$(echo "$_evo_level" | cut -d'|' -sf2)
if [ -z "$_evo_raw_level" ]; then
    _evo_raw_level="$_evo_level"
    _evo_msg="EE: advisory level $_evo_raw_level"
else
    _evo_msg="EE: $_evo_resolution"
fi
# Generate report with verification banner (compares last two runs)
"$_EVO_CMD" report . --verify 2>/dev/null
_evo_report="$(git rev-parse --show-toplevel 2>/dev/null)/.evo/report.html"
# Desktop notification (macOS / Linux)
if [ "$(uname)" = "Darwin" ]; then
    if command -v terminal-notifier >/dev/null 2>&1; then
        if [ -f "$_evo_report" ]; then
            terminal-notifier -title "Evolution Engine" -message "$_evo_msg" -sound default -open "file://$_evo_report" 2>/dev/null
        else
            terminal-notifier -title "Evolution Engine" -message "$_evo_msg" -sound default 2>/dev/null
        fi
    else
        osascript -e "display notification \\"$_evo_msg\\" with title \\"Evolution Engine\\"" 2>/dev/null
    fi
elif command -v notify-send >/dev/null 2>&1; then
    notify-send "Evolution Engine" "$_evo_msg" 2>/dev/null
fi"""


def _open_block(auto_open: bool, families_flag: str) -> str:
    """Return shell lines that open an HTML report in the browser."""
    if not auto_open:
        return ""
    return """
# Open report in browser (with verification banner)
"$_EVO_CMD" report . --open --verify""" + families_flag + " 2>/dev/null"


def _indent(text: str, spaces: int) -> str:
    """Indent every non-empty line of *text* by *spaces* spaces."""
    prefix = " " * spaces
    lines = text.splitlines()
    return "\n".join(
        (prefix + line) if line.strip() else line
        for line in lines
    )


# ─── Git directory helpers ───

def _find_git_dir(repo_path: Path) -> Optional[Path]:
    """Locate the .git directory (supports worktrees)."""
    dot_git = repo_path / ".git"
    if dot_git.is_dir():
        return dot_git
    # .git may be a file pointing to a worktree gitdir
    if dot_git.is_file():
        text = dot_git.read_text().strip()
        if text.startswith("gitdir:"):
            gitdir = Path(text.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = (repo_path / gitdir).resolve()
            return gitdir
    return None


def _hooks_dir(git_dir: Path) -> Path:
    """Return the hooks directory, respecting ``core.hooksPath`` if set."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            capture_output=True, text=True, timeout=5,
            cwd=str(git_dir.parent),
        )
        if result.returncode == 0 and result.stdout.strip():
            custom = Path(result.stdout.strip())
            if not custom.is_absolute():
                custom = (git_dir.parent / custom).resolve()
            return custom
    except Exception:
        pass
    return git_dir / "hooks"


# ─── HookManager ───

class HookManager:
    """Install, uninstall, and inspect Evolution Engine git hooks.

    Parameters
    ----------
    repo_path : str or Path
        Path to the repository root (where ``.git/`` lives).
    config : EvoConfig, optional
        User configuration.  A fresh ``EvoConfig()`` is loaded if omitted.
    """

    def __init__(self, repo_path: str | Path, config: Optional[EvoConfig] = None):
        self.repo_path = Path(repo_path).resolve()
        self.config = config or EvoConfig()
        self._git_dir = _find_git_dir(self.repo_path)

    # ── Public API ──

    def install(self, trigger: Optional[str] = None) -> dict[str, Any]:
        """Install the EE hook script into the repository.

        Parameters
        ----------
        trigger : str, optional
            ``"post-commit"`` or ``"pre-push"``.  Falls back to the
            ``hooks.trigger`` config value (default ``"post-commit"``).

        Returns
        -------
        dict
            ``{"ok": True, "hook_path": ..., "trigger": ...}`` on success,
            or ``{"ok": False, "error": ...}`` on failure.
        """
        trigger = trigger or self.config.get("hooks.trigger", "post-commit")
        if trigger not in _VALID_TRIGGERS:
            return {"ok": False, "error": f"Invalid trigger: {trigger!r}. Must be one of {_VALID_TRIGGERS}"}

        if self._git_dir is None:
            return {"ok": False, "error": f"Not a git repository: {self.repo_path}"}

        hooks = _hooks_dir(self._git_dir)
        hooks.mkdir(parents=True, exist_ok=True)
        hook_file = hooks / trigger

        script = _build_hook_script(
            background=self.config.get("hooks.background", True),
            auto_open=self.config.get("hooks.auto_open", True),
            notify=self.config.get("hooks.notify", True),
            min_severity=self.config.get("hooks.min_severity", "concern"),
            families=self.config.get("hooks.families", ""),
        )

        if hook_file.exists():
            existing = hook_file.read_text()
            # Remove any previous EE block before appending
            existing = _strip_evo_block(existing)
            # Append our block
            if not existing.endswith("\n"):
                existing += "\n"
            new_content = existing + "\n" + script
        else:
            # Create a brand-new hook file with a shebang
            new_content = "#!/bin/sh\n\n" + script

        hook_file.write_text(new_content)
        # Ensure the hook is executable
        hook_file.chmod(hook_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        return {"ok": True, "hook_path": str(hook_file), "trigger": trigger}

    def uninstall(self) -> dict[str, Any]:
        """Remove the EE hook section from all hook files.

        Only the lines between ``# evo-hook-start`` and ``# evo-hook-end``
        are removed.  If the resulting file is empty (or only a shebang),
        the file is deleted.

        Returns
        -------
        dict
            ``{"ok": True, "removed": [...]}`` with a list of cleaned
            hook paths, or ``{"ok": False, "error": ...}``.
        """
        if self._git_dir is None:
            return {"ok": False, "error": f"Not a git repository: {self.repo_path}"}

        hooks = _hooks_dir(self._git_dir)
        removed: list[str] = []

        for trigger in _VALID_TRIGGERS:
            hook_file = hooks / trigger
            if not hook_file.exists():
                continue
            content = hook_file.read_text()
            if _MARKER_START not in content:
                continue

            cleaned = _strip_evo_block(content)

            # If nothing meaningful remains, delete the file
            stripped = cleaned.strip()
            if not stripped or stripped == "#!/bin/sh":
                hook_file.unlink()
            else:
                hook_file.write_text(cleaned)

            removed.append(str(hook_file))

        return {"ok": True, "removed": removed}

    def is_installed(self) -> bool:
        """Return True if any hook file contains the EE marker."""
        if self._git_dir is None:
            return False

        hooks = _hooks_dir(self._git_dir)
        for trigger in _VALID_TRIGGERS:
            hook_file = hooks / trigger
            if hook_file.exists() and _MARKER_START in hook_file.read_text():
                return True
        return False

    def status(self) -> dict[str, Any]:
        """Return a summary dict describing the current hook state.

        Keys:
            installed (bool): Whether an EE hook is present.
            trigger (str | None): Which trigger is hooked (or None).
            hook_path (str | None): Path to the active hook file.
            config: Snapshot of all hooks.* config values.
        """
        info: dict[str, Any] = {
            "installed": False,
            "trigger": None,
            "hook_path": None,
            "config": {
                "trigger": self.config.get("hooks.trigger"),
                "auto_open": self.config.get("hooks.auto_open"),
                "notify": self.config.get("hooks.notify"),
                "min_severity": self.config.get("hooks.min_severity"),
                "families": self.config.get("hooks.families"),
                "background": self.config.get("hooks.background"),
            },
        }

        if self._git_dir is None:
            return info

        hooks = _hooks_dir(self._git_dir)
        for trigger in _VALID_TRIGGERS:
            hook_file = hooks / trigger
            if hook_file.exists() and _MARKER_START in hook_file.read_text():
                info["installed"] = True
                info["trigger"] = trigger
                info["hook_path"] = str(hook_file)
                break

        return info


# ─── Internal helpers ───

def _strip_evo_block(content: str) -> str:
    """Remove everything between (and including) the EE markers."""
    lines = content.splitlines(keepends=True)
    result: list[str] = []
    inside = False
    for line in lines:
        if line.strip() == _MARKER_START:
            inside = True
            continue
        if line.strip() == _MARKER_END:
            inside = False
            continue
        if not inside:
            result.append(line)
    # Remove trailing blank lines left behind
    text = "".join(result)
    while text.endswith("\n\n\n"):
        text = text[:-1]
    return text
