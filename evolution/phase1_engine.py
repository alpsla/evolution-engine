"""
Phase 1 Engine — Observation Layer

Consumes SourceEvents from adapters, validates them,
and persists immutable, content‑addressable events.

Supports all source families (version_control, ci, testing,
dependency, schema, deployment, config, security).
"""

from pathlib import Path
import json
import hashlib
from datetime import datetime

REQUIRED_FIELDS = {"source_type", "source_id", "ordering_mode", "attestation", "payload"}


class Phase1Engine:
    def __init__(self, evo_dir: Path):
        self.evo_dir = evo_dir
        self.events_path = evo_dir / "events"
        self.events_path.mkdir(parents=True, exist_ok=True)
        self.index_path = evo_dir / "index" / "source_to_event.json"
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        if self.index_path.exists():
            self.index = json.loads(self.index_path.read_text())
        else:
            self.index = {}

    def _hash(self, data: dict) -> str:
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate(self, event: dict):
        missing = REQUIRED_FIELDS - event.keys()
        if missing:
            raise ValueError(f"Adapter emitted invalid SourceEvent, missing fields: {missing}")

    def _dedup_key(self, raw_event: dict) -> str:
        """
        Extract a deduplication key from the attestation block.

        Each family uses a different attestation shape, so we build
        a universal key from source_family + attestation fields.
        """
        att = raw_event["attestation"]
        family = raw_event.get("source_family", raw_event.get("source_type", "unknown"))

        # Git: content-addressed by commit hash
        if "commit_hash" in att:
            return f"{family}:{att['commit_hash']}"
        # CI: run_id
        if "run_id" in att:
            return f"{family}:{att['run_id']}"
        # Testing: report_hash
        if "report_hash" in att:
            return f"{family}:{att['report_hash']}"
        # Dependency: snapshot_hash
        if "snapshot_hash" in att:
            return f"{family}:{att['snapshot_hash']}"
        # Schema: schema_hash
        if "schema_hash" in att:
            return f"{family}:{att['schema_hash']}"
        # Deployment: deployment_id
        if "deployment_id" in att:
            return f"{family}:{att['deployment_id']}"
        # Config: config_hash
        if "config_hash" in att:
            return f"{family}:{att['config_hash']}"
        # Security: scan_hash
        if "scan_hash" in att:
            return f"{family}:{att['scan_hash']}"

        # Fallback: hash the entire attestation block
        return f"{family}:{self._hash(att)}"

    def ingest(self, adapter, override_observed_at: str = None):
        """
        Ingest events from an adapter.
        
        Args:
            adapter: Adapter instance with iter_events()
            override_observed_at: Optional timestamp to override observed_at
                                 (for historical replay)
        """
        count = 0
        for raw_event in adapter.iter_events():
            self._validate(raw_event)
            key = self._dedup_key(raw_event)

            if key in self.index:
                continue

            # Use override, then payload timestamp, then wall clock as fallback
            observed_at = override_observed_at
            if not observed_at:
                payload = raw_event.get("payload", {})
                observed_at = (
                    payload.get("committed_at")
                    or payload.get("authored_at")
                    or payload.get("timestamp")
                    or (datetime.utcnow().isoformat() + "Z")
                )

            source_event = {
                "source_family": raw_event.get("source_family", ""),
                "source_type": raw_event["source_type"],
                "source_id": raw_event["source_id"],
                "ordering_mode": raw_event["ordering_mode"],
                "attestation": raw_event["attestation"],
                "predecessor_refs": raw_event.get("predecessor_refs"),
                "observed_at": observed_at,
                "payload": raw_event["payload"],
            }

            event_id = self._hash(source_event)
            source_event["event_id"] = event_id

            event_file = self.events_path / f"{event_id}.json"
            event_file.write_text(json.dumps(source_event, indent=2))

            self.index[key] = event_id
            count += 1

        self.index_path.write_text(json.dumps(self.index, indent=2))
        return count
