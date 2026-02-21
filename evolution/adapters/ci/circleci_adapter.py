"""
CircleCI Source Adapter (CI)

Emits canonical SourceEvent payloads for CircleCI pipeline runs.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/ci/FAMILY_CONTRACT.md (CI family)

Supports:
  - API mode: Fetches pipelines from CircleCI API v2 (requires token)
  - Fixture mode: Pre-parsed run dicts (for testing)

CircleCI API v2 uses project slugs like "gh/owner/repo" or "bb/owner/repo".
Auth is via CIRCLECI_TOKEN env var (personal API token).
"""

import json
import os
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None


class CircleCIAdapter:
    source_family = "ci"
    source_type = "circleci"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    API_BASE = "https://circleci.com/api/v2"

    def __init__(self, *, project_slug: str = None, token: str = None,
                 runs: list = None, source_id: str = None,
                 max_runs: int = 500, cache_dir: Path = None):
        """
        Args:
            project_slug: CircleCI project slug (e.g. "gh/owner/repo")
            token: CircleCI personal API token (or CIRCLECI_TOKEN env)
            runs: Pre-parsed list of pipeline dicts (fixture mode)
            source_id: Unique identifier
            max_runs: Maximum pipelines to fetch (default 500)
            cache_dir: Directory for response caching (optional)
        """
        self._fixture_runs = runs
        self.source_id = source_id or (
            f"circleci:{project_slug}" if project_slug else "circleci:fixture"
        )
        self.max_runs = max_runs
        self._project_slug = project_slug
        self._token = token or os.getenv("CIRCLECI_TOKEN")
        self._cache_dir = cache_dir
        self._requests_made = 0

        if runs is None:
            if _requests is None:
                raise RuntimeError("requests library required. pip install requests")
            if not project_slug:
                raise RuntimeError(
                    "Provide project_slug or runs for fixture mode."
                )
            if not self._token:
                raise RuntimeError(
                    "CircleCI token required. Set CIRCLECI_TOKEN env var or pass token=."
                )

    def _headers(self) -> dict:
        return {
            "Circle-Token": self._token,
            "Accept": "application/json",
        }

    def _cache_key(self, url: str, params: dict = None) -> str:
        raw = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _get(self, url: str, params: dict = None) -> dict:
        """GET with caching."""
        if self._cache_dir:
            key = self._cache_key(url, params)
            cache_file = self._cache_dir / f"{key}.json"
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))

        resp = _requests.get(url, headers=self._headers(),
                             params=params, timeout=30)
        self._requests_made += 1
        resp.raise_for_status()
        data = resp.json()

        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_dir / f"{key}.json"
            cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return data

    def _normalize_status(self, status: str) -> str:
        """Normalize CircleCI status to contract-defined status."""
        status_map = {
            "success": "success",
            "failed": "failure",
            "error": "failure",
            "canceled": "cancelled",
            "cancelled": "cancelled",
            "not_run": "skipped",
            "infrastructure_fail": "failure",
            "timedout": "failure",
            "on_hold": "skipped",
            "blocked": "skipped",
        }
        return status_map.get(status, "failure") if status else "cancelled"

    def _normalize_trigger(self, trigger_type: str) -> str:
        """Normalize CircleCI trigger type."""
        trigger_map = {
            "webhook": "push",
            "api": "manual",
            "schedule": "schedule",
            "explicit": "manual",
        }
        return trigger_map.get(trigger_type, "push")

    def _fetch_pipelines(self) -> list:
        """Fetch pipelines from CircleCI API v2."""
        url = f"{self.API_BASE}/project/{self._project_slug}/pipeline"
        all_pipelines = []
        next_page = None

        while len(all_pipelines) < self.max_runs:
            params = {"page-token": next_page} if next_page else {}
            data = self._get(url, params=params)

            items = data.get("items", [])
            if not items:
                break

            all_pipelines.extend(items)
            next_page = data.get("next_page_token")
            if not next_page:
                break

        return all_pipelines[:self.max_runs]

    def _fetch_workflows(self, pipeline_id: str) -> list:
        """Fetch workflows for a pipeline."""
        url = f"{self.API_BASE}/pipeline/{pipeline_id}/workflow"
        data = self._get(url)
        return data.get("items", [])

    def iter_events(self):
        if self._fixture_runs is not None:
            runs = self._fixture_runs
            for run in runs:
                yield self._run_to_event(run)
            return

        pipelines = self._fetch_pipelines()

        for pipeline in pipelines:
            pipeline_id = pipeline.get("id", "")
            sha = (pipeline.get("vcs", {}).get("revision", "")
                   or pipeline.get("trigger_parameters", {}).get("git", {}).get("revision", ""))
            branch = (pipeline.get("vcs", {}).get("branch", "")
                      or pipeline.get("trigger_parameters", {}).get("git", {}).get("branch", ""))
            trigger_type = pipeline.get("trigger", {}).get("type", "webhook")

            # Fetch workflows to get timing and status
            try:
                workflows = self._fetch_workflows(pipeline_id)
            except Exception:
                workflows = []

            if not workflows:
                continue

            # Use the first workflow as the primary (most pipelines have one)
            for wf in workflows:
                wf_status = wf.get("status", "")
                # Skip non-terminal workflows
                if wf_status in ("running", "not_run", "on_hold", "failing"):
                    continue

                created = wf.get("created_at", pipeline.get("created_at", ""))
                stopped = wf.get("stopped_at", "")
                duration = 0.0
                if created and stopped:
                    try:
                        s = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        e = datetime.fromisoformat(stopped.replace("Z", "+00:00"))
                        duration = max(0.0, (e - s).total_seconds())
                    except (ValueError, TypeError):
                        pass

                run = {
                    "run_id": wf.get("id", pipeline_id),
                    "workflow_name": wf.get("name", "workflow"),
                    "trigger": {
                        "type": self._normalize_trigger(trigger_type),
                        "ref": branch,
                        "commit_sha": sha,
                    },
                    "status": self._normalize_status(wf_status),
                    "timing": {
                        "created_at": created,
                        "started_at": created,
                        "completed_at": stopped,
                        "duration_seconds": duration,
                    },
                    "jobs": [],
                }

                yield self._run_to_event(run)

    def _run_to_event(self, run: dict) -> dict:
        """Convert a normalized run dict to a SourceEvent."""
        run_id = str(run.get("run_id", ""))
        return {
            "source_family": self.source_family,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "ordering_mode": self.ordering_mode,
            "attestation": {
                "type": "ci_run",
                "run_id": run_id,
                "commit_sha": run.get("trigger", {}).get("commit_sha", ""),
                "trust_tier": self.attestation_tier,
            },
            "predecessor_refs": None,
            "payload": run,
        }
