"""
GitLab Pipelines Source Adapter (CI)

Emits canonical SourceEvent payloads for GitLab CI pipeline runs.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/ci/FAMILY_CONTRACT.md (CI family)

Supports:
  - API mode: Fetches pipelines from GitLab API v4 (requires token)
  - Fixture mode: Pre-parsed run dicts (for testing)

Uses shared GitLabClient for rate limiting and caching.
"""

from datetime import datetime

from evolution.adapters.gitlab_client import GitLabClient


class GitLabPipelinesAdapter:
    source_family = "ci"
    source_type = "gitlab_ci"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, project_id: str = None, token: str = None,
                 client: GitLabClient = None, runs: list = None,
                 source_id: str = None, max_runs: int = 500,
                 fetch_jobs: bool = True):
        """
        Args:
            project_id: GitLab project ID (API mode)
            token: GitLab token (API mode)
            client: Shared GitLabClient instance
            runs: Pre-parsed list of pipeline dicts (fixture mode)
            source_id: Unique identifier
            max_runs: Maximum pipelines to fetch (default 500)
            fetch_jobs: Whether to fetch per-pipeline job details (default True)
        """
        self._fixture_runs = runs
        self.source_id = source_id or (
            f"gitlab_ci:{project_id}" if project_id else "gitlab_ci:fixture"
        )
        self.max_runs = max_runs
        self.fetch_jobs = fetch_jobs

        if runs is None:
            if client:
                self._client = client
            elif project_id:
                self._client = GitLabClient(project_id, token)
            else:
                raise RuntimeError("Provide project_id, client, or runs for fixture mode.")
        else:
            self._client = None

    def _parse_duration(self, pipeline: dict) -> float:
        """Calculate duration from GitLab pipeline timestamps."""
        # GitLab provides duration directly in some cases
        duration = pipeline.get("duration")
        if duration is not None:
            return float(duration)

        started = pipeline.get("started_at")
        finished = pipeline.get("finished_at") or pipeline.get("updated_at")
        if not started or not finished:
            return 0.0
        try:
            s = datetime.fromisoformat(started.replace("Z", "+00:00"))
            f = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            return max(0.0, (f - s).total_seconds())
        except (ValueError, TypeError):
            return 0.0

    def _normalize_status(self, status: str) -> str:
        """Normalize GitLab pipeline status to contract-defined status."""
        status_map = {
            "success": "success",
            "failed": "failure",
            "canceled": "cancelled",
            "skipped": "skipped",
            "manual": "skipped",
            "created": "skipped",
            "waiting_for_resource": "skipped",
            "preparing": "skipped",
            "pending": "skipped",
            "running": "skipped",
            "scheduled": "skipped",
        }
        return status_map.get(status, "failure") if status else "cancelled"

    def _normalize_trigger(self, source: str) -> str:
        """Normalize GitLab pipeline source to contract trigger type."""
        trigger_map = {
            "push": "push",
            "web": "manual",
            "trigger": "manual",
            "schedule": "schedule",
            "api": "manual",
            "pipeline": "manual",
            "merge_request_event": "pull_request",
            "external_pull_request_event": "pull_request",
            "parent_pipeline": "manual",
            "chat": "manual",
        }
        return trigger_map.get(source, "push")

    def _fetch_pipelines(self) -> list:
        """Fetch completed pipelines from GitLab API."""
        # Fetch pipelines sorted by ID ascending (oldest first)
        all_pipelines = self._client.get_paginated(
            "/pipelines",
            per_page=100,
        )

        # Filter to terminal states only
        terminal = {"success", "failed", "canceled", "skipped"}
        completed = [p for p in all_pipelines if p.get("status") in terminal]
        completed.sort(key=lambda p: p.get("created_at", ""))
        return completed[:self.max_runs]

    def _fetch_jobs_for_pipeline(self, pipeline_id: int) -> list:
        """Fetch jobs for a specific pipeline."""
        return self._client.get_paginated(
            f"/pipelines/{pipeline_id}/jobs",
            per_page=100,
        )

    def iter_events(self):
        if self._fixture_runs is not None:
            runs = self._fixture_runs
        else:
            runs = self._fetch_pipelines()

        for pipeline in runs:
            pipeline_id = str(pipeline.get("id", ""))
            status = pipeline.get("status", "")
            ref = pipeline.get("ref", "")
            sha = pipeline.get("sha", "")
            source = pipeline.get("source", "push")

            # Build job list
            jobs = []
            if self.fetch_jobs and self._client and pipeline.get("id"):
                try:
                    raw_jobs = self._fetch_jobs_for_pipeline(pipeline["id"])
                    for job in raw_jobs:
                        job_duration = float(job.get("duration", 0) or 0)
                        jobs.append({
                            "name": job.get("name", "unknown"),
                            "status": self._normalize_status(job.get("status")),
                            "duration_seconds": job_duration,
                        })
                except Exception:
                    pass
            elif pipeline.get("jobs"):
                # Fixture mode may include jobs directly
                jobs = pipeline["jobs"]

            payload = {
                "run_id": pipeline_id,
                "workflow_name": pipeline.get("name", ref),
                "trigger": pipeline.get("trigger", {
                    "type": self._normalize_trigger(source),
                    "ref": ref,
                    "commit_sha": sha,
                }),
                "status": self._normalize_status(status),
                "timing": pipeline.get("timing", {
                    "created_at": pipeline.get("created_at", ""),
                    "started_at": pipeline.get("started_at", ""),
                    "completed_at": pipeline.get("finished_at",
                                                  pipeline.get("updated_at", "")),
                    "duration_seconds": self._parse_duration(pipeline),
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
                    "run_id": pipeline_id,
                    "commit_sha": sha,
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
