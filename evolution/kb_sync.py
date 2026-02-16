"""
KB Sync — Opt-in community pattern sharing.

Manages push/pull of anonymized pattern digests with a remote registry.
Privacy levels control what data leaves the machine:

    Level 0: Nothing shared (default)
    Level 1: Advisory metadata only (family counts, risk levels — no patterns)
    Level 2: Anonymized pattern digests (sources, metrics, correlations — no code)

All pulled patterns go through kb_security.validate_pattern() before storage.

Usage:
    from evolution.kb_sync import KBSync
    sync = KBSync(evo_dir=".evo")
    sync.pull()                    # fetch community patterns
    sync.push()                    # share local patterns (if privacy allows)
    sync.status()                  # check sync state
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("evo.kb_sync")


# ─── Sync Result ───

@dataclass
class SyncResult:
    """Result of a sync operation."""
    action: str              # "pull", "push", "status"
    success: bool
    pulled: int = 0          # patterns received
    pushed: int = 0          # patterns sent
    rejected: int = 0        # patterns that failed validation
    skipped: int = 0         # patterns already present
    filtered: int = 0        # patterns filtered by quality gate
    error: Optional[str] = None
    registry_url: str = ""
    privacy_level: int = 0

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "success": self.success,
            "pulled": self.pulled,
            "pushed": self.pushed,
            "rejected": self.rejected,
            "skipped": self.skipped,
            "filtered": self.filtered,
            "error": self.error,
            "registry_url": self.registry_url,
            "privacy_level": self.privacy_level,
        }


class KBSync:
    """Sync patterns with a remote registry.

    Args:
        evo_dir: Path to .evo directory.
        config: Optional EvoConfig instance (uses defaults if None).
        registry_url: Override registry URL (otherwise from config).
    """

    def __init__(
        self,
        evo_dir: str | Path = ".evo",
        config=None,
        registry_url: Optional[str] = None,
    ):
        self._evo_dir = Path(evo_dir)
        self._db_path = self._evo_dir / "phase4" / "knowledge.db"
        self._sync_state_path = self._evo_dir / "sync_state.json"

        # Load config
        if config is None:
            from evolution.config import EvoConfig
            config = EvoConfig()
        self._config = config

        self._privacy_level = config.get("sync.privacy_level", 0)
        self._registry_url = registry_url or config.get(
            "sync.registry_url", "https://codequal.dev/api"
        )

    @property
    def privacy_level(self) -> int:
        return self._privacy_level

    @property
    def registry_url(self) -> str:
        return self._registry_url

    def pull(self) -> SyncResult:
        """Fetch community patterns from the registry.

        Always allowed regardless of privacy level — pulling patterns
        from the community doesn't share any local data.
        """
        if not self._db_path.exists():
            return SyncResult(
                action="pull", success=False,
                error="No knowledge base found. Run `evo analyze` first.",
                registry_url=self._registry_url,
                privacy_level=self._privacy_level,
            )

        try:
            patterns = self._fetch_patterns()
        except Exception as e:
            log.warning("Failed to fetch patterns: %s", e)
            return SyncResult(
                action="pull", success=False,
                error=str(e),
                registry_url=self._registry_url,
                privacy_level=self._privacy_level,
            )

        if not patterns:
            return SyncResult(
                action="pull", success=True,
                registry_url=self._registry_url,
                privacy_level=self._privacy_level,
            )

        # Import through the secure pipeline
        from evolution.kb_export import import_patterns
        result = import_patterns(self._db_path, patterns)

        # Update sync state
        self._update_sync_state("pull", pulled=result["imported"])

        return SyncResult(
            action="pull", success=True,
            pulled=result["imported"],
            skipped=result["skipped"],
            rejected=result["rejected"],
            registry_url=self._registry_url,
            privacy_level=self._privacy_level,
        )

    def push(self) -> SyncResult:
        """Share local patterns with the registry.

        Requires privacy_level >= 2. At level 1, only metadata is sent.
        At level 0, nothing is sent.
        """
        if self._privacy_level < 1:
            return SyncResult(
                action="push", success=False,
                error="Sharing disabled (privacy_level=0). "
                      "Set sync.privacy_level=1 or 2 with `evo config set sync.privacy_level 2`",
                registry_url=self._registry_url,
                privacy_level=self._privacy_level,
            )

        if not self._db_path.exists():
            return SyncResult(
                action="push", success=False,
                error="No knowledge base found. Run `evo analyze` first.",
                registry_url=self._registry_url,
                privacy_level=self._privacy_level,
            )

        try:
            if self._privacy_level == 1:
                payload = self._build_metadata_payload()
            else:
                payload = self._build_pattern_payload()
        except Exception as e:
            log.warning("Failed to build push payload: %s", e)
            return SyncResult(
                action="push", success=False,
                error=str(e),
                registry_url=self._registry_url,
                privacy_level=self._privacy_level,
            )

        try:
            pushed_count = self._upload_patterns(payload)
        except Exception as e:
            log.warning("Failed to push patterns: %s", e)
            return SyncResult(
                action="push", success=False,
                error=str(e),
                registry_url=self._registry_url,
                privacy_level=self._privacy_level,
            )

        self._update_sync_state("push", pushed=pushed_count)

        return SyncResult(
            action="push", success=True,
            pushed=pushed_count,
            filtered=getattr(self, "_last_filtered", 0),
            registry_url=self._registry_url,
            privacy_level=self._privacy_level,
        )

    def status(self) -> SyncResult:
        """Check sync state without transferring data."""
        state = self._load_sync_state()
        return SyncResult(
            action="status", success=True,
            pulled=state.get("total_pulled", 0),
            pushed=state.get("total_pushed", 0),
            registry_url=self._registry_url,
            privacy_level=self._privacy_level,
        )

    # ─── Private Helpers ───

    def _fetch_patterns(self) -> list[dict]:
        """Fetch patterns from remote registry."""
        import requests

        url = f"{self._registry_url}/patterns"
        last_pull = self._load_sync_state().get("last_pull_at")
        params = {}
        if last_pull:
            params["since"] = last_pull

        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("patterns", [])

    def _upload_patterns(self, payload: dict) -> int:
        """Upload payload to remote registry."""
        import requests

        url = f"{self._registry_url}/patterns"
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("accepted", 0)

    def _build_metadata_payload(self) -> dict:
        """Build level-1 metadata payload (no patterns, just stats)."""
        advisory_path = self._evo_dir / "phase5" / "advisory.json"
        if not advisory_path.exists():
            return {"level": 1, "metadata": {}}

        advisory = json.loads(advisory_path.read_text())
        summary = advisory.get("summary", {})

        return {
            "level": 1,
            "metadata": {
                "families": summary.get("families_affected", []),
                "significant_changes": summary.get("significant_changes", 0),
                "patterns_matched": summary.get("known_patterns_matched", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _build_pattern_payload(self) -> dict:
        """Build level-2 pattern payload (anonymized digests).

        Each pattern includes an HMAC attestation from this instance,
        proving it was computed by a real EE installation.

        Quality gate: only patterns with |correlation| >= 0.3 and
        occurrence_count >= 3 are shared. Weak local patterns must
        not pollute the community registry.
        """
        from evolution.kb_export import export_patterns
        from evolution.kb_security import get_instance_id

        export_stats = {}
        digests = export_patterns(
            self._db_path,
            min_occurrences=3,
            min_correlation=0.3,
            evo_dir=self._evo_dir,
            stats=export_stats,
        )
        instance_id = get_instance_id(self._evo_dir)

        filtered = export_stats.get("filtered", 0)
        if filtered > 0:
            log.info("Quality gate filtered %d weak pattern(s) from push", filtered)
        self._last_filtered = filtered

        return {
            "level": 2,
            "instance_id": instance_id,
            "patterns": digests,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _load_sync_state(self) -> dict:
        """Load sync state from disk."""
        if not self._sync_state_path.exists():
            return {}
        try:
            return json.loads(self._sync_state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _update_sync_state(self, action: str, **kwargs):
        """Update sync state on disk."""
        state = self._load_sync_state()
        now = datetime.now(timezone.utc).isoformat()

        if action == "pull":
            state["last_pull_at"] = now
            state["total_pulled"] = state.get("total_pulled", 0) + kwargs.get("pulled", 0)
        elif action == "push":
            state["last_push_at"] = now
            state["total_pushed"] = state.get("total_pushed", 0) + kwargs.get("pushed", 0)

        self._sync_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._sync_state_path.write_text(json.dumps(state, indent=2))
