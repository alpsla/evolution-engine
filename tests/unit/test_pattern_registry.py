"""
Unit tests for pattern registry (evolution/pattern_registry.py).

All network calls are mocked to avoid real PyPI requests during tests.
"""

import io
import json
import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.pattern_registry import (
    CACHE_TTL,
    PATTERN_CACHE_PATH,
    USER_BLOCKLIST_PATH,
    USER_SOURCES_PATH,
    _download_and_extract_patterns,
    _filter_by_families,
    _get_cached_or_fetch,
    _load_blocklist,
    _load_cache,
    _load_pattern_index,
    _save_cache,
    add_pattern_source,
    block_pattern_package,
    fetch_available_patterns,
    list_pattern_packages,
    remove_pattern_source,
    unblock_pattern_package,
)


# ─── Sample pattern data ───

SAMPLE_PATTERN = {
    "fingerprint": "3aab010d317b22df",
    "pattern_type": "co_occurrence",
    "discovery_method": "statistical",
    "sources": ["ci", "git"],
    "metrics": ["ci_presence", "dispersion"],
    "description_statistical": "When ci events occur, git.dispersion increases.",
    "correlation_strength": 0.38,
    "occurrence_count": 100,
    "confidence_tier": "confirmed",
    "scope": "community",
}

SAMPLE_PATTERN_DEP = {
    "fingerprint": "d3b14f1a8c2e7690",
    "pattern_type": "co_occurrence",
    "discovery_method": "statistical",
    "sources": ["dependency", "git"],
    "metrics": ["dependency_presence", "dispersion"],
    "description_statistical": "When dependency events occur, git.dispersion increases.",
    "correlation_strength": 0.45,
    "occurrence_count": 50,
    "confidence_tier": "statistical",
    "scope": "community",
}


@pytest.fixture(autouse=True)
def isolate_paths(tmp_path, monkeypatch):
    """Redirect all file paths to tmp_path for test isolation."""
    cache_file = tmp_path / "pattern_cache.json"
    sources_file = tmp_path / "pattern_sources.json"
    blocklist_file = tmp_path / "pattern_blocklist.json"

    monkeypatch.setattr("evolution.pattern_registry.PATTERN_CACHE_PATH", cache_file)
    monkeypatch.setattr("evolution.pattern_registry.USER_SOURCES_PATH", sources_file)
    monkeypatch.setattr("evolution.pattern_registry.USER_BLOCKLIST_PATH", blocklist_file)
    return tmp_path


def _make_wheel_bytes(patterns):
    """Create a minimal wheel zip file containing patterns.json."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("evo_patterns_test/patterns.json", json.dumps(patterns))
    return buf.getvalue()


# ─── _filter_by_families ───


class TestFilterByFamilies:
    def test_keeps_matching_patterns(self):
        result = _filter_by_families([SAMPLE_PATTERN], {"ci", "git"})
        assert len(result) == 1

    def test_keeps_if_any_source_matches(self):
        result = _filter_by_families([SAMPLE_PATTERN], {"ci"})
        assert len(result) == 1

    def test_excludes_non_matching(self):
        result = _filter_by_families([SAMPLE_PATTERN], {"deployment"})
        assert len(result) == 0

    def test_empty_families(self):
        result = _filter_by_families([SAMPLE_PATTERN], set())
        assert len(result) == 0

    def test_empty_patterns(self):
        result = _filter_by_families([], {"ci"})
        assert len(result) == 0

    def test_mixed_patterns(self):
        result = _filter_by_families([SAMPLE_PATTERN, SAMPLE_PATTERN_DEP], {"ci"})
        assert len(result) == 1
        assert result[0]["fingerprint"] == "3aab010d317b22df"


# ─── _load_pattern_index ───


class TestLoadPatternIndex:
    def test_loads_bundled_index(self):
        # Should at least load the bundled data file
        packages = _load_pattern_index()
        assert isinstance(packages, list)

    def test_merges_user_sources(self, tmp_path):
        sources_path = tmp_path / "pattern_sources.json"
        sources_path.write_text(json.dumps(["evo-patterns-custom"]))
        packages = _load_pattern_index()
        assert "evo-patterns-custom" in packages


# ─── _load_blocklist ───


class TestLoadBlocklist:
    def test_empty_by_default(self):
        blocked = _load_blocklist()
        assert isinstance(blocked, set)

    def test_loads_user_blocklist_strings(self, tmp_path):
        bl_path = tmp_path / "pattern_blocklist.json"
        bl_path.write_text(json.dumps(["bad-pkg"]))
        blocked = _load_blocklist()
        assert "bad-pkg" in blocked

    def test_loads_user_blocklist_dicts(self, tmp_path):
        bl_path = tmp_path / "pattern_blocklist.json"
        bl_path.write_text(json.dumps([{"name": "bad-pkg", "reason": "test"}]))
        blocked = _load_blocklist()
        assert "bad-pkg" in blocked


# ─── Cache ───


class TestCache:
    def test_save_and_load(self, tmp_path):
        cache_data = {"test-pkg": {"version": "1.0.0", "last_fetched": time.time()}}
        _save_cache(cache_data)
        loaded = _load_cache()
        assert loaded["test-pkg"]["version"] == "1.0.0"

    def test_empty_cache(self):
        loaded = _load_cache()
        assert loaded == {}


# ─── _get_cached_or_fetch ───


class TestGetCachedOrFetch:
    def test_returns_cached_entry_if_fresh(self):
        cache = {
            "test-pkg": {
                "version": "1.0.0",
                "last_fetched": time.time(),
                "families": ["ci"],
                "patterns": [SAMPLE_PATTERN],
            }
        }
        _save_cache(cache)

        result = _get_cached_or_fetch("test-pkg")
        assert result is not None
        assert result["version"] == "1.0.0"

    def test_returns_stale_cache_if_pypi_fails(self):
        cache = {
            "test-pkg": {
                "version": "1.0.0",
                "last_fetched": time.time() - CACHE_TTL - 100,
                "families": ["ci"],
                "patterns": [SAMPLE_PATTERN],
            }
        }
        _save_cache(cache)

        with patch("evolution.pattern_registry.check_pypi_version", return_value=None):
            result = _get_cached_or_fetch("test-pkg")
        assert result is not None
        assert result["version"] == "1.0.0"

    def test_refreshes_timestamp_if_version_unchanged(self):
        old_time = time.time() - CACHE_TTL - 100
        cache = {
            "test-pkg": {
                "version": "1.0.0",
                "last_fetched": old_time,
                "families": ["ci"],
                "patterns": [SAMPLE_PATTERN],
            }
        }
        _save_cache(cache)

        with patch("evolution.pattern_registry.check_pypi_version", return_value="1.0.0"):
            result = _get_cached_or_fetch("test-pkg")
        assert result["last_fetched"] > old_time


# ─── _download_and_extract_patterns ───


class TestDownloadAndExtract:
    def test_extracts_patterns_from_wheel(self):
        wheel_data = _make_wheel_bytes([SAMPLE_PATTERN])
        resp = MagicMock()
        resp.read.return_value = wheel_data
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("evolution.pattern_registry.urllib.request.urlopen", return_value=resp):
            result = _download_and_extract_patterns("https://example.com/pkg.whl", "test-pkg")

        assert result is not None
        assert len(result) == 1
        assert result[0]["fingerprint"] == "3aab010d317b22df"

    def test_returns_none_for_empty_wheel(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("other_file.txt", "hello")

        resp = MagicMock()
        resp.read.return_value = buf.getvalue()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("evolution.pattern_registry.urllib.request.urlopen", return_value=resp):
            result = _download_and_extract_patterns("https://example.com/pkg.whl", "test-pkg")

        assert result is None

    def test_rejects_oversized_download(self):
        resp = MagicMock()
        resp.read.return_value = b"x" * (11 * 1024 * 1024)  # 11MB
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("evolution.pattern_registry.urllib.request.urlopen", return_value=resp):
            result = _download_and_extract_patterns("https://example.com/pkg.whl", "test-pkg")

        assert result is None

    def test_handles_patterns_as_dict_with_key(self):
        patterns_data = {"patterns": [SAMPLE_PATTERN]}
        wheel_data = _make_wheel_bytes(patterns_data)
        # Need to rebuild because _make_wheel_bytes expects a list
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("evo_patterns_test/patterns.json", json.dumps(patterns_data))

        resp = MagicMock()
        resp.read.return_value = buf.getvalue()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("evolution.pattern_registry.urllib.request.urlopen", return_value=resp):
            result = _download_and_extract_patterns("https://example.com/pkg.whl", "test-pkg")

        assert result is not None
        assert len(result) == 1


# ─── fetch_available_patterns ───


class TestFetchAvailablePatterns:
    def test_returns_empty_when_no_packages(self, monkeypatch):
        monkeypatch.setattr(
            "evolution.pattern_registry._load_pattern_index", lambda: []
        )
        result = fetch_available_patterns(["ci", "git"])
        assert result == []

    def test_filters_blocked_packages(self, monkeypatch):
        monkeypatch.setattr(
            "evolution.pattern_registry._load_pattern_index",
            lambda: ["evo-patterns-test"],
        )
        monkeypatch.setattr(
            "evolution.pattern_registry._load_blocklist",
            lambda: {"evo-patterns-test"},
        )
        result = fetch_available_patterns(["ci", "git"])
        assert result == []

    def test_returns_cached_patterns(self):
        cache = {
            "evo-patterns-example": {
                "version": "1.0.0",
                "last_fetched": time.time(),
                "families": ["ci", "git"],
                "patterns": [SAMPLE_PATTERN],
            }
        }
        _save_cache(cache)

        result = fetch_available_patterns(["ci", "git"])
        assert len(result) == 1

    def test_filters_by_family(self):
        cache = {
            "evo-patterns-example": {
                "version": "1.0.0",
                "last_fetched": time.time(),
                "families": ["ci", "git", "dependency"],
                "patterns": [SAMPLE_PATTERN, SAMPLE_PATTERN_DEP],
            }
        }
        _save_cache(cache)

        result = fetch_available_patterns(["deployment"])
        assert len(result) == 0


# ─── User Source Management ───


class TestUserSources:
    def test_add_source(self):
        assert add_pattern_source("evo-patterns-new") is True
        assert add_pattern_source("evo-patterns-new") is False  # already added

    def test_remove_source(self):
        add_pattern_source("evo-patterns-new")
        assert remove_pattern_source("evo-patterns-new") is True
        assert remove_pattern_source("evo-patterns-new") is False  # already removed


# ─── Blocklist Management ───


class TestBlocklist:
    def test_block_package(self):
        assert block_pattern_package("bad-pkg", reason="test") is True
        assert block_pattern_package("bad-pkg") is False  # already blocked

    def test_unblock_package(self):
        block_pattern_package("bad-pkg")
        assert unblock_pattern_package("bad-pkg") is True
        assert unblock_pattern_package("bad-pkg") is False  # not blocked

    def test_block_removes_from_cache(self):
        cache = {"bad-pkg": {"version": "1.0.0", "last_fetched": time.time()}}
        _save_cache(cache)

        block_pattern_package("bad-pkg")
        loaded = _load_cache()
        assert "bad-pkg" not in loaded


# ─── list_pattern_packages ───


class TestListPatternPackages:
    def test_lists_bundled_packages(self):
        packages = list_pattern_packages()
        assert isinstance(packages, list)
        # Should include the bundled evo-patterns-example
        names = [p["name"] for p in packages]
        assert "evo-patterns-example" in names

    def test_includes_cache_info(self):
        cache = {
            "evo-patterns-example": {
                "version": "1.0.0",
                "last_fetched": time.time(),
                "families": ["ci", "git"],
                "patterns": [SAMPLE_PATTERN],
            }
        }
        _save_cache(cache)

        packages = list_pattern_packages()
        pkg = next(p for p in packages if p["name"] == "evo-patterns-example")
        assert pkg["cached_version"] == "1.0.0"
        assert pkg["pattern_count"] == 1
