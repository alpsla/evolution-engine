"""Tests for the notification system."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.notifications import (
    TYPE_ADAPTER_AVAILABLE,
    TYPE_ADAPTER_UPDATE,
    _add_notification,
    _load_notifications,
    _prune_expired,
    _save_notifications,
    _should_check,
    check_adapter_discovery,
    check_adapter_updates,
    check_and_notify,
    dismiss,
    dismiss_all,
    format_notifications,
    get_pending,
    EXPIRY_SECONDS,
)


# ─── Helpers ───


@pytest.fixture
def notification_file(tmp_path, monkeypatch):
    """Redirect notification file to temp directory."""
    nf = tmp_path / "notifications.json"
    monkeypatch.setattr("evolution.notifications.NOTIFICATION_FILE", nf)
    return nf


# ─── Load/Save ───


def test_load_empty(notification_file):
    """Loading when no file exists returns empty state."""
    state = _load_notifications()
    assert state["last_check"] == 0
    assert state["items"] == []


def test_save_and_load(notification_file):
    """Save and reload preserves state."""
    state = {"last_check": 123.0, "items": [
        {"type": "test", "key": "k1", "message": "hello", "created_at": 100, "dismissed": False},
    ]}
    _save_notifications(state)
    loaded = _load_notifications()
    assert loaded["last_check"] == 123.0
    assert len(loaded["items"]) == 1
    assert loaded["items"][0]["key"] == "k1"


def test_load_corrupt_file(notification_file):
    """Corrupt JSON returns empty state."""
    notification_file.write_text("not json{{{")
    state = _load_notifications()
    assert state["items"] == []


# ─── Prune Expired ───


def test_prune_removes_old():
    """Expired notifications are pruned."""
    now = time.time()
    state = {"last_check": 0, "items": [
        {"key": "old", "created_at": now - EXPIRY_SECONDS - 1, "dismissed": False},
        {"key": "new", "created_at": now - 100, "dismissed": False},
    ]}
    pruned = _prune_expired(state)
    assert len(pruned["items"]) == 1
    assert pruned["items"][0]["key"] == "new"


def test_prune_keeps_fresh():
    """Fresh notifications survive pruning."""
    now = time.time()
    state = {"last_check": 0, "items": [
        {"key": "a", "created_at": now, "dismissed": False},
        {"key": "b", "created_at": now - 86400, "dismissed": False},
    ]}
    pruned = _prune_expired(state)
    assert len(pruned["items"]) == 2


# ─── Add Notification ───


def test_add_notification():
    """Adding a notification with unique key works."""
    state = {"items": []}
    _add_notification(state, "test", "k1", "hello")
    assert len(state["items"]) == 1
    assert state["items"][0]["key"] == "k1"
    assert state["items"][0]["message"] == "hello"


def test_add_duplicate_notification():
    """Duplicate keys are not added."""
    state = {"items": [
        {"key": "k1", "type": "test", "message": "first", "created_at": 1, "dismissed": False},
    ]}
    _add_notification(state, "test", "k1", "second")
    assert len(state["items"]) == 1
    assert state["items"][0]["message"] == "first"


# ─── Get Pending ───


def test_get_pending_filters_dismissed(notification_file):
    """get_pending() excludes dismissed notifications."""
    state = {"last_check": 0, "items": [
        {"key": "k1", "type": "t", "message": "m1", "created_at": time.time(), "dismissed": False},
        {"key": "k2", "type": "t", "message": "m2", "created_at": time.time(), "dismissed": True},
    ]}
    _save_notifications(state)
    pending = get_pending()
    assert len(pending) == 1
    assert pending[0]["key"] == "k1"


# ─── Dismiss ───


def test_dismiss_by_key(notification_file):
    """dismiss() marks specific notification as dismissed."""
    state = {"last_check": 0, "items": [
        {"key": "k1", "type": "t", "message": "m1", "created_at": time.time(), "dismissed": False},
        {"key": "k2", "type": "t", "message": "m2", "created_at": time.time(), "dismissed": False},
    ]}
    _save_notifications(state)
    dismiss("k1")
    pending = get_pending()
    assert len(pending) == 1
    assert pending[0]["key"] == "k2"


def test_dismiss_all(notification_file):
    """dismiss_all() marks all notifications as dismissed."""
    state = {"last_check": 0, "items": [
        {"key": "k1", "type": "t", "message": "m1", "created_at": time.time(), "dismissed": False},
        {"key": "k2", "type": "t", "message": "m2", "created_at": time.time(), "dismissed": False},
    ]}
    _save_notifications(state)
    dismiss_all()
    assert get_pending() == []


# ─── Should Check ───


def test_should_check_respects_interval(notification_file, monkeypatch):
    """_should_check returns False if checked recently."""
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    mock_cfg = MagicMock()
    mock_cfg.get.return_value = True
    with patch("evolution.config.EvoConfig", return_value=mock_cfg):
        state = {"last_check": time.time() - 100}  # 100s ago
        assert _should_check(state) is False

        state = {"last_check": time.time() - 90000}  # > 24h ago
        assert _should_check(state) is True


def test_should_check_respects_do_not_track(notification_file, monkeypatch):
    """_should_check returns False when DO_NOT_TRACK=1."""
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    state = {"last_check": 0}
    assert _should_check(state) is False


def test_should_check_respects_config(notification_file, monkeypatch):
    """_should_check returns False when adapter.check_updates is disabled."""
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    mock_cfg = MagicMock()
    mock_cfg.get.return_value = False  # check_updates disabled
    with patch("evolution.config.EvoConfig", return_value=mock_cfg):
        state = {"last_check": 0}
        assert _should_check(state) is False


# ─── Check Adapter Updates ───


def test_check_adapter_updates_finds_update(notification_file):
    """check_adapter_updates detects when installed plugin has newer PyPI version."""
    mock_ep = MagicMock()
    mock_ep.dist.name = "evo-adapter-test"
    mock_ep.dist.version = "0.1.0"

    mock_eps = MagicMock()
    mock_eps.select.return_value = [mock_ep]

    state = {"items": []}

    with patch("importlib.metadata.entry_points", return_value=mock_eps), \
         patch("evolution.adapter_versions.check_pypi_version", return_value="0.2.0"):
        check_adapter_updates(state)

    assert len(state["items"]) == 1
    assert "0.1.0 → 0.2.0" in state["items"][0]["message"]
    assert state["items"][0]["type"] == TYPE_ADAPTER_UPDATE


def test_check_adapter_updates_up_to_date(notification_file):
    """check_adapter_updates adds nothing when versions match."""
    mock_ep = MagicMock()
    mock_ep.dist.name = "evo-adapter-test"
    mock_ep.dist.version = "0.1.0"

    mock_eps = MagicMock()
    mock_eps.select.return_value = [mock_ep]

    state = {"items": []}

    with patch("importlib.metadata.entry_points", return_value=mock_eps), \
         patch("evolution.adapter_versions.check_pypi_version", return_value="0.1.0"):
        check_adapter_updates(state)

    assert len(state["items"]) == 0


# ─── Check Adapter Discovery ───


def test_check_adapter_discovery_finds_available(notification_file, tmp_path):
    """check_adapter_discovery finds adapters on PyPI for detected tools."""
    mock_svc = MagicMock()
    mock_svc.adapter = "evo-adapter-datadog"
    mock_svc.display_name = "Datadog"
    mock_svc.family = "monitoring"

    mock_eps = MagicMock()
    mock_eps.select.return_value = []  # no adapters installed

    state = {"items": []}

    with patch("evolution.prescan.SourcePrescan") as MockPrescan, \
         patch("importlib.metadata.entry_points", return_value=mock_eps), \
         patch("evolution.adapter_versions.check_pypi_version", return_value="1.0.0"):
        MockPrescan.return_value.scan.return_value = [mock_svc]
        check_adapter_discovery(state, repo_path=tmp_path)

    assert len(state["items"]) == 1
    assert state["items"][0]["type"] == TYPE_ADAPTER_AVAILABLE
    assert "evo-adapter-datadog" in state["items"][0]["message"]


def test_check_adapter_discovery_skips_installed(notification_file, tmp_path):
    """check_adapter_discovery skips already-installed adapters."""
    mock_svc = MagicMock()
    mock_svc.adapter = "evo-adapter-datadog"
    mock_svc.display_name = "Datadog"
    mock_svc.family = "monitoring"

    mock_ep = MagicMock()
    mock_ep.dist.name = "evo-adapter-datadog"

    mock_eps = MagicMock()
    mock_eps.select.return_value = [mock_ep]

    state = {"items": []}

    with patch("evolution.prescan.SourcePrescan") as MockPrescan, \
         patch("importlib.metadata.entry_points", return_value=mock_eps):
        MockPrescan.return_value.scan.return_value = [mock_svc]
        check_adapter_discovery(state, repo_path=tmp_path)

    assert len(state["items"]) == 0


def test_check_adapter_discovery_no_repo_path(notification_file):
    """check_adapter_discovery does nothing without repo_path."""
    state = {"items": []}
    check_adapter_discovery(state, repo_path=None)
    assert len(state["items"]) == 0


# ─── check_and_notify integration ───


def test_check_and_notify_throttled(notification_file, monkeypatch):
    """check_and_notify respects 24h throttle."""
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)

    # Pre-populate with recent check
    state = {"last_check": time.time() - 100, "items": [
        {"key": "k1", "type": "t", "message": "existing",
         "created_at": time.time(), "dismissed": False},
    ]}
    _save_notifications(state)

    mock_cfg = MagicMock()
    mock_cfg.get.return_value = True
    with patch("evolution.config.EvoConfig", return_value=mock_cfg), \
         patch("evolution.notifications.check_adapter_updates") as mock_updates:
        result = check_and_notify()
        mock_updates.assert_not_called()  # Should be throttled

    assert len(result) == 1  # Returns existing notifications


# ─── Format ───


def test_format_empty():
    """format_notifications returns empty string for no notifications."""
    assert format_notifications([]) == ""


def test_format_single():
    """format_notifications formats a single notification."""
    result = format_notifications([
        {"type": "test", "message": "Hello world", "key": "k1"},
    ])
    assert "Hello world" in result
    assert "Notifications:" in result
    assert "dismiss" in result


def test_format_multiple():
    """format_notifications formats multiple notifications."""
    result = format_notifications([
        {"type": "t1", "message": "msg1", "key": "k1"},
        {"type": "t2", "message": "msg2", "key": "k2"},
    ])
    assert "msg1" in result
    assert "msg2" in result
