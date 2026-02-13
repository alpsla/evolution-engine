"""
Run History — Snapshot, compare, and manage advisory history.

Saves advisory snapshots after each Phase 5 run so users can track
changes over time and verify whether fixes resolved issues.

Usage:
    from evolution.history import HistoryManager
    hm = HistoryManager(evo_dir)
    hm.snapshot(advisory, scope)
    runs = hm.list_runs()
    diff = hm.compare(runs[1]["timestamp"], runs[0]["timestamp"])
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


SNAPSHOT_VERSION = 1


def diff_advisories(before: dict, after: dict) -> dict:
    """
    Compare two advisories and classify each change.

    Returns:
        dict with resolved, persisting, new, regressions lists.
    """
    # Index "before" changes by family:metric
    before_changes = {}
    for c in before.get("changes", []):
        key = f"{c['family']}:{c['metric']}"
        before_changes[key] = c

    # Index "after" changes by family:metric
    after_changes = {}
    for c in after.get("changes", []):
        key = f"{c['family']}:{c['metric']}"
        after_changes[key] = c

    resolved = []
    persisting = []
    new_changes = []
    regressions = []

    # Check what was flagged before
    for key, before_change in before_changes.items():
        if key in after_changes:
            after_change = after_changes[key]
            # Still flagged — check if it improved
            before_dev = abs(before_change["deviation_stddev"])
            after_dev = abs(after_change["deviation_stddev"])
            improvement = before_dev - after_dev

            persisting.append({
                **after_change,
                "was_deviation": before_change["deviation_stddev"],
                "now_deviation": after_change["deviation_stddev"],
                "improvement": round(improvement, 2),
                "improved": improvement > 0,
            })
        else:
            # No longer flagged — resolved!
            resolved.append({
                **before_change,
                "was_deviation": before_change["deviation_stddev"],
                "resolution": "returned_to_normal",
            })

    # Check for new changes not in the original
    for key, after_change in after_changes.items():
        if key not in before_changes:
            new_changes.append({
                **after_change,
                "classification": "new_observation",
            })

    # Detect regressions: metrics that were normal before but
    # now deviate in the opposite direction or newly appear
    for nc in new_changes:
        nc["classification"] = "regression" if any(
            nc["family"] == bc["family"] for bc in before.get("changes", [])
        ) else "new_observation"
        if nc["classification"] == "regression":
            regressions.append(nc)

    return {
        "resolved": resolved,
        "persisting": persisting,
        "new": [n for n in new_changes if n["classification"] != "regression"],
        "regressions": regressions,
    }


def format_diff_summary(before: dict, after: dict, diff: dict) -> str:
    """Format a human-readable comparison summary."""
    lines = []
    lines.append(f"Run Comparison — {after.get('scope', 'unknown')}")
    before_id = before.get("advisory_id", before.get("snapshot_id", "?"))
    after_id = after.get("advisory_id", after.get("snapshot_id", "?"))
    lines.append(f"Comparing: {str(before_id)[:8]} \u2192 {str(after_id)[:8]}")
    lines.append("")

    total_before = len(before.get("changes", []))
    resolved_count = len(diff["resolved"])
    new_count = len(diff["new"])

    # Summary line
    if resolved_count == total_before and new_count == 0 and total_before > 0:
        lines.append("ALL ISSUES RESOLVED. No new issues detected.")
    elif resolved_count > 0:
        lines.append(f"{resolved_count} of {total_before} flagged changes resolved.")
    elif total_before > 0:
        lines.append(f"No changes resolved ({total_before} still active).")
    else:
        lines.append("No flagged changes in the baseline run.")

    lines.append("")

    # Resolved
    if diff["resolved"]:
        lines.append("RESOLVED:")
        for r in diff["resolved"]:
            lines.append(f"  {r['family']} / {r['metric']} — back to normal")
        lines.append("")

    # Persisting
    if diff["persisting"]:
        lines.append("STILL UNUSUAL:")
        for p in diff["persisting"]:
            trend = "improving" if p["improved"] else "not improving"
            lines.append(f"  {p['family']} / {p['metric']} — "
                         f"deviation {p['was_deviation']:.1f} -> "
                         f"{p['now_deviation']:.1f} ({trend})")
        lines.append("")

    # New
    if diff["new"]:
        lines.append("NEW OBSERVATIONS:")
        for n in diff["new"]:
            lines.append(f"  {n['family']} / {n['metric']} — "
                         f"deviation {n['deviation_stddev']:.1f} (new)")
        lines.append("")

    # Regressions
    if diff["regressions"]:
        lines.append("REGRESSIONS:")
        for r in diff["regressions"]:
            lines.append(f"  {r['family']} / {r['metric']} — "
                         f"deviation {r['deviation_stddev']:.1f} (was normal before)")
        lines.append("")

    # Score
    if total_before > 0:
        resolution_rate = resolved_count / total_before * 100
        lines.append(f"Resolution rate: {resolution_rate:.0f}% "
                     f"({resolved_count}/{total_before})")

    return "\n".join(lines)


class HistoryManager:
    """Manages advisory snapshots in .evo/phase5/history/."""

    def __init__(self, evo_dir: Path | str):
        self.evo_dir = Path(evo_dir)
        self.history_dir = self.evo_dir / "phase5" / "history"

    def snapshot(self, advisory: dict, scope: str) -> Path:
        """Save an advisory snapshot. Returns the snapshot file path."""
        self.history_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()
        ts = now.strftime("%Y%m%d-%H%M%S-%f")
        target = self.history_dir / f"{ts}.json"

        envelope = {
            "snapshot_version": SNAPSHOT_VERSION,
            "timestamp": ts,
            "scope": scope,
            "saved_at": now.isoformat() + "Z",
            "advisory": advisory,
        }

        target.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        return target

    def list_runs(self, limit: Optional[int] = None) -> list[dict]:
        """List snapshots, newest first. Returns metadata (no full advisory)."""
        if not self.history_dir.exists():
            return []

        files = sorted(self.history_dir.glob("*.json"),
                       key=lambda f: f.stem, reverse=True)
        if limit is not None:
            files = files[:limit]

        runs = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                advisory = data.get("advisory", {})
                changes = advisory.get("changes", [])
                families = sorted(set(c.get("family", "") for c in changes))
                runs.append({
                    "timestamp": data.get("timestamp", f.stem),
                    "scope": data.get("scope", ""),
                    "saved_at": data.get("saved_at", ""),
                    "changes_count": len(changes),
                    "families": families,
                    "file": str(f),
                })
            except (json.JSONDecodeError, KeyError):
                continue

        return runs

    def load_run(self, timestamp: str) -> dict:
        """Load a snapshot by exact timestamp or prefix match."""
        if not self.history_dir.exists():
            raise FileNotFoundError(f"No history directory found")

        # Exact match first
        exact = self.history_dir / f"{timestamp}.json"
        if exact.exists():
            return json.loads(exact.read_text(encoding="utf-8"))

        # Prefix match (like git short hashes)
        matches = [f for f in self.history_dir.glob("*.json")
                   if f.stem.startswith(timestamp)]

        if len(matches) == 1:
            return json.loads(matches[0].read_text(encoding="utf-8"))
        elif len(matches) > 1:
            stems = [m.stem for m in matches]
            raise ValueError(
                f"Ambiguous prefix '{timestamp}' matches {len(matches)} runs: "
                f"{', '.join(stems[:5])}"
            )
        else:
            raise FileNotFoundError(f"No snapshot matching '{timestamp}'")

    def compare(self, ts1: str, ts2: str) -> dict:
        """Compare two snapshots. ts1=before, ts2=after."""
        run1 = self.load_run(ts1)
        run2 = self.load_run(ts2)

        before_advisory = run1.get("advisory", {})
        after_advisory = run2.get("advisory", {})

        diff = diff_advisories(before_advisory, after_advisory)
        diff["summary_text"] = format_diff_summary(
            before_advisory, after_advisory, diff
        )
        diff["before_timestamp"] = run1.get("timestamp", ts1)
        diff["after_timestamp"] = run2.get("timestamp", ts2)

        return diff

    def clean(self, keep: Optional[int] = None,
              before: Optional[str] = None) -> int:
        """Delete old snapshots. Returns count of deleted files."""
        if not self.history_dir.exists():
            return 0

        files = sorted(self.history_dir.glob("*.json"),
                       key=lambda f: f.stem, reverse=True)
        to_delete = []

        if keep is not None:
            # Keep the N most recent, delete the rest
            to_delete = files[keep:]
        elif before is not None:
            # Delete files with timestamp before the given date string
            to_delete = [f for f in files if f.stem < before]
        else:
            return 0

        for f in to_delete:
            f.unlink()

        return len(to_delete)
