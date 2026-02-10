"""
Tests for the license system (evolution/license.py).
"""

import json
import os
from pathlib import Path

import pytest

from evolution.license import (
    License,
    ProFeatureError,
    _get_signing_key,
    generate_key,
    get_license,
    is_pro,
    require_pro,
)


class TestLicenseDetection:
    """Test license detection from various sources."""

    def test_default_is_free_tier(self, monkeypatch):
        """No license key should default to free tier."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        lic = get_license()

        assert lic.tier == "free"
        assert lic.valid is True
        assert lic.source == "default"
        assert not lic.is_pro()

    def test_pro_trial_env_var(self, monkeypatch):
        """EVO_LICENSE_KEY=pro-trial should grant Pro tier."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")
        lic = get_license()

        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.source == "trial"
        assert lic.is_pro()

    def test_signed_key_via_env_var(self, monkeypatch):
        """Valid signed key via env var should grant Pro tier."""
        key = generate_key("pro", "test@example.com")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()

        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.source == "env"
        assert lic.email == "test@example.com"
        assert lic.is_pro()

    def test_invalid_key_falls_back_to_free(self, monkeypatch):
        """Invalid key should fall back to free tier."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "invalid-key-123")
        lic = get_license()

        assert lic.tier == "free"
        assert lic.valid is True
        assert lic.source == "default"
        assert not lic.is_pro()

    def test_license_file_home_directory(self, tmp_path, monkeypatch):
        """License from ~/.evo/license.json should be detected."""
        # Clear env var
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)

        # Create fake home directory
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        # Write license file
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
        # Clear env var and ensure no home license
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        # Create repo with license
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
        # Set env var
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")

        # Create fake home with a different license
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        evo_dir = fake_home / ".evo"
        evo_dir.mkdir()
        license_file = evo_dir / "license.json"
        # This would be free if read, but env var takes precedence
        license_file.write_text(json.dumps({"license_key": "invalid"}))

        lic = get_license()
        assert lic.tier == "pro"  # from env var
        assert lic.source == "trial"


class TestProFeatureGating:
    """Test Pro feature gating functions."""

    def test_is_pro_returns_false_for_free(self, monkeypatch):
        """is_pro() should return False for free tier."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        assert is_pro() is False

    def test_is_pro_returns_true_for_pro(self, monkeypatch):
        """is_pro() should return True for Pro tier."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")
        assert is_pro() is True

    def test_require_pro_raises_for_free(self, monkeypatch):
        """require_pro() should raise ProFeatureError for free tier."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)

        with pytest.raises(ProFeatureError) as exc_info:
            require_pro("Test Feature")

        assert "Test Feature" in str(exc_info.value)
        assert "Evolution Engine Pro" in str(exc_info.value)
        assert "https://evo.dev/pro" in str(exc_info.value)

    def test_require_pro_passes_for_pro(self, monkeypatch):
        """require_pro() should not raise for Pro tier."""
        monkeypatch.setenv("EVO_LICENSE_KEY", "pro-trial")
        # Should not raise
        require_pro("Test Feature")


class TestLicenseFeatures:
    """Test License.features property."""

    def test_free_tier_features(self, monkeypatch):
        """Free tier should have limited features."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        lic = get_license()

        assert lic.features["tier1_adapters"] is True  # git, dependency, config
        assert lic.features["tier2_adapters"] is False  # CI, deployment, security
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

    def test_generate_and_validate_key(self):
        """Generated key should validate correctly."""
        key = generate_key("pro", "user@example.com")
        assert isinstance(key, str)
        assert len(key) > 0

        # Should validate via env var
        lic_env = os.environ.get("EVO_LICENSE_KEY")
        os.environ["EVO_LICENSE_KEY"] = key
        lic = get_license()
        if lic_env:
            os.environ["EVO_LICENSE_KEY"] = lic_env
        else:
            os.environ.pop("EVO_LICENSE_KEY", None)

        assert lic.tier == "pro"
        assert lic.email == "user@example.com"
        assert lic.valid is True

    def test_tampered_key_is_invalid(self, monkeypatch):
        """Tampered key should be rejected."""
        key = generate_key("pro", "user@example.com")
        # Tamper with the key
        tampered = key[:-5] + "XXXXX"
        monkeypatch.setenv("EVO_LICENSE_KEY", tampered)

        lic = get_license()
        assert lic.tier == "free"  # falls back to free
        assert lic.source == "default"

    def test_expired_key_is_invalid(self, monkeypatch):
        """Expired key should be rejected."""
        key = generate_key("pro", "user@example.com", expires="2020-01-01")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)

        lic = get_license()
        assert lic.tier == "free"  # falls back to free
        assert lic.source == "default"

    def test_future_expiry_is_valid(self, monkeypatch):
        """Key with future expiry should be valid."""
        key = generate_key("pro", "user@example.com", expires="2099-12-31")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)

        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.expires == "2099-12-31"


class TestSigningKeyConfig:
    """Test configurable signing key."""

    def test_default_key_backward_compatible(self, monkeypatch):
        """Default key should work the same as before."""
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)
        key = generate_key("pro", "test@example.com")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True

    def test_custom_signing_key_works(self, monkeypatch):
        """Custom signing key should generate valid keys."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", "my-production-secret-key")
        key = generate_key("pro", "user@example.com")
        # Should validate with same custom key
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.email == "user@example.com"

    def test_mismatched_key_rejects(self, monkeypatch):
        """Key generated with one signing key should not validate with another."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", "key-one")
        key = generate_key("pro", "user@example.com")
        # Switch to different signing key
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", "key-two")
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()
        assert lic.tier == "free"  # Falls back to free
        assert lic.source == "default"

    def test_get_signing_key_returns_bytes(self, monkeypatch):
        """_get_signing_key should always return bytes."""
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)
        assert isinstance(_get_signing_key(), bytes)

        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", "custom-key")
        assert isinstance(_get_signing_key(), bytes)
        assert _get_signing_key() == b"custom-key"


class TestProFeatureError:
    """Test ProFeatureError exception."""

    def test_error_message_format(self):
        """Error message should be helpful."""
        err = ProFeatureError("CI Adapters")

        assert "CI Adapters" in str(err)
        assert "Evolution Engine Pro" in str(err)
        assert "https://evo.dev/pro" in str(err)
        assert err.feature_name == "CI Adapters"
