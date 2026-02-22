"""
Sentry Source Adapter (Error Tracking)

Emits canonical SourceEvent payloads for Sentry issues.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)

Supports:
  - API mode: Fetches issues from Sentry API v0 (requires auth token)
  - Fixture mode: Pre-parsed issue dicts (for testing)

Auth is via SENTRY_AUTH_TOKEN env var (Bearer token).
Supports self-hosted Sentry instances via base_url parameter.
"""

import json
import os
import hashlib
from pathlib import Path
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None


class SentryAdapter:
    source_family = "error_tracking"
    source_type = "sentry"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    API_BASE = "https://sentry.io/api/0"

    def __init__(self, *, org: str = None, project: str = None,
                 token: str = None, issues: list = None,
                 source_id: str = None, max_issues: int = 500,
                 cache_dir: Path = None, base_url: str = None):
        """
        Args:
            org: Sentry organization slug
            project: Sentry project slug
            token: Sentry auth token (or SENTRY_AUTH_TOKEN env)
            issues: Pre-parsed list of issue dicts (fixture mode)
            source_id: Unique identifier
            max_issues: Maximum issues to fetch (default 500)
            cache_dir: Directory for response caching (optional)
            base_url: Base URL for self-hosted Sentry (e.g. "https://sentry.mycompany.com/api/0")
        """
        self._fixture_issues = issues
        self._api_base = base_url or self.API_BASE
        self.source_id = source_id or (
            f"sentry:{org}/{project}" if org and project else "sentry:fixture"
        )
        self.max_issues = max_issues
        self._org = org
        self._project = project
        self._token = token or os.getenv("SENTRY_AUTH_TOKEN")
        self._cache_dir = cache_dir
        self._requests_made = 0

        if issues is None:
            if _requests is None:
                raise RuntimeError("requests library required. pip install requests")
            if not org or not project:
                raise RuntimeError(
                    "Provide org and project, or issues for fixture mode."
                )
            if not self._token:
                raise RuntimeError(
                    "Sentry auth token required. Set SENTRY_AUTH_TOKEN env var or pass token=."
                )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    def _cache_key(self, url: str, params: dict = None) -> str:
        raw = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _get(self, url: str, params: dict = None) -> tuple:
        """GET with caching. Returns (json_data, response_headers)."""
        if self._cache_dir:
            key = self._cache_key(url, params)
            cache_file = self._cache_dir / f"{key}.json"
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8")), {}

        resp = _requests.get(url, headers=self._headers(),
                             params=params, timeout=30)
        self._requests_made += 1
        resp.raise_for_status()
        data = resp.json()

        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_dir / f"{key}.json"
            cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return data, resp.headers

    def _normalize_level(self, level: str) -> str:
        """Normalize Sentry issue level."""
        level_map = {
            "fatal": "fatal",
            "error": "error",
            "warning": "warning",
            "info": "info",
            "debug": "debug",
            "sample": "info",
        }
        return level_map.get(level, "error") if level else "error"

    def _normalize_status(self, status: str) -> str:
        """Normalize Sentry issue status."""
        status_map = {
            "unresolved": "unresolved",
            "resolved": "resolved",
            "ignored": "ignored",
            "muted": "ignored",
            "resolvedInNextRelease": "resolved",
        }
        return status_map.get(status, "unresolved") if status else "unresolved"

    def _fetch_issues(self) -> list:
        """Fetch issues from Sentry API."""
        url = f"{self._api_base}/projects/{self._org}/{self._project}/issues/"
        all_issues = []
        params = {
            "query": "is:unresolved",
            "statsPeriod": "90d",
            "sort": "date",
        }

        while len(all_issues) < self.max_issues:
            data, headers = self._get(url, params=params)

            if not isinstance(data, list) or not data:
                break

            all_issues.extend(data)

            # Cursor-based pagination via Link header
            link = headers.get("Link", "")
            next_url = self._parse_next_link(link)
            if not next_url:
                break
            url = next_url
            params = {}  # URL already contains params

        return all_issues[:self.max_issues]

    @staticmethod
    def _parse_next_link(link_header: str) -> Optional[str]:
        """Parse Sentry's Link header for the next page URL."""
        if not link_header:
            return None
        for part in link_header.split(","):
            part = part.strip()
            if 'rel="next"' in part and 'results="true"' in part:
                url = part.split(";")[0].strip().strip("<>")
                return url
        return None

    def iter_events(self):
        if self._fixture_issues is not None:
            issues = self._fixture_issues
        else:
            issues = self._fetch_issues()

        # Sort by firstSeen for temporal ordering
        issues.sort(key=lambda i: i.get("firstSeen", ""))

        for issue in issues:
            yield self._issue_to_event(issue)

    def _issue_to_event(self, issue: dict) -> dict:
        """Convert a Sentry issue dict to a SourceEvent."""
        issue_id = str(issue.get("id", ""))
        first_seen = issue.get("firstSeen", "")
        last_seen = issue.get("lastSeen", "")
        level = self._normalize_level(issue.get("level", "error"))
        status = self._normalize_status(issue.get("status", "unresolved"))
        is_unhandled = bool(issue.get("isUnhandled", False))
        title = issue.get("title", "")
        count = int(issue.get("count", 0))
        user_count = int(issue.get("userCount", 0))

        # Extract release from metadata if available
        release = ""
        metadata = issue.get("metadata", {})
        if isinstance(metadata, dict):
            release = metadata.get("release", "")

        payload = {
            "issue_id": issue_id,
            "title": title,
            "level": level,
            "status": status,
            "is_unhandled": is_unhandled,
            "trigger": {
                "type": "error",
                "commit_sha": "",
                "release": release,
            },
            "timing": {
                "first_seen": first_seen,
                "last_seen": last_seen,
            },
            "stats": {
                "event_count": count,
                "user_count": user_count,
            },
        }

        return {
            "source_family": self.source_family,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "ordering_mode": self.ordering_mode,
            "attestation": {
                "type": "error_issue",
                "issue_id": issue_id,
                "trust_tier": self.attestation_tier,
            },
            "predecessor_refs": None,
            "payload": payload,
        }
