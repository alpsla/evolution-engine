"""
OpenAPI Schema Source Adapter (Schema Reference)

Emits canonical SourceEvent payloads for OpenAPI specification versions.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/schema/FAMILY_CONTRACT.md (schema family)

Accepts:
  - An OpenAPI spec file (JSON/YAML), or
  - A list of pre-parsed schema version dicts (for testing / fixtures)
"""

import hashlib
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


class OpenAPIAdapter:
    source_family = "schema"
    source_type = "openapi"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, spec_file: str = None, versions: list = None,
                 source_id: str = None):
        """
        Args:
            spec_file: Path to an OpenAPI spec file (JSON or YAML)
            versions: Pre-parsed list of schema version dicts (for fixtures)
            source_id: Unique identifier for this adapter instance
        """
        self.spec_file = Path(spec_file) if spec_file else None
        self._fixture_versions = versions
        self.source_id = source_id or f"openapi:{spec_file or 'fixture'}"

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _parse_openapi(self, path: Path) -> dict:
        """Parse an OpenAPI spec file and extract structural metrics."""
        text = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            if yaml is None:
                raise RuntimeError("PyYAML required for YAML specs. pip install pyyaml")
            spec = yaml.safe_load(text)
        else:
            spec = json.loads(text)

        # Count endpoints (paths)
        paths = spec.get("paths", {})
        endpoint_count = 0
        for path_key, methods in paths.items():
            for method in methods:
                if method.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                    endpoint_count += 1

        # Count types (schemas)
        components = spec.get("components", {})
        schemas = components.get("schemas", {})
        type_count = len(schemas)

        # Count fields across all schemas
        field_count = 0
        for schema_name, schema_def in schemas.items():
            props = schema_def.get("properties", {})
            field_count += len(props)

        version = spec.get("info", {}).get("version", "unknown")

        return {
            "schema_name": spec.get("info", {}).get("title", path.stem),
            "schema_format": "openapi",
            "version": version,
            "structure": {
                "endpoint_count": endpoint_count,
                "type_count": type_count,
                "field_count": field_count,
            },
        }

    def iter_events(self):
        if self._fixture_versions is not None:
            versions = self._fixture_versions
        elif self.spec_file and self.spec_file.exists():
            parsed = self._parse_openapi(self.spec_file)
            versions = [{
                **parsed,
                "trigger": {"commit_sha": ""},
                "diff": {
                    "endpoints_added": 0, "endpoints_removed": 0,
                    "fields_added": 0, "fields_removed": 0,
                    "types_added": 0, "types_removed": 0,
                },
            }]
        else:
            return

        for ver in versions:
            content_hash = self._hash(json.dumps(ver, sort_keys=True))

            payload = {
                "schema_name": ver.get("schema_name", "unknown"),
                "schema_format": ver.get("schema_format", "openapi"),
                "version": ver.get("version", "unknown"),
                "trigger": ver.get("trigger", {"commit_sha": ""}),
                "structure": ver.get("structure", {}),
                "diff": ver.get("diff", {}),
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "schema_version",
                    "schema_hash": content_hash,
                    "commit_sha": payload["trigger"].get("commit_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
