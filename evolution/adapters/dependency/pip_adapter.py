"""
Pip Dependency Source Adapter (Dependency Reference)

Emits canonical SourceEvent payloads for Python dependency snapshots.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/dependency/FAMILY_CONTRACT.md (dependency family)

Accepts:
  - A requirements.txt or Pipfile.lock path, or
  - A list of pre-parsed snapshot dicts (for testing / fixtures)
"""

import hashlib
import json
import re
from pathlib import Path


class PipDependencyAdapter:
    source_family = "dependency"
    source_type = "pip"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, lock_file: str = None, snapshots: list = None,
                 source_id: str = None):
        """
        Args:
            lock_file: Path to requirements.txt or Pipfile.lock
            snapshots: Pre-parsed list of snapshot dicts (for fixtures/testing)
            source_id: Unique identifier for this adapter instance
        """
        self.lock_file = Path(lock_file) if lock_file else None
        self._fixture_snapshots = snapshots
        self.source_id = source_id or f"pip:{lock_file or 'fixture'}"

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _parse_requirements(self, path: Path) -> list:
        """Parse a requirements.txt into a list of dependency dicts."""
        deps = []
        text = path.read_text(encoding="utf-8")
        for line in text.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Parse name==version, name>=version, name
            match = re.match(r'^([A-Za-z0-9_.-]+)\s*([><=!~]+\s*[\d.*]+)?', line)
            if match:
                name = match.group(1).lower()
                version = match.group(2).strip() if match.group(2) else "unspecified"
                version = re.sub(r'^[><=!~]+\s*', '', version)
                deps.append({
                    "name": name,
                    "version": version,
                    "direct": True,
                    "depth": 1,
                })
        return deps

    def iter_events(self):
        if self._fixture_snapshots is not None:
            snapshots = self._fixture_snapshots
        elif self.lock_file and self.lock_file.exists():
            deps = self._parse_requirements(self.lock_file)
            snapshots = [{
                "ecosystem": "pip",
                "manifest_file": str(self.lock_file),
                "trigger": {"commit_sha": ""},
                "snapshot": {
                    "direct_count": len(deps),
                    "transitive_count": 0,
                    "total_count": len(deps),
                    "max_depth": 1,
                },
                "dependencies": deps,
            }]
        else:
            return

        for snap in snapshots:
            content_hash = self._hash(json.dumps(snap, sort_keys=True))

            payload = {
                "ecosystem": snap.get("ecosystem", "pip"),
                "manifest_file": snap.get("manifest_file", "requirements.txt"),
                "trigger": snap.get("trigger", {"commit_sha": ""}),
                "snapshot": snap.get("snapshot", {}),
                "dependencies": snap.get("dependencies", []),
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "dependency_snapshot",
                    "snapshot_hash": content_hash,
                    "commit_sha": payload["trigger"].get("commit_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
