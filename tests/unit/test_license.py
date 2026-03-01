"""
Tests for the license system (evolution/license.py).
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from evolution.license import (
    License,
    ProFeatureError,
    _apply_heartbeat,
    _compute_activation_token,
    _get_heartbeat_path,
    _get_signing_key,
    _read_heartbeat_cache,
    _validate_activation,
    _validate_key,
    _write_heartbeat_cache,
    activate_license,
    generate_key,
    get_license,
    is_pro,
    require_pro,
)

# Test-only signing key (never used in production)
_TEST_KEY = b"test-signing-key-for-unit-tests"


class TestLicenseDetection:
    """Test license detection from various sources."""

    def test_default_is_free_tier(self, tmp_path, monkeypatch):
        """No license key should default to free tier."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        lic = get_license()

        assert lic.tier == "free"
        assert lic.valid is True
        assert lic.source == "default"
        assert not lic.is_pro()

    def test_pro_trial_env_var(self, monkeypatch):
        """EVO_LICENSE_KEY=pro-trial should grant Pro tier (in pytest)."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")
        lic = get_license()

        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.source == "trial"
        assert lic.is_pro()

    def test_signed_key_via_env_var(self, monkeypatch):
        """Valid signed key via env var should grant Pro tier."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", _TEST_KEY.decode())
        key = generate_key("pro", "test@example.com", signing_key=_TEST_KEY)
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()

        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.source == "env"
        assert lic.email is not None  # email_hash present
        assert lic.is_pro()

    def test_invalid_key_falls_back_to_free(self, tmp_path, monkeypatch):
        """Invalid key should fall back to free tier."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "invalid-key-123")
        monkeypatch.setenv("HOME", str(tmp_path))
        lic = get_license()

        assert lic.tier == "free"
        assert lic.valid is True
        assert lic.source == "default"
        assert not lic.is_pro()

    def test_license_file_home_directory(self, tmp_path, monkeypatch):
        """License from ~/.evo/license.json should be detected."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)

        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        evo_dir = fake_home / ".evo"
        evo_dir.mkdir()
        license_file = evo_dir / "license.json"
        license_file.write_text(json.dumps({"license_key": "pro-trial"}))

        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.source == "trial"
        assert lic.is_pro()

    def test_license_file_repo_directory(self, tmp_path, monkeypatch):
        """License from <repo>/.evo/license.json should be detected."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        repo_dir = tmp_path / "repo"
        evo_dir = repo_dir / ".evo"
        evo_dir.mkdir(parents=True)
        license_file = evo_dir / "license.json"
        license_file.write_text(json.dumps({"license_key": "pro-trial"}))

        lic = get_license(str(repo_dir))
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.is_pro()

    def test_env_var_takes_precedence(self, tmp_path, monkeypatch):
        """Env var should take precedence over file."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")

        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        evo_dir = fake_home / ".evo"
        evo_dir.mkdir()
        license_file = evo_dir / "license.json"
        license_file.write_text(json.dumps({"license_key": "invalid"}))

        lic = get_license()
        assert lic.tier == "pro"  # from env var
        assert lic.source == "trial"


class TestActivatedLicense:
    """Test server-activated license file validation."""

    def test_activated_license_detected(self, tmp_path, monkeypatch):
        """Activated license with valid token should be detected."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)

        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        key = "some-base64-key"
        tier = "pro"
        email_hash = "abc123def456"
        issued = "2026-02-28T10:00:00"
        token = _compute_activation_token(key, tier, email_hash, issued)

        evo_dir = fake_home / ".evo"
        evo_dir.mkdir()
        license_file = evo_dir / "license.json"
        license_file.write_text(json.dumps({
            "license_key": key,
            "tier": tier,
            "email_hash": email_hash,
            "issued": issued,
            "activation_token": token,
        }))

        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.source == "activated"
        assert lic.is_pro()

    def test_tampered_activation_rejected(self, tmp_path, monkeypatch):
        """Activation with wrong token should be rejected."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)

        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        evo_dir = fake_home / ".evo"
        evo_dir.mkdir()
        license_file = evo_dir / "license.json"
        license_file.write_text(json.dumps({
            "license_key": "some-key",
            "tier": "pro",
            "email_hash": "abc123",
            "issued": "2026-02-28T10:00:00",
            "activation_token": "tampered-wrong-token-value-here",
        }))

        lic = get_license()
        assert lic.tier == "free"
        assert lic.source == "default"

    def test_activation_token_computation(self):
        """Activation token should be deterministic."""
        token1 = _compute_activation_token("key", "pro", "hash", "2026-01-01")
        token2 = _compute_activation_token("key", "pro", "hash", "2026-01-01")
        assert token1 == token2
        assert len(token1) == 32

        # Different inputs → different tokens
        token3 = _compute_activation_token("key2", "pro", "hash", "2026-01-01")
        assert token1 != token3


class TestProFeatureGating:
    """Test Pro feature gating functions."""

    def test_is_pro_returns_false_for_free(self, tmp_path, monkeypatch):
        """is_pro() should return False for free tier."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert is_pro() is False

    def test_is_pro_returns_true_for_pro(self, monkeypatch):
        """is_pro() should return True for Pro tier."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")
        assert is_pro() is True

    def test_require_pro_raises_for_free(self, tmp_path, monkeypatch):
        """require_pro() should raise ProFeatureError for free tier."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))

        with pytest.raises(ProFeatureError) as exc_info:
            require_pro("Test Feature")

        assert "Test Feature" in str(exc_info.value)
        assert "Evolution Engine Pro" in str(exc_info.value)
        assert "https://codequal.dev/#pricing" in str(exc_info.value)

    def test_require_pro_passes_for_pro(self, monkeypatch):
        """require_pro() should not raise for Pro tier."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")
        require_pro("Test Feature")


class TestLicenseFeatures:
    """Test License.features property."""

    def test_free_tier_features(self, tmp_path, monkeypatch):
        """Free tier should have limited features."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        lic = get_license()

        assert lic.features["tier1_adapters"] is True
        assert lic.features["tier2_adapters"] is False
        assert lic.features["llm_explanations"] is False
        assert lic.features["llm_patterns"] is False
        assert lic.features["local_kb"] is True
        assert lic.features["community_sync"] is False

    def test_pro_tier_features(self, monkeypatch):
        """Pro tier should have all features."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")
        lic = get_license()

        assert lic.features["tier1_adapters"] is True
        assert lic.features["tier2_adapters"] is True
        assert lic.features["llm_explanations"] is True
        assert lic.features["llm_patterns"] is True
        assert lic.features["local_kb"] is True
        assert lic.features["community_sync"] is True


class TestKeyGeneration:
    """Test signed key generation and validation."""

    def test_generate_and_validate_key(self, monkeypatch):
        """Generated key should validate correctly."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", _TEST_KEY.decode())
        key = generate_key("pro", "user@example.com", signing_key=_TEST_KEY)
        assert isinstance(key, str)
        assert len(key) > 0

        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()

        assert lic.tier == "pro"
        assert lic.email is not None
        assert lic.valid is True

    def test_tampered_key_is_invalid(self, tmp_path, monkeypatch):
        """Tampered key should be rejected."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", _TEST_KEY.decode())
        key = generate_key("pro", "user@example.com", signing_key=_TEST_KEY)
        tampered = key[:-5] + "XXXXX"
        monkeypatch.setenv("EVO_LICENSE_KEY", tampered)
        monkeypatch.setenv("HOME", str(tmp_path))

        lic = get_license()
        assert lic.tier == "free"
        assert lic.source == "default"

    def test_expired_key_is_invalid(self, tmp_path, monkeypatch):
        """Expired key should be rejected."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", _TEST_KEY.decode())
        key = generate_key("pro", "user@example.com", signing_key=_TEST_KEY, expires="2020-01-01")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        monkeypatch.setenv("HOME", str(tmp_path))

        lic = get_license()
        assert lic.tier == "free"
        assert lic.source == "default"

    def test_future_expiry_is_valid(self, monkeypatch):
        """Key with future expiry should be valid."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", _TEST_KEY.decode())
        key = generate_key("pro", "user@example.com", signing_key=_TEST_KEY, expires="2099-12-31")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)

        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.expires == "2099-12-31"

    def test_generate_key_requires_signing_key(self):
        """generate_key() should require an explicit signing_key."""
        import inspect
        sig = inspect.signature(generate_key)
        # signing_key must be a required parameter (no default)
        param = sig.parameters["signing_key"]
        assert param.default is inspect.Parameter.empty


class TestSigningKeyConfig:
    """Test configurable signing key."""

    def test_no_key_returns_none_for_pure_python(self, monkeypatch):
        """Without env var or embedded key, _get_signing_key should return None."""
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)
        # In pure-Python installs, placeholder stays → returns None
        result = _get_signing_key()
        # Result is None (placeholder) or bytes (if embedded key is present)
        assert result is None or isinstance(result, bytes)

    def test_custom_signing_key_works(self, monkeypatch):
        """Custom signing key should generate valid keys."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", "my-production-secret-key")
        key = generate_key("pro", "user@example.com", signing_key=b"my-production-secret-key")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.email is not None

    def test_mismatched_key_rejects(self, monkeypatch):
        """Key generated with one signing key should not validate with another."""
        key = generate_key("pro", "user@example.com", signing_key=b"key-one")
        # Validate with different signing key
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", "key-two")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()
        assert lic.tier == "free"
        assert lic.source == "default"

    def test_env_signing_key_returns_bytes(self, monkeypatch):
        """_get_signing_key with env var should return bytes."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", "custom-key")
        assert isinstance(_get_signing_key(), bytes)
        assert _get_signing_key() == b"custom-key"


class TestActivation:
    """Test the license activation flow."""

    def test_activate_with_local_key(self, tmp_path, monkeypatch):
        """Activation should work locally when signing key is available."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", _TEST_KEY.decode())
        key = generate_key("pro", "test@example.com", signing_key=_TEST_KEY)

        result = activate_license(key)
        assert result["success"] is True
        assert result["tier"] == "pro"
        assert result["source"] == "local"

        # Verify file was written
        license_file = tmp_path / ".evo" / "license.json"
        assert license_file.exists()
        data = json.loads(license_file.read_text())
        assert data["tier"] == "pro"
        assert "activation_token" in data

    def test_activate_saves_valid_activation(self, tmp_path, monkeypatch):
        """After activation, get_license should detect the activated license."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", _TEST_KEY.decode())
        key = generate_key("pro", "test@example.com", signing_key=_TEST_KEY)

        activate_license(key)

        # Now clear the signing key — should still work via activation token
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)
        lic = get_license()
        assert lic.tier == "pro"
        assert lic.source == "activated"
        assert lic.is_pro()

    def test_activate_server_fallback(self, tmp_path, monkeypatch):
        """Without signing key, activation should attempt server call."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)

        # Mock the server call
        result = activate_license("fake-key", server_url="http://invalid.test/api/activate-license")
        assert result["success"] is False
        assert "error" in result


class TestValidateActivation:
    """Test _validate_activation integrity checking."""

    def test_valid_activation_data(self):
        """Valid activation data should pass."""
        key = "test-key"
        tier = "pro"
        email_hash = "abc123"
        issued = "2026-01-01"
        token = _compute_activation_token(key, tier, email_hash, issued)

        data = {
            "license_key": key,
            "tier": tier,
            "email_hash": email_hash,
            "issued": issued,
            "activation_token": token,
        }
        result = _validate_activation(data)
        assert result is not None
        assert result["tier"] == "pro"

    def test_missing_fields_rejected(self):
        """Activation data with missing fields should be rejected."""
        assert _validate_activation({}) is None
        assert _validate_activation({"license_key": "x"}) is None
        assert _validate_activation({"license_key": "x", "tier": "pro"}) is None

    def test_wrong_token_rejected(self):
        """Wrong activation token should be rejected."""
        data = {
            "license_key": "key",
            "tier": "pro",
            "email_hash": "hash",
            "issued": "2026-01-01",
            "activation_token": "wrong-token-value-here-tampered",
        }
        assert _validate_activation(data) is None


class TestProFeatureError:
    """Test ProFeatureError exception."""

    def test_error_message_format(self):
        """Error message should be helpful."""
        err = ProFeatureError("CI Adapters")

        assert "CI Adapters" in str(err)
        assert "Evolution Engine Pro" in str(err)
        assert "https://codequal.dev/#pricing" in str(err)
        assert err.feature_name == "CI Adapters"


class TestHeartbeat:
    """Test server-side license heartbeat verification."""

    @pytest.fixture(autouse=True)
    def setup_home(self, tmp_path, monkeypatch):
        """Isolate heartbeat cache to tmp_path."""
        self.home = tmp_path / "home"
        self.home.mkdir()
        monkeypatch.setenv("HOME", str(self.home))
        # Ensure .evo directory exists
        (self.home / ".evo").mkdir()

    def _pro_license(self):
        return License(tier="pro", valid=True, source="env")

    def _free_license(self):
        return License(tier="free", valid=True, source="default")

    def test_heartbeat_skipped_for_free_tier(self):
        """Heartbeat should not affect free tier licenses."""
        lic = self._free_license()
        result = _apply_heartbeat(lic, "any-key")
        assert result.tier == "free"

    def test_heartbeat_skipped_in_test_env(self):
        """Heartbeat should be skipped in test environments."""
        lic = self._pro_license()
        # We're running in pytest, so _is_test_environment() returns True
        result = _apply_heartbeat(lic, "any-key")
        assert result.tier == "pro"  # unchanged, heartbeat skipped

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value="active")
    def test_heartbeat_active_keeps_pro(self, mock_check, mock_test):
        """Active subscription should keep Pro tier."""
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "pro"
        mock_check.assert_called_once_with("some-key")

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value="cancelled")
    def test_heartbeat_cancelled_degrades_to_free(self, mock_check, mock_test):
        """Cancelled subscription should degrade to free tier."""
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "free"
        assert "cancelled" in (result.error or "")

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value="revoked")
    def test_heartbeat_revoked_degrades_to_free(self, mock_check, mock_test):
        """Revoked license should degrade to free tier."""
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "free"
        assert "revoked" in (result.error or "")

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value="past_due")
    def test_heartbeat_past_due_within_grace(self, mock_check, mock_test):
        """Past-due within grace period should keep Pro."""
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "pro"  # within 14-day grace

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value="past_due")
    def test_heartbeat_past_due_after_grace_degrades(self, mock_check, mock_test):
        """Past-due beyond grace period should degrade to free."""
        # Pre-set a grace_start that's 20 days ago
        _write_heartbeat_cache({
            "status": "past_due",
            "last_checked": (datetime.now() - timedelta(days=8)).isoformat(),
            "last_success": (datetime.now() - timedelta(days=20)).isoformat(),
            "grace_start": (datetime.now() - timedelta(days=20)).isoformat(),
        })
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "free"
        assert "past due" in (result.error or "").lower()

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value="active")
    def test_heartbeat_uses_cache_within_interval(self, mock_check, mock_test):
        """Recent heartbeat should use cache, not call server."""
        _write_heartbeat_cache({
            "status": "active",
            "last_checked": datetime.now().isoformat(),
            "last_success": datetime.now().isoformat(),
        })
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "pro"
        mock_check.assert_not_called()  # should use cache

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value=None)
    def test_heartbeat_network_failure_within_grace(self, mock_check, mock_test):
        """Network failure within grace period should keep Pro."""
        _write_heartbeat_cache({
            "status": "active",
            "last_checked": (datetime.now() - timedelta(days=8)).isoformat(),
            "last_success": (datetime.now() - timedelta(days=8)).isoformat(),
        })
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "pro"  # 8 days < 14 day grace

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value=None)
    def test_heartbeat_network_failure_beyond_grace(self, mock_check, mock_test):
        """Network failure beyond grace period should degrade."""
        _write_heartbeat_cache({
            "status": "active",
            "last_checked": (datetime.now() - timedelta(days=20)).isoformat(),
            "last_success": (datetime.now() - timedelta(days=20)).isoformat(),
        })
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "free"
        assert "grace period" in (result.error or "").lower()

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value=None)
    def test_heartbeat_no_cache_network_failure_allows(self, mock_check, mock_test):
        """First-ever heartbeat with network failure should allow Pro (new user)."""
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "pro"  # no previous check → allow

    @patch("evolution.license._is_test_environment", return_value=False)
    def test_heartbeat_respects_do_not_track(self, mock_test, monkeypatch):
        """DO_NOT_TRACK=1 should skip heartbeat entirely."""
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "pro"  # no check performed

    def test_heartbeat_cache_read_write(self):
        """Heartbeat cache should round-trip correctly."""
        data = {"status": "active", "last_checked": "2026-02-28T12:00:00"}
        _write_heartbeat_cache(data)
        result = _read_heartbeat_cache()
        assert result["status"] == "active"
        assert result["last_checked"] == "2026-02-28T12:00:00"

    def test_heartbeat_cache_empty_when_missing(self):
        """Missing cache file should return empty dict."""
        # Remove the file if it exists
        path = _get_heartbeat_path()
        if path.exists():
            path.unlink()
        result = _read_heartbeat_cache()
        assert result == {}

    @patch("evolution.license._is_test_environment", return_value=False)
    @patch("evolution.license._heartbeat_check", return_value="cancelled")
    def test_cached_cancelled_degrades_without_server_call(self, mock_check, mock_test):
        """Cached 'cancelled' status should degrade without calling server."""
        _write_heartbeat_cache({
            "status": "cancelled",
            "last_checked": datetime.now().isoformat(),
            "last_success": datetime.now().isoformat(),
        })
        lic = self._pro_license()
        result = _apply_heartbeat(lic, "some-key")
        assert result.tier == "free"
        mock_check.assert_not_called()  # should use cache
