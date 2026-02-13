"""
Accepted Deviations — Manage acknowledged deviations in .evo/accepted.json.

Users accept deviations they've reviewed and consider intentional.
Accepted deviations are excluded from future Phase 5 advisories.

Usage:
    from evolution.accepted import AcceptedDeviations
    ad = AcceptedDeviations(evo_dir)
    ad.add("git:dispersion", "git", "dispersion", reason="Known refactoring spike")
    ad.is_accepted("git", "dispersion")  # True
    ad.accepted_keys()                    # {"git:dispersion"}
"""

import json
from datetime import datetime, timezone
from pathlib import Path


VERSION = 1


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

    def add(self, key: str, family: str, metric: str,
            reason: str = "", advisory_id: str = "") -> bool:
        """Accept a deviation. Returns False if already accepted."""
        entries = self.load()
        existing_keys = {e["key"] for e in entries}
        if key in existing_keys:
            return False
        entries.append({
            "key": key,
            "family": family,
            "metric": metric,
            "reason": reason,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "from_advisory": advisory_id,
        })
        self.save(entries)
        return True

    def remove(self, key: str) -> bool:
        """Remove an accepted deviation. Returns False if not found."""
        entries = self.load()
        new_entries = [e for e in entries if e["key"] != key]
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

    def is_accepted(self, family: str, metric: str) -> bool:
        """Check if a family:metric pair is accepted."""
        key = f"{family}:{metric}"
        return key in self.accepted_keys()

    def accepted_keys(self) -> set[str]:
        """Return set of accepted family:metric keys for fast lookup."""
        return {e["key"] for e in self.load()}
