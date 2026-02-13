"""
Unit tests for adapter version checking (evolution/adapter_versions.py).

All network calls are mocked to avoid real PyPI requests during tests.
"""

import json
import time
from unittest.mock import patch, MagicMock

import pytest

from evolution.adapter_versions import (
    check_pypi_version,
    check_all_updates,
    check_self_update_nudge,
    _load_cache,
    _save_cache,
    _cache_path,
    CACHE_TTL_SECONDS,
)


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """Redirect cache to tmp_path for test isolation."""
    cache_file = tmp_path / "version_cache.json"
    monkeypatch.setattr("evolution.adapter_versions._cache_path", lambda: cache_file)
    return cache_file


@pytest.fixture
def mock_urlopen():
    """Mock urllib.request.urlopen to return fake PyPI data."""
    def _make_mock(version="1.2.3"):
        resp = MagicMock()
        resp.read.return_value = json.dumps({
            "info": {"version": version}
        }).encode("utf-8")
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp
    return _make_mock


# ─── check_pypi_version ───


class TestCheckPypiVersion:
    def test_returns_version_from_pypi(self, mock_urlopen):
        resp = mock_urlopen("2.0.0")
        with patch("evolution.adapter_versions.urllib.request.urlopen", return_value=resp):
            version = check_pypi_version("some-package", use_cache=False)
        assert version == "2.0.0"

    def test_returns_none_on_network_error(self):
        import urllib.error
        with patch("evolution.adapter_versions.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("timeout")):
            version = check_pypi_version("some-package", use_cache=False)
        assert version is None

    def test_uses_cache_when_fresh(self, isolate_cache, mock_urlopen):
        # Pre-populate cache
        _save_cache({
            "cached-pkg": {
                "latest_version": "1.0.0",
                "checked_at": time.time(),
            }
        })
        # Should not hit network
        version = check_pypi_version("cached-pkg", use_cache=True)
        assert version == "1.0.0"

    def test_ignores_stale_cache(self, isolate_cache, mock_urlopen):
        # Pre-populate with old cache
        _save_cache({
            "old-pkg": {
                "latest_version": "0.9.0",
                "checked_at": time.time() - CACHE_TTL_SECONDS - 1,
            }
        })
        resp = mock_urlopen("1.0.0")
        with patch("evolution.adapter_versions.urllib.request.urlopen", return_value=resp):
            version = check_pypi_version("old-pkg", use_cache=True)
        assert version == "1.0.0"

    def test_updates_cache_after_fetch(self, isolate_cache, mock_urlopen):
        resp = mock_urlopen("3.0.0")
        with patch("evolution.adapter_versions.urllib.request.urlopen", return_value=resp):
            check_pypi_version("new-pkg", use_cache=False)
        cache = _load_cache()
        assert cache["new-pkg"]["latest_version"] == "3.0.0"


# ─── check_all_updates ───


class TestCheckAllUpdates:
    def test_returns_updates_when_newer(self, mock_urlopen):
        resp = mock_urlopen("2.0.0")
        with patch("evolution.adapter_versions.urllib.request.urlopen", return_value=resp):
            updates = check_all_updates({"pkg-a": "1.0.0"}, use_cache=False)
        assert len(updates) == 1
        assert updates[0]["name"] == "pkg-a"
        assert updates[0]["current"] == "1.0.0"
        assert updates[0]["latest"] == "2.0.0"

    def test_returns_empty_when_up_to_date(self, mock_urlopen):
        resp = mock_urlopen("1.0.0")
        with patch("evolution.adapter_versions.urllib.request.urlopen", return_value=resp):
            updates = check_all_updates({"pkg-a": "1.0.0"}, use_cache=False)
        assert len(updates) == 0

    def test_returns_empty_on_network_failure(self):
        import urllib.error
        with patch("evolution.adapter_versions.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("timeout")):
            updates = check_all_updates({"pkg-a": "1.0.0"}, use_cache=False)
        assert len(updates) == 0


# ─── check_self_update_nudge ───


class TestCheckSelfUpdateNudge:
    def test_returns_nudge_when_update_available(self, tmp_path, monkeypatch, mock_urlopen):
        # Mock config to isolated path
        monkeypatch.setattr("evolution.adapter_versions.EvoConfig",
                            lambda: _make_config(tmp_path, check_updates=True))
        resp = mock_urlopen("99.0.0")
        with patch("evolution.adapter_versions.urllib.request.urlopen", return_value=resp):
            with patch("evolution.adapter_versions.__version__", "1.0.0",
                       create=True):
                # Patch at the import site
                import evolution.adapter_versions
                old = getattr(evolution.adapter_versions, '__version__', None)
                with patch("evolution.__version__", "1.0.0"):
                    result = check_self_update_nudge(use_cache=False)
        assert result is not None
        assert "99.0.0" in result

    def test_returns_none_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr("evolution.adapter_versions.EvoConfig",
                            lambda: _make_config(tmp_path, check_updates=False))
        result = check_self_update_nudge()
        assert result is None


def _make_config(tmp_path, check_updates=True):
    """Create a mock EvoConfig for testing."""
    from evolution.config import EvoConfig
    cfg = EvoConfig(path=tmp_path / "config.toml")
    cfg.set("adapter.check_updates", check_updates)
    cfg.set("adapter.last_version_check", "")
    return cfg
