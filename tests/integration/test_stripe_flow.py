"""
Integration tests for the Stripe purchase-to-license flow.

Tests the end-to-end chain:
  webhook._generate_license_key() → license._validate_key() → get_license() → Pro tier

All Stripe API calls are mocked — safe for CI.
"""

import os
import sys

import pytest

# Allow importing from website/api/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "website", "api"))

from evolution.license import _validate_key, generate_key, get_license

# Import webhook helpers directly from the serverless function module
from webhook import (  # website/api/webhook.py
    _generate_license_key,
    _handle_checkout_completed,
    _handle_subscription_deleted,
)


# ─── Shared fixtures ───

SIGNING_KEY = "evo-license-v1-dev-key-replace-in-production"
CUSTOM_KEY = "my-production-secret-key-2026"


class TestKeyCompatibility:
    """Verify that webhook-generated keys are accepted by the CLI license system."""

    def test_webhook_key_validates_in_cli(self):
        """Key from _generate_license_key() should pass _validate_key()."""
        key = _generate_license_key(
            tier="pro",
            email="buyer@example.com",
            signing_key=SIGNING_KEY.encode("utf-8"),
        )
        result = _validate_key(key)
        assert result is not None
        assert result["tier"] == "pro"
        assert "email_hash" in result  # email is hashed, not plaintext

    def test_webhook_key_grants_pro_via_get_license(self, monkeypatch):
        """Webhook-generated key → get_license() returns Pro tier."""
        key = _generate_license_key(
            tier="pro",
            email="buyer@example.com",
            signing_key=SIGNING_KEY.encode("utf-8"),
        )
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.email is not None  # email_hash present
        assert lic.is_pro()

    def test_custom_signing_key_consistency(self, monkeypatch):
        """Both sides using the same custom signing key should produce valid keys."""
        monkeypatch.setenv("EVO_LICENSE_SIGNING_KEY", CUSTOM_KEY)
        # Webhook side generates with custom key
        key = _generate_license_key(
            tier="pro",
            email="enterprise@corp.com",
            signing_key=CUSTOM_KEY.encode("utf-8"),
        )
        # CLI side validates with same custom key (via env var)
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        lic = get_license()
        assert lic.tier == "pro"
        assert lic.valid is True
        assert lic.email is not None  # email_hash present

    def test_mismatched_signing_key_falls_back_to_free(self, tmp_path, monkeypatch):
        """Key generated with one signing key should not validate with another."""
        # Generate with production key
        key = _generate_license_key(
            tier="pro",
            email="buyer@example.com",
            signing_key=b"production-secret",
        )
        # Validate with the default dev key (simulates mismatch)
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        monkeypatch.setenv("HOME", str(tmp_path))
        lic = get_license()
        assert lic.tier == "free"
        assert lic.source == "default"
        assert not lic.is_pro()


class TestWebhookHandlers:
    """Test the webhook handler functions with mocked Stripe API."""

    def _make_mock_stripe(self):
        """Create a mock Stripe module with Customer.retrieve/modify."""

        class _CustomerStore:
            def __init__(self):
                self.customers = {}

            def create(self, email="test@example.com"):
                cid = f"cus_test_{len(self.customers)}"
                self.customers[cid] = {
                    "id": cid,
                    "email": email,
                    "metadata": {},
                }
                return self.customers[cid]

        store = _CustomerStore()

        class MockCustomer:
            @staticmethod
            def retrieve(customer_id):
                return store.customers.get(customer_id, {
                    "id": customer_id, "email": "unknown@example.com", "metadata": {},
                })

            @staticmethod
            def modify(customer_id, **kwargs):
                if customer_id in store.customers:
                    if "metadata" in kwargs:
                        store.customers[customer_id]["metadata"].update(kwargs["metadata"])
                return store.customers.get(customer_id)

        class MockStripe:
            Customer = MockCustomer

        return MockStripe(), store

    def test_checkout_completed_stores_valid_key(self):
        """_handle_checkout_completed should store a valid license key on Customer."""
        mock_stripe, store = self._make_mock_stripe()
        customer = store.create(email="buyer@example.com")
        cid = customer["id"]

        _handle_checkout_completed(mock_stripe, cid, SIGNING_KEY)

        # Key should be stored in metadata
        key = store.customers[cid]["metadata"]["evo_license_key"]
        assert key  # non-empty
        # Key should validate
        result = _validate_key(key)
        assert result is not None
        assert result["tier"] == "pro"
        assert "email_hash" in result  # email is hashed, not plaintext

    def test_checkout_completed_is_idempotent(self):
        """Second call to _handle_checkout_completed should not overwrite existing key."""
        mock_stripe, store = self._make_mock_stripe()
        customer = store.create(email="buyer@example.com")
        cid = customer["id"]

        _handle_checkout_completed(mock_stripe, cid, SIGNING_KEY)
        first_key = store.customers[cid]["metadata"]["evo_license_key"]

        _handle_checkout_completed(mock_stripe, cid, SIGNING_KEY)
        second_key = store.customers[cid]["metadata"]["evo_license_key"]

        assert first_key == second_key  # unchanged

    def test_subscription_deleted_clears_key(self):
        """_handle_subscription_deleted should clear the license key."""
        mock_stripe, store = self._make_mock_stripe()
        customer = store.create(email="buyer@example.com")
        cid = customer["id"]

        # First grant a license
        _handle_checkout_completed(mock_stripe, cid, SIGNING_KEY)
        assert store.customers[cid]["metadata"]["evo_license_key"]

        # Then revoke
        _handle_subscription_deleted(mock_stripe, cid)
        assert store.customers[cid]["metadata"]["evo_license_key"] == ""

    def test_cleared_key_falls_back_to_free(self, tmp_path, monkeypatch):
        """After subscription deletion, the cleared key should yield free tier."""
        mock_stripe, store = self._make_mock_stripe()
        customer = store.create(email="buyer@example.com")
        cid = customer["id"]

        _handle_checkout_completed(mock_stripe, cid, SIGNING_KEY)
        key = store.customers[cid]["metadata"]["evo_license_key"]

        # Verify it was Pro
        monkeypatch.delenv("EVO_LICENSE_SIGNING_KEY", raising=False)
        monkeypatch.setenv("EVO_LICENSE_KEY", key)
        assert get_license().is_pro()

        # Revoke and try empty key
        _handle_subscription_deleted(mock_stripe, cid)
        cleared = store.customers[cid]["metadata"]["evo_license_key"]
        monkeypatch.setenv("EVO_LICENSE_KEY", cleared)
        monkeypatch.setenv("HOME", str(tmp_path))
        lic = get_license()
        assert lic.tier == "free"
        assert not lic.is_pro()
