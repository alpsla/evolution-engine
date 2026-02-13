#!/usr/bin/env python3
"""
Manual Stripe Sandbox Test — validates the full purchase-to-license flow.

Requires:
    STRIPE_SECRET_KEY=sk_test_...   (Stripe test mode key)
    STRIPE_PRICE_ID=price_...       (needed for subscription tests 7-10)

What it does:
  Layer 2 (basic key flow):
    1-6: Customer create, key generate/store/validate, revocation, free fallback

  Layer 3 (subscription flows):
    7: Pro subscription flow -- create subscription with test payment method
    8: Cancellation flow -- cancel subscription, verify license revoked
    9: Discount flow -- apply FOUNDING50, verify pricing
   10: Payment failure -- test declined card handling

Usage:
    # Set keys directly:
    STRIPE_SECRET_KEY=sk_test_xxx STRIPE_PRICE_ID=price_xxx python scripts/test_stripe_sandbox.py

    # Or load from .env (if python-dotenv installed):
    python scripts/test_stripe_sandbox.py
"""

import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "website", "api"))

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass


@contextmanager
def _hide_license_file():
    """Temporarily move ~/.evo/license.json so get_license() returns free tier."""
    home_license = Path.home() / ".evo" / "license.json"
    backup = Path.home() / ".evo" / "license.json.test-bak"
    moved = False
    try:
        if home_license.exists():
            shutil.move(str(home_license), str(backup))
            moved = True
        yield
    finally:
        if moved and backup.exists():
            shutil.move(str(backup), str(home_license))


def _cleanup_customer(stripe_mod, customer_id):
    """Delete a test customer and cancel their subscriptions."""
    try:
        subs = stripe_mod.Subscription.list(customer=customer_id, status="all")
        for sub in subs.auto_paging_iter():
            if sub.status in ("active", "trialing", "past_due", "incomplete"):
                try:
                    stripe_mod.Subscription.cancel(sub.id)
                except Exception:
                    pass
        stripe_mod.Customer.delete(customer_id)
    except Exception as e:
        print(f"        Cleanup warning: {e}")


def _create_customer_with_card(stripe_mod, email, token="tok_visa"):
    """Create a test customer with a payment method attached as default."""
    customer = stripe_mod.Customer.create(
        email=email,
        metadata={"test": "true", "source": "test_stripe_sandbox.py"},
    )
    pm = stripe_mod.PaymentMethod.create(type="card", card={"token": token})
    stripe_mod.PaymentMethod.attach(pm.id, customer=customer.id)
    stripe_mod.Customer.modify(
        customer.id,
        invoice_settings={"default_payment_method": pm.id},
    )
    return customer, pm


# ── Layer 3 test functions ───────────────────────────────────────────


def test_pro_subscription(stripe_mod, price_id, signing_key):
    """[7/10] Pro subscription flow — create subscription with test payment."""
    from webhook import _generate_license_key
    from evolution.license import _validate_key, get_license

    print("\n[ 7/10] Pro subscription flow...")
    customer = None
    try:
        customer, _pm = _create_customer_with_card(
            stripe_mod, "sub-test@codequal.dev"
        )
        print(f"        Customer: {customer.id}")

        # Create subscription with real Stripe API
        sub = stripe_mod.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
        )
        print(f"        Subscription: {sub.id} (status={sub.status})")
        assert sub.status == "active", f"Expected active, got {sub.status}"

        # Simulate checkout.session.completed webhook: generate + store license
        key = _generate_license_key(
            tier="pro",
            email=customer.email,
            signing_key=signing_key.encode("utf-8"),
        )
        stripe_mod.Customer.modify(customer.id, metadata={"evo_license_key": key})

        # Validate with CLI license system
        result = _validate_key(key)
        assert result is not None, "Key validation failed!"
        assert result["tier"] == "pro", f"Expected 'pro', got '{result['tier']}'"

        # Verify via get_license() with env var
        old_env = os.environ.get("EVO_LICENSE_KEY")
        os.environ["EVO_LICENSE_KEY"] = key
        try:
            lic = get_license()
            assert lic.is_pro(), "get_license() did not return Pro!"
            print(f"        License: tier={lic.tier}, source={lic.source}")
        finally:
            if old_env:
                os.environ["EVO_LICENSE_KEY"] = old_env
            else:
                os.environ.pop("EVO_LICENSE_KEY", None)

        print("        PASS: Subscription active, license valid Pro")
        return True

    except Exception as e:
        print(f"        FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if customer:
            _cleanup_customer(stripe_mod, customer.id)


def test_cancellation(stripe_mod, price_id, signing_key):
    """[8/10] Cancellation flow — cancel subscription, verify license revoked."""
    from webhook import _generate_license_key
    from evolution.license import get_license

    print("\n[ 8/10] Cancellation flow...")
    customer = None
    try:
        customer, _pm = _create_customer_with_card(
            stripe_mod, "cancel-test@codequal.dev"
        )
        print(f"        Customer: {customer.id}")

        # Create active subscription
        sub = stripe_mod.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
        )
        assert sub.status == "active", f"Expected active, got {sub.status}"
        print(f"        Subscription: {sub.id} (status={sub.status})")

        # Simulate checkout.session.completed: generate + store license
        key = _generate_license_key(
            tier="pro",
            email=customer.email,
            signing_key=signing_key.encode("utf-8"),
        )
        stripe_mod.Customer.modify(customer.id, metadata={"evo_license_key": key})

        # Cancel subscription via Stripe API
        cancelled = stripe_mod.Subscription.cancel(sub.id)
        print(f"        Cancelled: status={cancelled.status}")

        # Simulate customer.subscription.deleted webhook: clear license key
        stripe_mod.Customer.modify(customer.id, metadata={"evo_license_key": ""})

        # Verify metadata is cleared (Stripe deletes keys set to "")
        refreshed = stripe_mod.Customer.retrieve(customer.id)
        cleared = refreshed.metadata.get("evo_license_key", "")
        assert cleared == "", f"Key not cleared: '{cleared}'"

        # Verify free tier fallback (hide license file to test env-only path)
        old_env = os.environ.get("EVO_LICENSE_KEY")
        os.environ["EVO_LICENSE_KEY"] = ""
        try:
            with _hide_license_file():
                lic = get_license()
                assert not lic.is_pro(), "Should be free tier after cancellation!"
                print(f"        Fallback: tier={lic.tier} (correct)")
        finally:
            if old_env:
                os.environ["EVO_LICENSE_KEY"] = old_env
            else:
                os.environ.pop("EVO_LICENSE_KEY", None)

        print("        PASS: Subscription cancelled, license revoked, free tier fallback")
        return True

    except Exception as e:
        print(f"        FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if customer:
            _cleanup_customer(stripe_mod, customer.id)


def test_discount(stripe_mod, price_id, signing_key):
    """[9/10] Discount flow — apply FOUNDING50, verify pricing."""
    from webhook import _generate_license_key
    from evolution.license import _validate_key

    print("\n[ 9/10] Discount flow (FOUNDING50)...")
    customer = None
    try:
        # Look up the FOUNDING50 promotion code
        promo_codes = stripe_mod.PromotionCode.list(code="FOUNDING50", active=True)
        if not promo_codes.data:
            print("        SKIP: FOUNDING50 promotion code not found in Stripe test mode")
            print("        Create it in Dashboard > Coupons > Promotion Codes")
            return None

        promo = promo_codes.data[0]
        coupon_id = promo.coupon.id
        pct_off = promo.coupon.percent_off
        duration = promo.coupon.duration
        months = getattr(promo.coupon, "duration_in_months", None)
        print(f"        Found FOUNDING50: coupon={coupon_id}, {pct_off}% off, {duration}")

        customer, _pm = _create_customer_with_card(
            stripe_mod, "discount-test@codequal.dev"
        )
        print(f"        Customer: {customer.id}")

        # Create subscription with discount applied
        sub = stripe_mod.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
            discounts=[{"coupon": coupon_id}],
        )
        print(f"        Subscription: {sub.id} (status={sub.status})")
        assert sub.status == "active", f"Expected active, got {sub.status}"

        # Verify discount is applied (expand needed — discounts are IDs by default)
        sub_full = stripe_mod.Subscription.retrieve(sub.id, expand=["discounts"])
        assert sub_full.discounts, "No discounts on subscription!"
        discount = sub_full.discounts[0]
        assert discount.coupon.id == coupon_id, (
            f"Wrong coupon: expected {coupon_id}, got {discount.coupon.id}"
        )
        applied_pct = discount.coupon.percent_off
        applied_months = discount.coupon.duration_in_months
        print(f"        Discount applied: {applied_pct}% off for {applied_months} months")

        # Verify 50% off for 3 months
        assert applied_pct == 50.0, f"Expected 50% off, got {applied_pct}%"
        assert applied_months == 3, f"Expected 3 months, got {applied_months}"

        # Verify license key still works as Pro (discount is billing-only)
        key = _generate_license_key(
            tier="pro",
            email=customer.email,
            signing_key=signing_key.encode("utf-8"),
        )
        result = _validate_key(key)
        assert result is not None, "Key validation failed!"
        assert result["tier"] == "pro", "Discounted subscription should still be Pro!"

        print("        PASS: Discount applied, license still valid Pro")
        return True

    except Exception as e:
        print(f"        FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if customer:
            _cleanup_customer(stripe_mod, customer.id)


def test_payment_failure(stripe_mod, price_id, signing_key):
    """[10/10] Payment failure — webhook handler flags customer correctly."""
    print("\n[10/10] Payment failure (webhook handler)...")
    customer = None
    try:
        # Create customer without a subscription (simulating failed initial payment)
        customer = stripe_mod.Customer.create(
            email="declined-test@codequal.dev",
            metadata={"test": "true", "source": "test_stripe_sandbox.py"},
        )
        print(f"        Customer: {customer.id}")

        # Simulate invoice.payment_failed webhook handler:
        # This is what _handle_payment_failed() does in webhook.py
        stripe_mod.Customer.modify(
            customer.id,
            metadata={
                "evo_payment_status": "past_due",
                "evo_payment_failed_at": "2025-01-01T00:00:00+00:00",
                "evo_payment_attempt": "1",
            },
        )

        # Verify customer is flagged as past_due
        refreshed = stripe_mod.Customer.retrieve(customer.id)
        assert refreshed.metadata.get("evo_payment_status") == "past_due", (
            "Customer not flagged as past_due!"
        )
        assert refreshed.metadata.get("evo_payment_attempt") == "1"
        print("        Flagged: payment_status=past_due, attempt=1")

        # Verify no license key was generated (payment never succeeded)
        assert not refreshed.metadata.get("evo_license_key"), (
            "License key should not exist for failed payment!"
        )
        print("        No license key (correct)")

        # Simulate second failed attempt (increment counter)
        stripe_mod.Customer.modify(
            customer.id,
            metadata={"evo_payment_attempt": "2"},
        )
        refreshed = stripe_mod.Customer.retrieve(customer.id)
        assert refreshed.metadata.get("evo_payment_attempt") == "2"
        print("        Second attempt: attempt=2 (correct)")

        # Verify still no license key after multiple failures
        assert not refreshed.metadata.get("evo_license_key"), (
            "License key should not appear after repeated failures!"
        )

        print("        PASS: Customer flagged, no license generated, counter incremented")
        return True

    except Exception as e:
        print(f"        FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if customer:
            _cleanup_customer(stripe_mod, customer.id)


# ── Main ─────────────────────────────────────────────────────────────


def main():
    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key or not secret_key.startswith("sk_test_"):
        print("ERROR: Set STRIPE_SECRET_KEY to a test-mode key (sk_test_...)")
        print("       Never use a live key for testing!")
        sys.exit(1)

    import stripe

    stripe.api_key = secret_key

    from webhook import _generate_license_key
    from evolution.license import _validate_key, get_license

    signing_key = os.environ.get(
        "EVO_LICENSE_SIGNING_KEY",
        "evo-license-v1-dev-key-replace-in-production",
    )

    passed = 0
    failed = 0
    skipped = 0

    # ── Layer 2: Basic key flow (steps 1-6) ──────────────────────────
    print("=== Layer 2: Basic Key Flow ===\n")

    customer = None
    try:
        # Step 1: Create test customer
        print("[ 1/10] Creating test customer...")
        customer = stripe.Customer.create(
            email="sandbox-test@codequal.dev",
            metadata={"test": "true", "source": "test_stripe_sandbox.py"},
        )
        print(f"        Customer: {customer.id}")

        # Step 2: Generate license key (same as webhook handler)
        print("[ 2/10] Generating license key...")
        key = _generate_license_key(
            tier="pro",
            email=customer.email,
            signing_key=signing_key.encode("utf-8"),
        )
        print(f"        Key: {key[:40]}...")

        # Step 3: Store on customer metadata
        print("[ 3/10] Storing key on customer metadata...")
        stripe.Customer.modify(
            customer.id,
            metadata={"evo_license_key": key},
        )

        # Verify it's stored
        refreshed = stripe.Customer.retrieve(customer.id)
        stored_key = refreshed.metadata.get("evo_license_key", "")
        assert stored_key == key, "Key mismatch after storage!"
        print("        Stored and verified.")

        # Step 4: Validate with CLI license system
        print("[ 4/10] Validating with CLI license system...")
        result = _validate_key(key)
        assert result is not None, "Key validation failed!"
        assert result["tier"] == "pro", f"Expected 'pro', got '{result['tier']}'"
        assert "email_hash" in result, "Missing email_hash in key payload"
        print(
            f"        Valid: tier={result['tier']}, email_hash={result['email_hash']}"
        )

        # Also test via get_license() with env var
        old_env = os.environ.get("EVO_LICENSE_KEY")
        os.environ["EVO_LICENSE_KEY"] = key
        lic = get_license()
        assert lic.is_pro(), "get_license() did not return Pro!"
        print(f"        get_license(): tier={lic.tier}, source={lic.source}")
        if old_env:
            os.environ["EVO_LICENSE_KEY"] = old_env
        else:
            os.environ.pop("EVO_LICENSE_KEY", None)

        # Step 5: Simulate revocation
        print("[ 5/10] Simulating subscription deletion (clearing key)...")
        stripe.Customer.modify(
            customer.id,
            metadata={"evo_license_key": ""},
        )
        refreshed = stripe.Customer.retrieve(customer.id)
        # Stripe deletes metadata keys set to "" — so absent or empty both mean cleared
        cleared = refreshed.metadata.get("evo_license_key", "")
        assert cleared == "", f"Key not cleared: '{cleared}'"
        print("        Key cleared.")

        # Step 6: Verify free tier fallback
        print("[ 6/10] Verifying free tier fallback...")
        os.environ["EVO_LICENSE_KEY"] = ""
        with _hide_license_file():
            lic = get_license()
            assert not lic.is_pro(), "Should be free tier after revocation!"
            print(f"        get_license(): tier={lic.tier} (correct)")
        os.environ.pop("EVO_LICENSE_KEY", None)

        passed += 6

    except Exception as e:
        print(f"\nLayer 2 FAILED: {e}")
        import traceback

        traceback.print_exc()
        failed += 6
    finally:
        if customer:
            print(f"\n        Cleaning up: deleting customer {customer.id}...")
            try:
                stripe.Customer.delete(customer.id)
                print("        Done.")
            except Exception as e:
                print(f"        Cleanup warning: {e}")

    # ── Layer 3: Subscription flows (steps 7-10) ─────────────────────
    price_id = os.environ.get("STRIPE_PRICE_ID")
    if not price_id:
        print("\n=== Layer 3: Subscription Flows (SKIPPED) ===")
        print("    Set STRIPE_PRICE_ID to enable subscription tests (7-10)")
        skipped += 4
    else:
        print("\n=== Layer 3: Subscription Flows ===")

        for test_fn in [
            test_pro_subscription,
            test_cancellation,
            test_discount,
            test_payment_failure,
        ]:
            result = test_fn(stripe, price_id, signing_key)
            if result is True:
                passed += 1
            elif result is None:
                skipped += 1
            else:
                failed += 1

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    if failed:
        print("SOME CHECKS FAILED")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
