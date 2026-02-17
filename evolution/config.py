"""
User configuration management for Evolution Engine.

Manages persistent user preferences stored in ~/.evo/config.toml.
Used by KB sync, CLI defaults, and other components that need
cross-session settings.

Usage:
    from evolution.config import EvoConfig
    cfg = EvoConfig()
    cfg.get("sync.privacy_level")       # → 0
    cfg.set("sync.privacy_level", 1)
    cfg.get("sync.registry_url")        # → default URL
"""

import os
from pathlib import Path
from typing import Any, Optional


# ─── Defaults ───

_DEFAULTS = {
    "sync.privacy_level": 0,          # 0=nothing, 1=share anonymized patterns
    "sync.registry_url": "https://codequal.dev/api",
    "sync.auto_pull": False,           # auto-pull community patterns on analyze
    "sync.share_prompted": False,      # whether sharing prompt has been shown
    "analyze.families": "",            # empty = auto-detect
    "analyze.json_output": False,
    "telemetry.enabled": False,        # opt-in anonymous usage stats
    "telemetry.prompted": False,       # whether we've asked the user
    "adapter.check_blocklist": True,   # check blocklist during adapter detection
    "adapter.check_updates": True,     # show update reminders for adapters
    "adapter.last_version_check": "",  # ISO timestamp of last PyPI version check
    "hooks.trigger": "post-commit",
    "hooks.auto_open": True,
    "hooks.notify": True,
    "hooks.min_severity": "concern",
    "hooks.families": "",
    "hooks.background": True,
    "init.integration": "",
    "init.first_run_count": 0,
    "stats.analyze_count": 0,           # lifetime analysis count (for activation metrics)
    "stats.first_analyze_ts": "",       # ISO timestamp of first ever analysis
    "stats.last_analyze_ts": "",        # ISO timestamp of most recent analysis
}


# ─── Config Metadata ───
# Describes each key for evo setup (interactive), evo config list (grouped),
# and evo setup --ui (form generation). Groups define display sections.

_GROUPS = {
    "analyze": {"label": "Analysis", "order": 1, "description": "What to analyze and output format"},
    "hooks": {"label": "Hooks", "order": 2, "description": "Automatic background analysis on commit/push"},
    "sync": {"label": "Patterns & Sync", "order": 3, "description": "Community pattern sharing"},
    "adapter": {"label": "Adapters", "order": 4, "description": "Plugin and adapter management"},
    "telemetry": {"label": "Telemetry", "order": 5, "description": "Anonymous usage statistics"},
    "init": {"label": "Setup", "order": 6, "description": "Initial setup state (managed by evo init)"},
    "stats": {"label": "Usage Stats", "order": 7, "description": "Internal usage counters for telemetry"},
}

_METADATA = {
    # ── Analysis ──
    "analyze.families": {
        "description": "Restrict to specific families (empty = auto-detect)",
        "type": "str",
        "group": "analyze",
        "display": "Which signal families should EE analyze?",
        "placeholder": "git,ci,dependency",
    },
    "analyze.json_output": {
        "description": "Machine-readable JSON output",
        "type": "bool",
        "group": "analyze",
        "display": "Default to JSON output?",
    },
    # ── Hooks ──
    "hooks.trigger": {
        "description": "When to run: post-commit or pre-push",
        "type": "choice",
        "allowed": ["post-commit", "pre-push"],
        "group": "hooks",
        "display": "When should EE run automatically?",
    },
    "hooks.min_severity": {
        "description": "Notification threshold",
        "type": "choice",
        "allowed": ["critical", "concern", "watch", "info"],
        "allowed_labels": {
            "critical": "Only critical issues (Action Required)",
            "concern": "Important findings (Action Required + Needs Attention)",
            "watch": "Everything worth noting",
            "info": "Everything",
        },
        "group": "hooks",
        "display": "When should EE notify you?",
    },
    "hooks.auto_open": {
        "description": "Open report in browser when findings detected",
        "type": "bool",
        "group": "hooks",
        "display": "Open report in browser automatically?",
    },
    "hooks.notify": {
        "description": "Desktop notification when findings detected",
        "type": "bool",
        "group": "hooks",
        "display": "Desktop notifications enabled?",
    },
    "hooks.families": {
        "description": "Override families for hook runs (empty = auto-detect)",
        "type": "str",
        "group": "hooks",
        "display": "Restrict hook analysis to specific families?",
        "placeholder": "git,ci,dependency",
    },
    "hooks.background": {
        "description": "Non-blocking hook execution",
        "type": "bool",
        "group": "hooks",
        "display": "Run analysis in background (non-blocking)?",
    },
    # ── Patterns & Sync ──
    "sync.privacy_level": {
        "description": "Share anonymized patterns with community",
        "type": "choice",
        "allowed": [0, 1],
        "allowed_labels": {
            0: "Nothing shared",
            1: "Share anonymized patterns",
        },
        "group": "sync",
        "display": "Share anonymized patterns with community?",
        "pro": True,
    },
    "sync.registry_url": {
        "description": "Pattern registry endpoint",
        "type": "str",
        "group": "sync",
        "display": "Registry URL?",
        "advanced": True,
    },
    "sync.auto_pull": {
        "description": "Auto-pull community patterns on analyze",
        "type": "bool",
        "group": "sync",
        "display": "Auto-pull community patterns?",
        "pro": True,
    },
    "sync.share_prompted": {
        "description": "Whether sharing prompt has been shown",
        "type": "bool",
        "group": "sync",
        "internal": True,
    },
    # ── Adapters ──
    "adapter.check_blocklist": {
        "description": "Check blocklist during adapter detection",
        "type": "bool",
        "group": "adapter",
        "display": "Check adapter blocklist?",
    },
    "adapter.check_updates": {
        "description": "Show update reminders for installed adapters",
        "type": "bool",
        "group": "adapter",
        "display": "Check for adapter updates?",
    },
    "adapter.last_version_check": {
        "description": "Timestamp of last PyPI version check",
        "type": "str",
        "group": "adapter",
        "internal": True,
    },
    # ── Telemetry ──
    "telemetry.enabled": {
        "description": "Anonymous usage statistics",
        "type": "bool",
        "group": "telemetry",
        "display": "Send anonymous usage statistics?",
    },
    "telemetry.prompted": {
        "description": "Whether telemetry prompt has been shown",
        "type": "bool",
        "group": "telemetry",
        "internal": True,
    },
    # ── Init (internal) ──
    "init.integration": {
        "description": "Integration path chosen during setup",
        "type": "str",
        "group": "init",
        "internal": True,
    },
    "init.first_run_count": {
        "description": "Tracks runs for first-run hints",
        "type": "int",
        "group": "init",
        "internal": True,
    },
    # ── Stats (internal, for telemetry metrics) ──
    "stats.analyze_count": {
        "description": "Lifetime analysis count",
        "type": "int",
        "group": "stats",
        "internal": True,
    },
    "stats.first_analyze_ts": {
        "description": "Timestamp of first analysis",
        "type": "str",
        "group": "stats",
        "internal": True,
    },
    "stats.last_analyze_ts": {
        "description": "Timestamp of most recent analysis",
        "type": "str",
        "group": "stats",
        "internal": True,
    },
}


def config_groups() -> dict:
    """Return group definitions ordered by display order."""
    return dict(sorted(_GROUPS.items(), key=lambda g: g[1]["order"]))


def config_metadata(key: str) -> dict:
    """Return metadata for a config key, or empty dict if not found."""
    return _METADATA.get(key, {})


def config_keys_for_group(group: str, include_internal: bool = False) -> list[str]:
    """Return config keys belonging to a group, in definition order."""
    keys = []
    for key, meta in _METADATA.items():
        if meta.get("group") != group:
            continue
        if meta.get("internal") and not include_internal:
            continue
        keys.append(key)
    return keys


def _config_dir() -> Path:
    """Return the config directory (~/.evo/)."""
    return Path(os.environ.get("EVO_CONFIG_DIR", Path.home() / ".evo"))


def _config_path() -> Path:
    """Return the config file path (~/.evo/config.toml)."""
    return _config_dir() / "config.toml"


class EvoConfig:
    """Read/write user configuration from ~/.evo/config.toml.

    Uses a simple key=value format with dotted keys (e.g. sync.privacy_level=1).
    Falls back to _DEFAULTS for any unset key.
    """

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _config_path()
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load config from disk. Creates file if missing."""
        self._data = {}
        if not self._path.exists():
            return
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            self._data[key] = _parse_value(value)

    def _save(self):
        """Write config to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Evolution Engine configuration", ""]
        # Group by prefix
        groups: dict[str, list[tuple[str, Any]]] = {}
        for key in sorted(self._data):
            prefix = key.split(".")[0] if "." in key else "_"
            groups.setdefault(prefix, []).append((key, self._data[key]))
        for prefix, items in groups.items():
            lines.append(f"# {prefix}")
            for key, value in items:
                lines.append(f"{key} = {_format_value(value)}")
            lines.append("")
        self._path.write_text("\n".join(lines))

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value, falling back to built-in defaults."""
        if key in self._data:
            return self._data[key]
        if key in _DEFAULTS:
            return _DEFAULTS[key]
        return default

    def set(self, key: str, value: Any):
        """Set a config value and persist to disk."""
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> bool:
        """Remove a config key. Returns True if it existed."""
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def all(self) -> dict[str, Any]:
        """Return all effective settings (user overrides + defaults)."""
        merged = dict(_DEFAULTS)
        merged.update(self._data)
        return merged

    def user_overrides(self) -> dict[str, Any]:
        """Return only explicitly set values (not defaults)."""
        return dict(self._data)

    @property
    def path(self) -> Path:
        return self._path


# ─── Value Parsing ───

def _parse_value(raw: str) -> Any:
    """Parse a TOML-like value string into a Python type."""
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    # Try int
    try:
        return int(raw)
    except ValueError:
        pass
    # Try float
    try:
        return float(raw)
    except ValueError:
        pass
    # Strip quotes
    if (raw.startswith('"') and raw.endswith('"')) or \
       (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    return raw


def _format_value(value: Any) -> str:
    """Format a Python value for config file."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        if " " in value or not value:
            return f'"{value}"'
        return value
    return str(value)
