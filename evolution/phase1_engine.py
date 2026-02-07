"""
Phase 1 Engine — Observation Layer

Consumes SourceEvents from adapters, validates them,
and persists immutable, content‑addressable events.
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

    def ingest(self, adapter):
        for raw_event in adapter.iter_events():
            self._validate(raw_event)
            key = raw_event["attestation"]["commit_hash"]
            if key in self.index:
                continue

            source_event = {
                "source_type": raw_event["source_type"],
                "source_id": raw_event["source_id"],
                "ordering_mode": raw_event["ordering_mode"],
                "attestation": raw_event["attestation"],
                "predecessor_refs": raw_event.get("predecessor_refs"),
                "observed_at": datetime.utcnow().isoformat() + "Z",
                "payload": raw_event["payload"],
            }

            event_id = self._hash(source_event)
            source_event["event_id"] = event_id

            event_file = self.events_path / f"{event_id}.json"
            event_file.write_text(json.dumps(source_event, indent=2))

            self.index[key] = event_id

        self.index_path.write_text(json.dumps(self.index, indent=2))
