"""
Shared GitLab API Client

Provides rate-limited, cached HTTP access to GitLab REST API v4.
Used by all GitLab-based adapters (CI, Deployment).

Features:
  - Automatic rate limit detection and backoff
  - Response caching (avoids re-fetching on re-runs)
  - Pagination helper (keyset or page-based)
  - Shared across multiple adapters in the same session
  - Works with gitlab.com and self-hosted instances
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None


class GitLabClient:
    """Shared GitLab REST API v4 client with rate limiting and caching."""

    def __init__(self, project_id: str, token: str = None,
                 base_url: str = None, cache_dir: Path = None,
                 max_pages: int = 50):
        """
        Args:
            project_id: GitLab project ID (numeric) or URL-encoded path (e.g. "group%2Fproject")
            token: GitLab personal access token (or GITLAB_TOKEN env)
            base_url: GitLab API base URL (default: https://gitlab.com/api/v4)
            cache_dir: Directory for response caching (optional)
            max_pages: Maximum pages to fetch per endpoint (default 50 = 5000 items)
        """
        if requests is None:
            raise RuntimeError("requests library required. pip install requests")

        self.project_id = project_id
        self.token = token or os.getenv("GITLAB_TOKEN")
        self.max_pages = max_pages
        self.api_base = (base_url or os.getenv("CI_API_V4_URL")
                         or "https://gitlab.com/api/v4")
        self.base_url = f"{self.api_base}/projects/{project_id}"

        if not self.token:
            raise RuntimeError(
                "GitLab token required. Set GITLAB_TOKEN env var or pass token=."
            )

        # Rate limit tracking (GitLab: 300 req/min authenticated)
        self._remaining = 300
        self._reset_at = 0
        self._requests_made = 0

        # Optional response cache
        self._cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _headers(self) -> dict:
        return {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

    def _check_rate_limit(self, response):
        """Update rate limit tracking from response headers."""
        self._remaining = int(response.headers.get("RateLimit-Remaining", 300))
        self._reset_at = int(response.headers.get("RateLimit-Reset", 0))

        if self._remaining < 20:
            wait = max(0, self._reset_at - time.time()) + 1
            if 0 < wait < 300:  # Don't wait more than 5 min
                print(f"  [gitlab] Rate limit low ({self._remaining} remaining), "
                      f"waiting {wait:.0f}s...")
                time.sleep(wait)

    def _cache_key(self, url: str, params: dict = None) -> str:
        """Generate a cache filename from URL + params."""
        import hashlib
        raw = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _get_cached(self, key: str) -> Optional[dict]:
        if not self._cache_dir:
            return None
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        return None

    def _set_cached(self, key: str, data):
        if not self._cache_dir:
            return
        cache_file = self._cache_dir / f"{key}.json"
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, path: str, params: dict = None, use_cache: bool = True) -> dict:
        """
        GET request with rate limiting and optional caching.

        Args:
            path: API path (appended to project base_url), e.g. "/pipelines"
            params: Query parameters
            use_cache: Whether to use response caching
        """
        url = f"{self.base_url}{path}"
        cache_key = self._cache_key(url, params)

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        resp = requests.get(url, headers=self._headers(),
                            params=params, timeout=30)
        self._requests_made += 1
        self._check_rate_limit(resp)
        resp.raise_for_status()

        data = resp.json()
        if use_cache:
            self._set_cached(cache_key, data)
        return data

    def get_paginated(self, path: str, per_page: int = 100,
                      use_cache: bool = True) -> list:
        """
        Fetch all pages of a paginated endpoint.

        GitLab returns lists directly (not wrapped in an object),
        so no list_key parameter is needed.

        Args:
            path: API path
            per_page: Items per page (max 100)
            use_cache: Whether to cache responses
        """
        all_items = []
        page = 1

        while page <= self.max_pages:
            params = {"per_page": per_page, "page": page}
            data = self.get(path, params=params, use_cache=use_cache)

            if not isinstance(data, list) or not data:
                break

            all_items.extend(data)
            page += 1

            # GitLab returns fewer items on last page
            if len(data) < per_page:
                break

        return all_items

    @property
    def stats(self) -> dict:
        """Return API usage statistics."""
        return {
            "requests_made": self._requests_made,
            "rate_limit_remaining": self._remaining,
        }
