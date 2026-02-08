"""
Shared GitHub API Client

Provides rate-limited, cached HTTP access to GitHub REST API.
Used by all GitHub-based adapters (CI, Deployment, Security).

Features:
  - Automatic rate limit detection and backoff
  - Response caching (avoids re-fetching on re-runs)
  - Pagination helper
  - Shared across multiple adapters in the same session
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None


class GitHubClient:
    """Shared GitHub REST API client with rate limiting and caching."""

    def __init__(self, owner: str, repo: str, token: str = None,
                 cache_dir: Path = None, max_pages: int = 50):
        """
        Args:
            owner: GitHub repo owner
            repo: GitHub repo name
            token: GitHub personal access token (or GITHUB_TOKEN env)
            cache_dir: Directory for response caching (optional)
            max_pages: Maximum pages to fetch per endpoint (default 50 = 5000 items)
        """
        if requests is None:
            raise RuntimeError("requests library required. pip install requests")

        self.owner = owner
        self.repo = repo
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.max_pages = max_pages
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"

        if not self.token:
            raise RuntimeError(
                "GitHub token required. Set GITHUB_TOKEN env var or pass token=."
            )

        # Rate limit tracking
        self._remaining = 5000
        self._reset_at = 0
        self._requests_made = 0

        # Optional response cache
        self._cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _check_rate_limit(self, response):
        """Update rate limit tracking from response headers."""
        self._remaining = int(response.headers.get("X-RateLimit-Remaining", 5000))
        self._reset_at = int(response.headers.get("X-RateLimit-Reset", 0))

        if self._remaining < 50:
            wait = max(0, self._reset_at - time.time()) + 1
            if wait > 0 and wait < 900:  # Don't wait more than 15 min
                print(f"  [github] Rate limit low ({self._remaining} remaining), "
                      f"waiting {wait:.0f}s...")
                time.sleep(wait)

    def _cache_key(self, url: str, params: dict = None) -> str:
        """Generate a cache filename from URL + params."""
        import hashlib
        raw = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _get_cached(self, key: str) -> Optional[dict]:
        """Load cached response if available."""
        if not self._cache_dir:
            return None
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        return None

    def _set_cached(self, key: str, data):
        """Save response to cache."""
        if not self._cache_dir:
            return
        cache_file = self._cache_dir / f"{key}.json"
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, path: str, params: dict = None, use_cache: bool = True) -> dict:
        """
        GET request with rate limiting and optional caching.

        Args:
            path: API path (appended to base_url), e.g. "/actions/runs"
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

    def get_paginated(self, path: str, list_key: str = None,
                      per_page: int = 100, use_cache: bool = True) -> list:
        """
        Fetch all pages of a paginated endpoint.

        Args:
            path: API path
            list_key: JSON key containing the list (e.g. "workflow_runs").
                      If None, response is assumed to be a list directly.
            per_page: Items per page
            use_cache: Whether to cache responses
        """
        all_items = []
        page = 1

        while page <= self.max_pages:
            params = {"per_page": per_page, "page": page}
            data = self.get(path, params=params, use_cache=use_cache)

            if list_key:
                items = data.get(list_key, [])
                total = data.get("total_count", None)
            else:
                items = data if isinstance(data, list) else []
                total = None

            if not items:
                break

            all_items.extend(items)
            page += 1

            # Stop if we've fetched everything
            if total is not None and len(all_items) >= total:
                break

        return all_items

    @property
    def stats(self) -> dict:
        """Return API usage statistics."""
        return {
            "requests_made": self._requests_made,
            "rate_limit_remaining": self._remaining,
        }
