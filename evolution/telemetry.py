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

Typed helpers (preferred over raw track_event):
    from evolution.telemetry import track_analyze, track_investigate, track_error
    track_analyze(duration_seconds=1.2, license_tier="free", ...)
"""

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Optional


_TELEMETRY_URL = "https://codequal.dev/api/telemetry"
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
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"evo-cli/{_get_version()}",
                },
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


# ─────────────────── Typed Helpers ───────────────────
# Each helper standardizes an event schema and delegates to track_event().
# Prefer these over raw track_event() for consistent analytics.


def track_analyze(
    *,
    license_tier: str = "free",
    duration_seconds: float = 0.0,
    total_events: int = 0,
    active_families_count: int = 0,
    patterns_matched: int = 0,
    significant_changes_count: int = 0,
    gated_families_count: int = 0,
    has_diagnostics: bool = False,
    run_number: int = 0,
):
    """Track a completed `evo analyze` run."""
    track_event("analyze_complete", {
        "license_tier": license_tier,
        "duration_seconds": round(duration_seconds, 1),
        "total_events": total_events,
        "active_families_count": active_families_count,
        "patterns_matched": patterns_matched,
        "significant_changes_count": significant_changes_count,
        "gated_families_count": gated_families_count,
        "has_diagnostics": has_diagnostics,
        "run_number": run_number,
    })


def track_investigate(
    *,
    agent: str = "",
    duration_seconds: float = 0.0,
    success: bool = False,
    finding_count: int = 0,
):
    """Track an `evo investigate` execution."""
    track_event("investigate", {
        "agent": agent,
        "duration_seconds": round(duration_seconds, 1),
        "success": success,
        "finding_count": finding_count,
    })


def track_fix(
    *,
    iterations: int = 0,
    resolved: int = 0,
    status: str = "",
    duration_seconds: float = 0.0,
    termination_reason: str = "",
    dry_run: bool = False,
):
    """Track an `evo fix` execution."""
    track_event("fix", {
        "iterations": iterations,
        "resolved": resolved,
        "status": status,
        "duration_seconds": round(duration_seconds, 1),
        "termination_reason": termination_reason,
        "dry_run": dry_run,
    })


def track_verify(
    *,
    duration_seconds: float = 0.0,
    changes_resolved: int = 0,
    changes_persisting: int = 0,
    changes_new: int = 0,
):
    """Track an `evo verify` execution."""
    track_event("verify", {
        "duration_seconds": round(duration_seconds, 1),
        "changes_resolved": changes_resolved,
        "changes_persisting": changes_persisting,
        "changes_new": changes_new,
    })


def track_accept(
    *,
    scope: str = "permanent",
    count: int = 0,
    family: str = "",
):
    """Track an `evo accept` execution."""
    track_event("accept", {
        "scope": scope,
        "count": count,
        "family": family,
    })


def track_sources(
    *,
    families_detected: int = 0,
    tier2_available: int = 0,
    unconnected_services: list[str] | None = None,
):
    """Track an `evo sources` execution."""
    track_event("sources", {
        "families_detected": families_detected,
        "tier2_available": tier2_available,
        "unconnected_services": unconnected_services or [],
    })


def track_license_check(
    *,
    tier: str = "free",
    source: str = "",
    valid: bool = False,
    days_to_expiry: int = -1,
):
    """Track a license validation check."""
    track_event("license_check", {
        "tier": tier,
        "source": source,
        "valid": valid,
        "days_to_expiry": days_to_expiry,
    })


def track_adapter_execution(
    *,
    family: str = "",
    tier: int = 1,
    event_count: int = 0,
    duration_ms: int = 0,
    success: bool = True,
):
    """Track a single adapter's execution during analysis."""
    track_event("adapter_execution", {
        "family": family,
        "tier": tier,
        "event_count": event_count,
        "duration_ms": duration_ms,
        "success": success,
    })


def track_pattern_sync(
    *,
    action: str = "",
    count: int = 0,
    rejected: int = 0,
    source: str = "",
):
    """Track a pattern sync operation (pull or push)."""
    track_event("pattern_sync", {
        "action": action,
        "count": count,
        "rejected": rejected,
        "source": source,
    })


def track_error(
    *,
    error_type: str = "",
    command: str = "",
):
    """Track an unhandled error. Never sends stack traces or file paths."""
    # Strip module path from error type — class name only
    if "." in error_type:
        error_type = error_type.rsplit(".", 1)[-1]
    track_event("error", {
        "error_type": error_type,
        "command": command,
    })
