"""
Terraform / Generic Config Source Adapter (Config Reference)

Emits canonical SourceEvent payloads for infrastructure configuration snapshots.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/config/FAMILY_CONTRACT.md (config family)

Accepts:
  - A directory of .tf files, or
  - A list of pre-parsed config snapshot dicts (for testing / fixtures)
"""

import hashlib
import json
import re
from pathlib import Path


class TerraformAdapter:
    source_family = "config"
    source_type = "terraform"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, config_dir: str = None, snapshots: list = None,
                 source_id: str = None):
        """
        Args:
            config_dir: Path to directory containing .tf files
            snapshots: Pre-parsed list of config snapshot dicts (for fixtures)
            source_id: Unique identifier for this adapter instance
        """
        self.config_dir = Path(config_dir) if config_dir else None
        self._fixture_snapshots = snapshots
        self.source_id = source_id or f"terraform:{config_dir or 'fixture'}"

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _parse_tf_dir(self, config_dir: Path) -> dict:
        """Parse .tf files and extract structural metrics."""
        tf_files = list(config_dir.glob("*.tf"))
        resource_count = 0
        resource_types = set()

        # Simple regex-based resource counter
        resource_re = re.compile(r'^resource\s+"(\w+)"\s+"(\w+)"', re.MULTILINE)

        for tf_file in tf_files:
            text = tf_file.read_text(encoding="utf-8")
            matches = resource_re.findall(text)
            resource_count += len(matches)
            for rtype, _ in matches:
                resource_types.add(rtype)

        return {
            "config_scope": config_dir.name,
            "config_format": "terraform",
            "structure": {
                "resource_count": resource_count,
                "resource_types": len(resource_types),
                "file_count": len(tf_files),
            },
        }

    def iter_events(self):
        if self._fixture_snapshots is not None:
            snapshots = self._fixture_snapshots
        elif self.config_dir and self.config_dir.exists():
            parsed = self._parse_tf_dir(self.config_dir)
            snapshots = [{
                **parsed,
                "trigger": {"commit_sha": "", "apply_id": ""},
                "diff": {
                    "resources_added": 0,
                    "resources_removed": 0,
                    "resources_modified": 0,
                },
            }]
        else:
            return

        for snap in snapshots:
            content_hash = self._hash(json.dumps(snap, sort_keys=True))

            payload = {
                "config_scope": snap.get("config_scope", "unknown"),
                "config_format": snap.get("config_format", "terraform"),
                "trigger": snap.get("trigger", {}),
                "structure": snap.get("structure", {}),
                "diff": snap.get("diff", {}),
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "config_snapshot",
                    "config_hash": content_hash,
                    "commit_sha": payload["trigger"].get("commit_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
