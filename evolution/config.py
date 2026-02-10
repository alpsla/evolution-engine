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
    "sync.privacy_level": 0,          # 0=nothing, 1=metadata, 2=anonymized digests
    "sync.registry_url": "https://registry.evo.dev/v1",
    "sync.auto_pull": False,           # auto-pull community patterns on analyze
    "llm.enabled": False,
    "llm.provider": "anthropic",
    "llm.model": "claude-sonnet-4-5-20250929",
    "analyze.families": "",            # empty = auto-detect
    "analyze.json_output": False,
    "report.theme": "dark",
    "telemetry.enabled": False,        # opt-in anonymous usage stats
    "telemetry.prompted": False,       # whether we've asked the user
}


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
