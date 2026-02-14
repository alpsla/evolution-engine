"""
Accepted Deviations — Manage acknowledged deviations in .evo/accepted.json.

Users accept deviations they've reviewed and consider intentional.
Accepted deviations are excluded from future Phase 5 advisories.

Scope types:
    permanent  — always suppress this family:metric (default, backward compat)
    commits    — suppress only when trigger events are within a commit range
    dates      — suppress only when trigger events are within a date range
    this-run   — one-time dismiss, expires on next analysis

Usage:
    from evolution.accepted import AcceptedDeviations
    ad = AcceptedDeviations(evo_dir)
    ad.add("git:dispersion", "git", "dispersion", reason="Known refactoring spike")
    ad.add("ci:run_duration", "ci", "run_duration",
           scope={"type": "commits", "from": "abc123", "to": "def456"},
           reason="Planned CI migration")
    ad.is_accepted("git", "dispersion")  # True (permanent)
    ad.is_accepted_in_context("ci", "run_duration", commit_sha="ccc000")  # depends on range
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


VERSION = 2

SCOPE_PERMANENT = "permanent"
SCOPE_COMMITS = "commits"
SCOPE_DATES = "dates"
SCOPE_THIS_RUN = "this-run"
VALID_SCOPE_TYPES = {SCOPE_PERMANENT, SCOPE_COMMITS, SCOPE_DATES, SCOPE_THIS_RUN}


class AcceptedDeviations:
    """Manage accepted/acknowledged deviations in .evo/accepted.json."""

    def __init__(self, evo_dir: Path | str):
        self.path = Path(evo_dir) / "accepted.json"

    def load(self) -> list[dict]:
        """Load accepted deviations list."""
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("accepted", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def save(self, entries: list[dict]) -> None:
        """Write accepted deviations to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": VERSION, "accepted": entries}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(
        self,
        key: str,
        family: str,
        metric: str,
        reason: str = "",
        advisory_id: str = "",
        scope: Optional[dict] = None,
    ) -> bool:
        """Accept a deviation with optional scope.

        Args:
            key: The family:metric key (e.g. "git:dispersion").
            family: Signal family.
            metric: Signal metric name.
            reason: Human reason for acceptance.
            advisory_id: The advisory this acceptance came from.
            scope: Scope dict, e.g.:
                {"type": "permanent"}  (default)
                {"type": "commits", "from": "abc123", "to": "def456"}
                {"type": "dates", "from": "2026-02-10", "to": "2026-02-14"}
                {"type": "this-run", "advisory_id": "..."}

        Returns:
            True if added, False if an identical permanent acceptance exists.
        """
        if scope is None:
            scope = {"type": SCOPE_PERMANENT}

        scope_type = scope.get("type", SCOPE_PERMANENT)
        if scope_type not in VALID_SCOPE_TYPES:
            raise ValueError(f"Invalid scope type: {scope_type}. Must be one of {VALID_SCOPE_TYPES}")

        entries = self.load()

        # For permanent scope, check for duplicate keys (backward compat)
        if scope_type == SCOPE_PERMANENT:
            existing_permanent = {
                e["key"] for e in entries
                if e.get("scope", {}).get("type", SCOPE_PERMANENT) == SCOPE_PERMANENT
            }
            if key in existing_permanent:
                return False

        entry = {
            "key": key,
            "family": family,
            "metric": metric,
            "reason": reason,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "from_advisory": advisory_id,
            "scope": scope,
        }

        entries.append(entry)
        self.save(entries)
        return True

    def remove(self, key: str) -> bool:
        """Remove an accepted deviation by key. Removes ALL scopes for that key.

        Returns False if not found.
        """
        entries = self.load()
        new_entries = [e for e in entries if e["key"] != key]
        if len(new_entries) == len(entries):
            return False
        self.save(new_entries)
        return True

    def remove_scoped(self, key: str, scope_type: str) -> bool:
        """Remove accepted deviations for a key with a specific scope type.

        Returns False if none found.
        """
        entries = self.load()
        new_entries = [
            e for e in entries
            if not (e["key"] == key and e.get("scope", {}).get("type", SCOPE_PERMANENT) == scope_type)
        ]
        if len(new_entries) == len(entries):
            return False
        self.save(new_entries)
        return True

    def clear(self) -> int:
        """Remove all accepted deviations. Returns count removed."""
        entries = self.load()
        count = len(entries)
        if count > 0:
            self.save([])
        return count

    def cleanup_expired(self, current_advisory_id: str = "") -> int:
        """Remove expired this-run entries that don't match the current advisory.

        Called at the start of each analysis. Returns count removed.
        """
        entries = self.load()
        kept = []
        removed = 0
        for e in entries:
            scope = e.get("scope", {})
            if scope.get("type") == SCOPE_THIS_RUN:
                # Keep only if it matches the current advisory
                if scope.get("advisory_id") == current_advisory_id and current_advisory_id:
                    kept.append(e)
                else:
                    removed += 1
            else:
                kept.append(e)
        if removed > 0:
            self.save(kept)
        return removed

    def is_accepted(self, family: str, metric: str) -> bool:
        """Check if a family:metric pair has a permanent acceptance."""
        key = f"{family}:{metric}"
        for e in self.load():
            if e["key"] != key:
                continue
            scope_type = e.get("scope", {}).get("type", SCOPE_PERMANENT)
            if scope_type == SCOPE_PERMANENT:
                return True
        return False

    def is_accepted_in_context(
        self,
        family: str,
        metric: str,
        commit_sha: str = "",
        event_date: str = "",
        advisory_id: str = "",
        commit_list: Optional[list[str]] = None,
    ) -> bool:
        """Check if a family:metric is accepted given the current context.

        This is the full scope-aware check used by Phase 5.

        Args:
            family: Signal family.
            metric: Signal metric.
            commit_sha: The commit SHA triggering the signal.
            event_date: ISO date string of the event.
            advisory_id: Current advisory ID (for this-run scope).
            commit_list: Ordered list of all commit SHAs in the analysis window.
                Used for commit range checking.

        Returns:
            True if any matching acceptance applies in this context.
        """
        key = f"{family}:{metric}"
        entries = [e for e in self.load() if e["key"] == key]

        for e in entries:
            scope = e.get("scope", {})
            scope_type = scope.get("type", SCOPE_PERMANENT)

            if scope_type == SCOPE_PERMANENT:
                return True

            if scope_type == SCOPE_THIS_RUN:
                if scope.get("advisory_id") == advisory_id and advisory_id:
                    return True

            if scope_type == SCOPE_COMMITS and commit_sha:
                if _commit_in_range(
                    commit_sha,
                    scope.get("from", ""),
                    scope.get("to", ""),
                    commit_list or [],
                ):
                    return True

            if scope_type == SCOPE_DATES and event_date:
                date_from = scope.get("from", "")
                date_to = scope.get("to", "")
                if _date_in_range(event_date, date_from, date_to):
                    return True

        return False

    def accepted_keys(self) -> set[str]:
        """Return set of permanently accepted family:metric keys (backward compat)."""
        keys = set()
        for e in self.load():
            scope_type = e.get("scope", {}).get("type", SCOPE_PERMANENT)
            if scope_type == SCOPE_PERMANENT:
                keys.add(e["key"])
        return keys

    def all_entries_for_key(self, key: str) -> list[dict]:
        """Return all acceptance entries for a given key (all scopes)."""
        return [e for e in self.load() if e["key"] == key]


def _commit_in_range(
    sha: str,
    range_from: str,
    range_to: str,
    commit_list: list[str],
) -> bool:
    """Check if a commit SHA falls within a range.

    Uses commit_list (ordered oldest→newest) for positional comparison.
    Falls back to prefix matching if the commit isn't in the list.
    """
    if not range_from:
        return False

    # Single commit scope (no "to")
    if not range_to or range_to == range_from:
        return sha.startswith(range_from) or range_from.startswith(sha)

    # Prefix-match the from/to in the commit list
    from_idx = None
    to_idx = None
    sha_idx = None

    for i, c in enumerate(commit_list):
        if c.startswith(range_from) or range_from.startswith(c):
            from_idx = i
        if c.startswith(range_to) or range_to.startswith(c):
            to_idx = i
        if c.startswith(sha) or sha.startswith(c):
            sha_idx = i

    if from_idx is not None and to_idx is not None and sha_idx is not None:
        low = min(from_idx, to_idx)
        high = max(from_idx, to_idx)
        return low <= sha_idx <= high

    # Fallback: direct prefix match against from/to
    return sha.startswith(range_from) or sha.startswith(range_to)


def _date_in_range(event_date: str, date_from: str, date_to: str) -> bool:
    """Check if an event date falls within a date range.

    Dates are compared as strings (ISO format: YYYY-MM-DD or full ISO).
    """
    if not date_from:
        return False

    # Normalize to date-only for comparison
    event_day = event_date[:10]
    from_day = date_from[:10]
    to_day = (date_to[:10] if date_to else from_day)

    return from_day <= event_day <= to_day
