"""
GitHub Releases/Deployments Source Adapter (Deployment Reference)

Emits canonical SourceEvent payloads for GitHub deployment events.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/deployment/FAMILY_CONTRACT.md (deployment family)

Accepts:
  - GitHub owner/repo + token (API mode), or
  - A list of pre-parsed deployment dicts (for testing / fixtures)
"""

import hashlib
import json
import os
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None


class GitHubReleasesAdapter:
    source_family = "deployment"
    source_type = "github_releases"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, owner: str = None, repo: str = None,
                 token: str = None, deployments: list = None,
                 source_id: str = None):
        """
        Args:
            owner: GitHub repo owner (API mode)
            repo: GitHub repo name (API mode)
            token: GitHub token (API mode)
            deployments: Pre-parsed list of deployment dicts (for fixtures)
            source_id: Unique identifier for this adapter instance
        """
        self.owner = owner
        self.repo = repo
        self.token = token or os.getenv("GITHUB_TOKEN")
        self._fixture_deployments = deployments
        self.source_id = source_id or f"github_releases:{owner}/{repo}" if owner else "github_releases:fixture"

        if owner and not self.token:
            raise RuntimeError("GitHub token required for API mode.")

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _fetch_deployments(self):
        """Fetch deployments from GitHub API."""
        if requests is None:
            raise RuntimeError("requests library required. pip install requests")

        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/deployments"
        all_deploys = []
        page = 1

        while True:
            resp = requests.get(url, headers=self._headers(),
                                params={"per_page": 100, "page": page}, timeout=30)
            resp.raise_for_status()
            deploys = resp.json()
            if not deploys:
                break
            all_deploys.extend(deploys)
            page += 1

        # Fetch statuses for each deployment
        results = []
        for deploy in all_deploys:
            status_url = deploy["statuses_url"]
            resp = requests.get(status_url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            statuses = resp.json()

            latest_status = statuses[0] if statuses else {}
            state = latest_status.get("state", "unknown")

            status_map = {
                "success": "success", "failure": "failure",
                "error": "failure", "inactive": "success",
                "in_progress": "in_progress", "queued": "in_progress",
                "pending": "in_progress",
            }

            created = deploy.get("created_at", "")
            updated = latest_status.get("created_at", created)

            duration = 0.0
            if created and updated:
                try:
                    s = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    c = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    duration = max(0.0, (c - s).total_seconds())
                except (ValueError, TypeError):
                    pass

            results.append({
                "deployment_id": str(deploy["id"]),
                "environment": deploy.get("environment", "unknown"),
                "trigger": {
                    "type": "automated" if deploy.get("transient_environment") else "manual",
                    "commit_sha": deploy.get("sha", ""),
                    "ref": deploy.get("ref", ""),
                },
                "status": status_map.get(state, "failure"),
                "timing": {
                    "initiated_at": created,
                    "completed_at": updated,
                    "duration_seconds": duration,
                },
                "version": deploy.get("ref", ""),
            })

        results.sort(key=lambda d: d["timing"]["initiated_at"])
        return results

    def iter_events(self):
        if self._fixture_deployments is not None:
            deployments = self._fixture_deployments
        elif self.owner and self.repo:
            deployments = self._fetch_deployments()
        else:
            return

        for deploy in deployments:
            content_hash = self._hash(json.dumps(deploy, sort_keys=True))

            payload = {
                "deployment_id": deploy.get("deployment_id", ""),
                "environment": deploy.get("environment", "unknown"),
                "trigger": deploy.get("trigger", {}),
                "status": deploy.get("status", "unknown"),
                "timing": deploy.get("timing", {}),
                "version": deploy.get("version", ""),
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
