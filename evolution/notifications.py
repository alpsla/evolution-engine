"""
Notification System — Lightweight persistent notifications for EVO CLI.

Stores notifications in ~/.evo/notifications.json. Displayed after
`evo analyze` and `evo status`. Auto-expires after 30 days.

Notification sources:
  1. Adapter updates — installed plugins have newer PyPI versions
  2. Adapter discovery — prescan-detected tools have adapters on PyPI
  3. Pattern updates — community patterns available (requires sync.auto_pull)
  4. EE updates — evolution-engine itself has a new version

Privacy:
  - All checks use cached PyPI lookups (24h TTL, same as adapter_versions.py)
  - Respects DO_NOT_TRACK=1
  - No data is sent — only public PyPI metadata is fetched
  - Can be fully disabled via `evo config set adapter.check_updates false`

Usage:
    from evolution.notifications import check_and_notify, get_pending
    notifications = check_and_notify(repo_path=".", evo_dir=".evo")
    for n in get_pending():
        print(n["message"])
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("evo.notifications")

# Notification file location
NOTIFICATION_FILE = Path.home() / ".evo" / "notifications.json"

# Check interval: at most once per 24 hours
CHECK_INTERVAL_SECONDS = 86400

# Notifications expire after 30 days
EXPIRY_SECONDS = 30 * 86400

# Notification types
TYPE_ADAPTER_UPDATE = "adapter_update"
TYPE_ADAPTER_AVAILABLE = "adapter_available"
TYPE_PATTERN_UPDATE = "pattern_update"
TYPE_EE_UPDATE = "ee_update"


def _load_notifications() -> dict:
    """Load notification state from disk."""
    if not NOTIFICATION_FILE.exists():
        return {"last_check": 0, "items": []}
    try:
        return json.loads(NOTIFICATION_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"last_check": 0, "items": []}


def _save_notifications(state: dict):
    """Save notification state to disk."""
    try:
        NOTIFICATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        NOTIFICATION_FILE.write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def _prune_expired(state: dict) -> dict:
    """Remove expired notifications."""
    now = time.time()
    state["items"] = [
        n for n in state["items"]
        if now - n.get("created_at", 0) < EXPIRY_SECONDS
    ]
    return state


def get_pending() -> list[dict]:
    """Get all pending (unread) notifications.

    Returns:
        List of notification dicts with keys: type, message, created_at, key.
    """
    state = _load_notifications()
    state = _prune_expired(state)
    return [n for n in state["items"] if not n.get("dismissed")]


def dismiss(key: str):
    """Dismiss a notification by key."""
    state = _load_notifications()
    for n in state["items"]:
        if n.get("key") == key:
            n["dismissed"] = True
    _save_notifications(state)


def dismiss_all():
    """Dismiss all pending notifications."""
    state = _load_notifications()
    for n in state["items"]:
        n["dismissed"] = True
    _save_notifications(state)


def _add_notification(state: dict, ntype: str, key: str, message: str):
    """Add a notification if not already present (by key)."""
    existing_keys = {n["key"] for n in state["items"]}
    if key in existing_keys:
        return
    state["items"].append({
        "type": ntype,
        "key": key,
        "message": message,
        "created_at": time.time(),
        "dismissed": False,
    })


def _should_check(state: dict) -> bool:
    """Check if we should run discovery (24h throttle)."""
    if os.environ.get("DO_NOT_TRACK", "").strip() == "1":
        return False

    from evolution.config import EvoConfig
    cfg = EvoConfig()
    if not cfg.get("adapter.check_updates"):
        return False

    elapsed = time.time() - state.get("last_check", 0)
    return elapsed >= CHECK_INTERVAL_SECONDS


def check_adapter_updates(state: dict):
    """Check installed adapter plugins for updates."""
    try:
        import importlib.metadata
        from evolution.adapter_versions import check_pypi_version

        eps = importlib.metadata.entry_points()
        if hasattr(eps, "select"):
            adapter_eps = eps.select(group="evo.adapters")
        else:
            adapter_eps = eps.get("evo.adapters", [])

        seen_packages = set()
        for ep in adapter_eps:
            pkg = ep.dist.name if hasattr(ep, "dist") and ep.dist else None
            if not pkg or pkg in seen_packages:
                continue
            seen_packages.add(pkg)

            try:
                current = ep.dist.version
            except Exception:
                continue

            latest = check_pypi_version(pkg, use_cache=True)
            if latest and latest != current:
                _add_notification(
                    state,
                    TYPE_ADAPTER_UPDATE,
                    f"update:{pkg}:{latest}",
                    f"Update available: {pkg} {current} → {latest}. "
                    f"Run: pip install --upgrade {pkg}",
                )
    except Exception as e:
        log.debug("Adapter update check failed: %s", e)


def check_adapter_discovery(state: dict, repo_path: str | Path = None):
    """Check if prescan-detected tools have adapters available on PyPI.

    Compares prescan results against installed plugins. For any detected
    tool whose adapter isn't installed, checks if the adapter package
    exists on PyPI and notifies the user.
    """
    if not repo_path:
        return

    try:
        import importlib.metadata
        from evolution.prescan import SourcePrescan
        from evolution.adapter_versions import check_pypi_version

        # What tools are detected in the repo?
        prescan = SourcePrescan(repo_path)
        detected = prescan.scan()
        if not detected:
            return

        # What packages are already installed?
        installed = set()
        eps = importlib.metadata.entry_points()
        if hasattr(eps, "select"):
            adapter_eps = eps.select(group="evo.adapters")
        else:
            adapter_eps = eps.get("evo.adapters", [])
        for ep in adapter_eps:
            if hasattr(ep, "dist") and ep.dist:
                installed.add(ep.dist.name)

        # Check detected tools whose adapters aren't installed
        for svc in detected:
            adapter_pkg = svc.adapter
            if not adapter_pkg or adapter_pkg in installed:
                continue

            # Check if the adapter exists on PyPI (cached)
            latest = check_pypi_version(adapter_pkg, use_cache=True)
            if latest:
                _add_notification(
                    state,
                    TYPE_ADAPTER_AVAILABLE,
                    f"available:{adapter_pkg}",
                    f"Adapter available: {adapter_pkg} v{latest} "
                    f"(detected {svc.display_name} in repo). "
                    f"Install: pip install {adapter_pkg}",
                )
    except Exception as e:
        log.debug("Adapter discovery check failed: %s", e)


def check_and_notify(
    repo_path: str | Path = None,
    evo_dir: str | Path = None,
) -> list[dict]:
    """Run all notification checks and return pending notifications.

    This is the main entry point, called after `evo analyze` completes.
    Respects 24h check interval — safe to call on every run.

    Returns:
        List of pending notification dicts.
    """
    state = _load_notifications()
    state = _prune_expired(state)

    if _should_check(state):
        # Run checks (all non-blocking, all use cached PyPI lookups)
        check_adapter_updates(state)
        check_adapter_discovery(state, repo_path)
        state["last_check"] = time.time()
        _save_notifications(state)

    return [n for n in state["items"] if not n.get("dismissed")]


def format_notifications(notifications: list[dict]) -> str:
    """Format notifications for CLI display.

    Returns:
        Multi-line string ready for click.echo(), or empty string if none.
    """
    if not notifications:
        return ""

    lines = ["\nNotifications:"]
    for n in notifications:
        lines.append(f"  {n['message']}")
    lines.append("  Run `evo notifications dismiss` to clear.")
    return "\n".join(lines)
