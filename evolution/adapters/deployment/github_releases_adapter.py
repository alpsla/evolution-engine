"""
GitHub Releases Source Adapter (Deployment Reference)

Emits canonical SourceEvent payloads for GitHub Releases.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/deployment/FAMILY_CONTRACT.md (deployment family)

Supports:
  - API mode: Fetches releases from GitHub API (requires token)
  - Fixture mode: Pre-parsed deployment dicts (for testing)

Uses the Releases API (/releases) which is widely available on public repos,
rather than the Deployments API (/deployments) which requires specific CI setup.
"""

import hashlib
import json
import os
from datetime import datetime

from evolution.adapters.github_client import GitHubClient


class GitHubReleasesAdapter:
    source_family = "deployment"
    source_type = "github_releases"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, owner: str = None, repo: str = None,
                 token: str = None, client: GitHubClient = None,
                 deployments: list = None, source_id: str = None):
        """
        Args:
            owner: GitHub repo owner (API mode)
            repo: GitHub repo name (API mode)
            token: GitHub token (API mode)
            client: Shared GitHubClient instance
            deployments: Pre-parsed list of deployment dicts (fixture mode)
            source_id: Unique identifier
        """
        self._fixture_deployments = deployments
        self.source_id = source_id or (
            f"github_releases:{owner}/{repo}" if owner else "github_releases:fixture"
        )

        if deployments is None:
            if client:
                self._client = client
            elif owner and repo:
                self._client = GitHubClient(owner, repo, token)
            else:
                raise RuntimeError("Provide owner+repo, client, or deployments.")
        else:
            self._client = None

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _fetch_releases(self) -> list:
        """Fetch releases from GitHub API (oldest first)."""
        releases = self._client.get_paginated("/releases", per_page=100)
        releases.sort(key=lambda r: r.get("published_at") or r.get("created_at", ""))
        return releases

    def _release_to_deployment(self, release: dict) -> dict:
        """Convert a GitHub Release to our deployment event format."""
        created = release.get("published_at") or release.get("created_at", "")
        tag = release.get("tag_name", "")
        is_prerelease = release.get("prerelease", False)

        return {
            "deployment_id": str(release.get("id", "")),
            "environment": "prerelease" if is_prerelease else "production",
            "trigger": {
                "type": "release",
                "commit_sha": release.get("target_commitish", ""),
                "ref": tag,
            },
            "status": "success",  # Published releases are successful
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
                # Compute inter-release interval (release cadence)
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
                d["is_prerelease"] = r.get("prerelease", False)
                d["asset_count"] = len(r.get("assets", []))
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
