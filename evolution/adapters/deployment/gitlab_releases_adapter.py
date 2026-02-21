"""
GitLab Releases Source Adapter (Deployment)

Emits canonical SourceEvent payloads for GitLab Releases.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/deployment/FAMILY_CONTRACT.md (deployment family)

Supports:
  - API mode: Fetches releases from GitLab API v4 (requires token)
  - Fixture mode: Pre-parsed deployment dicts (for testing)

Uses shared GitLabClient for rate limiting and caching.
"""

import hashlib
import json
from datetime import datetime

from evolution.adapters.gitlab_client import GitLabClient


class GitLabReleasesAdapter:
    source_family = "deployment"
    source_type = "gitlab_releases"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, project_id: str = None, token: str = None,
                 client: GitLabClient = None, deployments: list = None,
                 source_id: str = None):
        """
        Args:
            project_id: GitLab project ID (API mode)
            token: GitLab token (API mode)
            client: Shared GitLabClient instance
            deployments: Pre-parsed list of deployment dicts (fixture mode)
            source_id: Unique identifier
        """
        self._fixture_deployments = deployments
        self.source_id = source_id or (
            f"gitlab_releases:{project_id}" if project_id else "gitlab_releases:fixture"
        )

        if deployments is None:
            if client:
                self._client = client
            elif project_id:
                self._client = GitLabClient(project_id, token)
            else:
                raise RuntimeError("Provide project_id, client, or deployments.")
        else:
            self._client = None

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _fetch_releases(self) -> list:
        """Fetch releases from GitLab API (oldest first)."""
        releases = self._client.get_paginated("/releases", per_page=100)
        releases.sort(key=lambda r: r.get("released_at") or r.get("created_at", ""))
        return releases

    def _release_to_deployment(self, release: dict) -> dict:
        """Convert a GitLab Release to deployment event format."""
        created = release.get("released_at") or release.get("created_at", "")
        tag = release.get("tag_name", "")

        # GitLab releases don't have a prerelease flag like GitHub.
        # Heuristic: tag contains "alpha", "beta", "rc", "pre"
        tag_lower = tag.lower()
        is_prerelease = any(
            marker in tag_lower
            for marker in ("alpha", "beta", "rc", "pre", "dev", "snapshot")
        )

        # GitLab provides commit info in release
        commit_info = release.get("commit", {})
        commit_sha = commit_info.get("id", "") if commit_info else ""

        return {
            "deployment_id": str(release.get("tag_name", "")),
            "environment": "prerelease" if is_prerelease else "production",
            "trigger": {
                "type": "release",
                "commit_sha": commit_sha,
                "ref": tag,
            },
            "status": "success",
            "timing": {
                "initiated_at": created,
                "completed_at": created,
                "duration_seconds": 0.0,
            },
            "version": tag,
            "is_rollback": False,
        }

    def iter_events(self):
        if self._fixture_deployments is not None:
            deployments = self._fixture_deployments
        else:
            raw_releases = self._fetch_releases()
            deployments = []
            prev_time = None
            for r in raw_releases:
                d = self._release_to_deployment(r)
                # Compute inter-release interval
                current_time = d["timing"]["initiated_at"]
                since_previous = None
                if prev_time and current_time:
                    try:
                        t1 = datetime.fromisoformat(prev_time.replace("Z", "+00:00"))
                        t2 = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
                        since_previous = max(0.0, (t2 - t1).total_seconds())
                    except (ValueError, TypeError):
                        pass
                d["timing"]["since_previous_seconds"] = since_previous
                d["is_prerelease"] = any(
                    m in (r.get("tag_name", "")).lower()
                    for m in ("alpha", "beta", "rc", "pre", "dev", "snapshot")
                )
                # GitLab releases have "assets.links" and "assets.sources"
                assets = r.get("assets", {})
                link_count = len(assets.get("links", []))
                source_count = len(assets.get("sources", []))
                d["asset_count"] = link_count + source_count
                prev_time = current_time
                deployments.append(d)

        for deploy in deployments:
            content_hash = self._hash(json.dumps(deploy, sort_keys=True))

            payload = {
                "deployment_id": deploy.get("deployment_id", ""),
                "environment": deploy.get("environment", "unknown"),
                "trigger": deploy.get("trigger", {}),
                "status": deploy.get("status", "unknown"),
                "timing": deploy.get("timing", {}),
                "version": deploy.get("version", ""),
                "is_rollback": deploy.get("is_rollback", False),
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "deployment",
                    "deployment_id": payload["deployment_id"],
                    "commit_sha": payload["trigger"].get("commit_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
