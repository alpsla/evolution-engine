"""
Opt-in anonymous product telemetry for Evolution Engine.

- Disabled by default (opt-in only)
- Respects DO_NOT_TRACK=1 environment variable
- Never collects: file paths, code content, repo names, usernames
- Fire-and-forget: runs in background thread, never blocks CLI
- Config stored in ~/.evo/config.toml as telemetry.enabled

Usage:
    from evolution.telemetry import track_event, prompt_consent
    prompt_consent()  # Ask user once on first evo analyze
    track_event("cli_command", {"command": "analyze", "adapter_count": 3})
"""

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Optional


_TELEMETRY_URL = "https://evo.dev/api/telemetry"
_TIMEOUT = 2  # seconds


def _is_enabled() -> bool:
    """Check if telemetry is enabled. Returns False by default."""
    # Standard DO_NOT_TRACK env var overrides everything
    if os.environ.get("DO_NOT_TRACK", "").strip() == "1":
        return False

    # Check config
    from evolution.config import EvoConfig
    try:
        cfg = EvoConfig()
        return bool(cfg.get("telemetry.enabled", False))
    except Exception:
        return False


def _get_anon_id() -> str:
    """Get or create anonymous ID (UUID4, no PII)."""
    from evolution.config import _config_dir
    anon_path = _config_dir() / "anon_id"
    if anon_path.exists():
        return anon_path.read_text().strip()
    anon_id = str(uuid.uuid4())
    try:
        anon_path.parent.mkdir(parents=True, exist_ok=True)
        anon_path.write_text(anon_id)
    except OSError:
        pass
    return anon_id


def track_event(event_name: str, properties: Optional[dict[str, Any]] = None):
    """Fire-and-forget telemetry event. Non-blocking, never raises."""
    if not _is_enabled():
        return

    def _send():
        try:
            import urllib.request
            payload = {
                "event": event_name,
                "properties": properties or {},
                "anon_id": _get_anon_id(),
                "version": _get_version(),
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                _TELEMETRY_URL,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=_TIMEOUT)
        except Exception:
            pass  # Fire-and-forget

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


def prompt_consent():
    """Prompt user for telemetry consent on first run.

    Only prompts if:
    - telemetry.prompted is False (never asked before)
    - Running in an interactive terminal (not CI)
    - DO_NOT_TRACK is not set
    """
    # Respect DO_NOT_TRACK
    if os.environ.get("DO_NOT_TRACK", "").strip() == "1":
        return

    # Don't prompt in non-interactive environments (CI, pipes)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return

    from evolution.config import EvoConfig
    try:
        cfg = EvoConfig()
    except Exception:
        return

    # Only prompt once
    if cfg.get("telemetry.prompted", False):
        return

    try:
        print()
        print("Help improve Evolution Engine?")
        print("We collect anonymous usage stats only (command names, adapter counts).")
        print("Never code, file paths, or personal data. You can change this anytime")
        print("with: evo config set telemetry.enabled false")
        print()
        answer = input("Allow anonymous usage stats? [y/N]: ").strip().lower()
        enabled = answer in ("y", "yes")
        cfg.set("telemetry.enabled", enabled)
        cfg.set("telemetry.prompted", True)
        if enabled:
            print("Thanks! Telemetry enabled.")
        else:
            print("No problem. Telemetry disabled.")
        print()
    except (EOFError, KeyboardInterrupt):
        # Non-interactive or user cancelled — mark as prompted, leave disabled
        cfg.set("telemetry.prompted", True)


def _get_version() -> str:
    """Get the current package version."""
    try:
        from evolution import __version__
        return __version__
    except (ImportError, AttributeError):
        return "unknown"
