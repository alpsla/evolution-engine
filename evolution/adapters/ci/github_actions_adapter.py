"""
GitHub Actions Source Adapter (CI Reference)

Emits canonical SourceEvent payloads for GitHub Actions workflow runs.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/ci/FAMILY_CONTRACT.md (CI family)

Supports:
  - API mode: Fetches runs from GitHub API (requires token)
  - Fixture mode: Pre-parsed run dicts (for testing)

Uses shared GitHubClient for rate limiting and caching.
"""

import hashlib
import json
import os
from datetime import datetime

from evolution.adapters.github_client import GitHubClient


class GitHubActionsAdapter:
    source_family = "ci"
    source_type = "github_actions"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, owner: str = None, repo: str = None,
                 token: str = None, client: GitHubClient = None,
                 runs: list = None, source_id: str = None,
                 max_runs: int = 500, fetch_jobs: bool = False):
        """
        Args:
            owner: GitHub repo owner (API mode)
            repo: GitHub repo name (API mode)
            token: GitHub token (API mode)
            client: Shared GitHubClient instance (reuses rate limiting/cache)
            runs: Pre-parsed list of run dicts (fixture mode)
            source_id: Unique identifier
            max_runs: Maximum workflow runs to fetch (default 500)
            fetch_jobs: Whether to fetch per-run job details (slower, N+1 calls)
        """
        self._fixture_runs = runs
        self.source_id = source_id or (
            f"github_actions:{owner}/{repo}" if owner else "github_actions:fixture"
        )
        self.max_runs = max_runs
        self.fetch_jobs = fetch_jobs

        if runs is None:
            if client:
                self._client = client
            elif owner and repo:
                self._client = GitHubClient(owner, repo, token)
            else:
                raise RuntimeError("Provide owner+repo, client, or runs for fixture mode.")
        else:
            self._client = None

    def _parse_duration(self, run: dict) -> float:
        """Calculate duration in seconds from run timestamps."""
        started = run.get("run_started_at") or run.get("created_at")
        completed = run.get("updated_at")
        if not started or not completed:
            return 0.0
        try:
            s = datetime.fromisoformat(started.replace("Z", "+00:00"))
            c = datetime.fromisoformat(completed.replace("Z", "+00:00"))
            return max(0.0, (c - s).total_seconds())
        except (ValueError, TypeError):
            return 0.0

    def _normalize_status(self, conclusion: str) -> str:
        """Normalize GitHub's conclusion to contract-defined status."""
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

    def _fetch_runs(self) -> list:
        """Fetch completed workflow runs from GitHub API."""
        all_runs = self._client.get_paginated(
            "/actions/runs",
            list_key="workflow_runs",
            per_page=100,
        )

        # Filter to completed runs, cap at max_runs
        completed = [r for r in all_runs if r.get("status") == "completed"]
        completed.sort(key=lambda r: r.get("created_at", ""))
        return completed[:self.max_runs]

    def _fetch_jobs_for_run(self, run_id: int) -> list:
        """Fetch jobs for a specific workflow run (optional, slower)."""
        data = self._client.get(f"/actions/runs/{run_id}/jobs")
        return data.get("jobs", [])

    def iter_events(self):
        if self._fixture_runs is not None:
            runs = self._fixture_runs
        else:
            runs = self._fetch_runs()

        for run in runs:
            run_id = str(run.get("id", run.get("run_id", "")))
            conclusion = run.get("conclusion", "")

            # Build job list
            jobs = []
            if self.fetch_jobs and self._client and "id" in run:
                raw_jobs = self._fetch_jobs_for_run(run["id"])
                for job in raw_jobs:
                    job_started = job.get("started_at")
                    job_completed = job.get("completed_at")
                    job_duration = 0.0
                    if job_started and job_completed:
                        try:
                            s = datetime.fromisoformat(job_started.replace("Z", "+00:00"))
                            c = datetime.fromisoformat(job_completed.replace("Z", "+00:00"))
                            job_duration = max(0.0, (c - s).total_seconds())
                        except (ValueError, TypeError):
                            pass
                    jobs.append({
                        "name": job["name"],
                        "status": self._normalize_status(job.get("conclusion")),
                        "duration_seconds": job_duration,
                    })
            elif run.get("jobs"):
                # Fixture mode may include jobs directly
                jobs = run["jobs"]

            payload = {
                "run_id": run_id,
                "workflow_name": run.get("name", run.get("workflow_name", "unknown")),
                "trigger": run.get("trigger", {
                    "type": run.get("event", "unknown"),
                    "ref": run.get("head_branch", ""),
                    "commit_sha": run.get("head_sha", ""),
                }),
                "status": self._normalize_status(conclusion),
                "timing": run.get("timing", {
                    "created_at": run.get("created_at", ""),
                    "started_at": run.get("run_started_at", ""),
                    "completed_at": run.get("updated_at", ""),
                    "duration_seconds": self._parse_duration(run),
                }),
                "jobs": jobs,
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "ci_run",
                    "run_id": run_id,
                    "commit_sha": payload["trigger"].get("commit_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
