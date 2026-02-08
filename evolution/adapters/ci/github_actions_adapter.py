"""
GitHub Actions Source Adapter (CI Reference)

Emits canonical SourceEvent payloads for GitHub Actions workflow runs.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/ci/FAMILY_CONTRACT.md (CI family)

Requires:
  - GITHUB_TOKEN environment variable (or gh CLI authentication)
  - Repository owner/name
"""

import os
import json
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None


class GitHubActionsAdapter:
    source_family = "ci"
    source_type = "github_actions"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, owner: str, repo: str, token: str = None):
        self.owner = owner
        self.repo = repo
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.source_id = f"github_actions:{owner}/{repo}"
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"

        if not self.token:
            raise RuntimeError(
                "GitHub token required. Set GITHUB_TOKEN environment variable "
                "or pass token= to the adapter."
            )

        if requests is None:
            raise RuntimeError("requests library is required. Install with: pip install requests")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _fetch_runs(self, per_page: int = 100):
        """Fetch workflow runs from GitHub API, oldest first."""
        all_runs = []
        page = 1

        while True:
            url = f"{self.base_url}/actions/runs"
            params = {"per_page": per_page, "page": page}
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            runs = data.get("workflow_runs", [])
            if not runs:
                break

            all_runs.extend(runs)
            page += 1

            # Stop if we've fetched all runs
            if len(all_runs) >= data.get("total_count", 0):
                break

        # Oldest first (temporal ordering)
        all_runs.sort(key=lambda r: r["created_at"])
        return all_runs

    def _fetch_jobs(self, run_id: int):
        """Fetch jobs for a specific workflow run."""
        url = f"{self.base_url}/actions/runs/{run_id}/jobs"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json().get("jobs", [])

    def _parse_duration(self, run: dict) -> float:
        """Calculate duration in seconds from run timestamps."""
        if not run.get("run_started_at") or not run.get("updated_at"):
            return 0.0

        started = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
        completed = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        return max(0.0, (completed - started).total_seconds())

    def _normalize_status(self, run: dict) -> str:
        """Normalize GitHub's conclusion to contract-defined status."""
        conclusion = run.get("conclusion")
        status_map = {
            "success": "success",
            "failure": "failure",
            "cancelled": "cancelled",
            "skipped": "skipped",
            "timed_out": "failure",
            "action_required": "failure",
            "stale": "cancelled",
        }
        return status_map.get(conclusion, "failure") if conclusion else "cancelled"

    def iter_events(self):
        runs = self._fetch_runs()

        for run in runs:
            # Only emit completed runs
            if run.get("status") != "completed":
                continue

            # Fetch job details
            raw_jobs = self._fetch_jobs(run["id"])
            jobs = []
            for job in raw_jobs:
                job_started = job.get("started_at")
                job_completed = job.get("completed_at")
                job_duration = 0.0
                if job_started and job_completed:
                    s = datetime.fromisoformat(job_started.replace("Z", "+00:00"))
                    c = datetime.fromisoformat(job_completed.replace("Z", "+00:00"))
                    job_duration = max(0.0, (c - s).total_seconds())

                jobs.append({
                    "name": job["name"],
                    "status": self._normalize_status({"conclusion": job.get("conclusion")}),
                    "duration_seconds": job_duration,
                })

            payload = {
                "run_id": str(run["id"]),
                "workflow_name": run.get("name", "unknown"),
                "trigger": {
                    "type": run.get("event", "unknown"),
                    "ref": run.get("head_branch", ""),
                    "commit_sha": run.get("head_sha", ""),
                },
                "status": self._normalize_status(run),
                "timing": {
                    "created_at": run.get("created_at", ""),
                    "started_at": run.get("run_started_at", ""),
                    "completed_at": run.get("updated_at", ""),
                    "duration_seconds": self._parse_duration(run),
                },
                "jobs": jobs,
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "ci_run",
                    "run_id": str(run["id"]),
                    "commit_sha": run.get("head_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
