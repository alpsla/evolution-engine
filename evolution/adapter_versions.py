"""
Adapter Version Checker — PyPI version lookups for update reminders.

Uses stdlib urllib.request only (no new dependencies). Results are cached
to ~/.evo/version_cache.json with a 24-hour TTL.

Usage:
    from evolution.adapter_versions import check_pypi_version, check_all_updates

    latest = check_pypi_version("evo-adapter-jenkins")
    updates = check_all_updates({"evo-adapter-jenkins": "0.1.0"})

CLI:
    evo adapter check-updates
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evolution.config import EvoConfig


PYPI_URL = "https://pypi.org/pypi/{package}/json"
CACHE_TTL_SECONDS = 86400  # 24 hours
SELF_UPDATE_INTERVAL_SECONDS = 604800  # 7 days


def _cache_path() -> Path:
    """Return path to the version cache file."""
    cfg_dir = Path.home() / ".evo"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "version_cache.json"


def _load_cache() -> dict:
    """Load the version cache from disk."""
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict):
    """Save the version cache to disk."""
    try:
        _cache_path().write_text(json.dumps(cache, indent=2))
    except OSError:
        pass


def check_pypi_version(package_name: str, use_cache: bool = True) -> Optional[str]:
    """Check PyPI for the latest version of a package.

    Args:
        package_name: PyPI package name (e.g. "evo-adapter-jenkins").
        use_cache: If True, use cached result if fresh (24h TTL).

    Returns:
        Latest version string, or None if lookup fails.
    """
    now = time.time()

    # Check cache
    if use_cache:
        cache = _load_cache()
        entry = cache.get(package_name)
        if entry and (now - entry.get("checked_at", 0)) < CACHE_TTL_SECONDS:
            return entry.get("latest_version")

    # Query PyPI
    url = PYPI_URL.format(package=package_name)
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            version = data.get("info", {}).get("version")
    except (urllib.error.URLError, json.JSONDecodeError, OSError, KeyError):
        return None

    # Update cache
    if version:
        cache = _load_cache()
        cache[package_name] = {
            "latest_version": version,
            "checked_at": now,
        }
        _save_cache(cache)

    return version


def check_all_updates(installed_plugins: dict[str, str],
                      use_cache: bool = True) -> list[dict]:
    """Check for updates across all installed plugin adapters.

    Args:
        installed_plugins: Dict of {package_name: current_version}.
        use_cache: If True, use cached results.

    Returns:
        List of dicts: [{"name": ..., "current": ..., "latest": ...}, ...]
        Only includes packages where latest > current.
    """
    updates = []
    for name, current in installed_plugins.items():
        latest = check_pypi_version(name, use_cache=use_cache)
        if latest and latest != current:
            updates.append({
                "name": name,
                "current": current,
                "latest": latest,
            })
    return updates


def check_self_update_nudge(use_cache: bool = True) -> Optional[str]:
    """Check if evolution-engine itself has an update available.

    Checks at most once per 7 days (configurable via config).

    Returns:
        A one-line nudge string, or None if up-to-date or check skipped.
    """
    from evolution import __version__

    cfg = EvoConfig()
    if not cfg.get("adapter.check_updates"):
        return None

    # Check interval
    last_check = cfg.get("adapter.last_version_check", "")
    if last_check and use_cache:
        try:
            last_dt = datetime.fromisoformat(last_check)
            now = datetime.now(timezone.utc)
            elapsed = (now - last_dt).total_seconds()
            if elapsed < SELF_UPDATE_INTERVAL_SECONDS:
                return None
        except (ValueError, TypeError):
            pass

    latest = check_pypi_version("evolution-engine", use_cache=use_cache)
    if latest is None:
        return None

    # Record check time
    cfg.set("adapter.last_version_check",
            datetime.now(timezone.utc).isoformat())

    if latest != __version__:
        return (f"Update available: evolution-engine {__version__} → {latest}. "
                f"Run: pip install --upgrade evolution-engine")

    return None
