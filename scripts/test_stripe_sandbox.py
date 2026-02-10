#!/usr/bin/env python3
"""
Manual Stripe Sandbox Test — validates the full purchase-to-license flow.

Requires:
    STRIPE_SECRET_KEY=sk_test_...   (Stripe test mode key)

What it does:
  1. Creates a test Customer
  2. Generates a license key (same as webhook handler)
  3. Stores it on Customer metadata
  4. Validates the key with the CLI license system
  5. Simulates revocation (clears key)
  6. Verifies free tier fallback
  7. Cleans up the test Customer

Usage:
    STRIPE_SECRET_KEY=sk_test_xxx python scripts/test_stripe_sandbox.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "website", "api"))


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

    customer = None
    try:
        # Step 1: Create test customer
        print("[1/6] Creating test customer...")
        customer = stripe.Customer.create(
            email="sandbox-test@codequal.dev",
            metadata={"test": "true", "source": "test_stripe_sandbox.py"},
        )
        print(f"      Customer: {customer.id}")

        # Step 2: Generate license key (same as webhook handler)
        print("[2/6] Generating license key...")
        key = _generate_license_key(
            tier="pro",
            email=customer.email,
            signing_key=signing_key.encode("utf-8"),
        )
        print(f"      Key: {key[:40]}...")

        # Step 3: Store on customer metadata
        print("[3/6] Storing key on customer metadata...")
        stripe.Customer.modify(
            customer.id,
            metadata={"evo_license_key": key},
        )

        # Verify it's stored
        refreshed = stripe.Customer.retrieve(customer.id)
        stored_key = refreshed.metadata.get("evo_license_key", "")
        assert stored_key == key, "Key mismatch after storage!"
        print("      Stored and verified.")

        # Step 4: Validate with CLI license system
        print("[4/6] Validating with CLI license system...")
        result = _validate_key(key)
        assert result is not None, "Key validation failed!"
        assert result["tier"] == "pro", f"Expected 'pro', got '{result['tier']}'"
        assert result["email"] == customer.email
        print(f"      Valid: tier={result['tier']}, email={result['email']}")

        # Also test via get_license() with env var
        old_env = os.environ.get("EVO_LICENSE_KEY")
        os.environ["EVO_LICENSE_KEY"] = key
        lic = get_license()
        assert lic.is_pro(), "get_license() did not return Pro!"
        print(f"      get_license(): tier={lic.tier}, source={lic.source}")
        if old_env:
            os.environ["EVO_LICENSE_KEY"] = old_env
        else:
            os.environ.pop("EVO_LICENSE_KEY", None)

        # Step 5: Simulate revocation
        print("[5/6] Simulating subscription deletion (clearing key)...")
        stripe.Customer.modify(
            customer.id,
            metadata={"evo_license_key": ""},
        )
        refreshed = stripe.Customer.retrieve(customer.id)
        cleared = refreshed.metadata.get("evo_license_key", "MISSING")
        assert cleared == "", f"Key not cleared: '{cleared}'"
        print("      Key cleared.")

        # Step 6: Verify free tier fallback
        print("[6/6] Verifying free tier fallback...")
        os.environ["EVO_LICENSE_KEY"] = ""
        lic = get_license()
        assert not lic.is_pro(), "Should be free tier after revocation!"
        print(f"      get_license(): tier={lic.tier} (correct)")
        os.environ.pop("EVO_LICENSE_KEY", None)

        print()
        print("ALL CHECKS PASSED")

    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        # Cleanup
        if customer:
            print(f"\nCleaning up: deleting customer {customer.id}...")
            try:
                stripe.Customer.delete(customer.id)
                print("Done.")
            except Exception as e:
                print(f"Cleanup warning: {e}")


if __name__ == "__main__":
    main()
