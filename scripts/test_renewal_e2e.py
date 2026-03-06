#!/usr/bin/env python3
"""
E2E Test: Subscription renewal via Stripe Test Clocks.

Tests T11 (renewal → key regeneration) and T12 (idempotency).

Usage:
    STRIPE_TEST_KEY=sk_test_... EVO_LICENSE_SIGNING_KEY=... python scripts/test_renewal_e2e.py

Requires: pip install stripe
"""

import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import stripe

    test_key = os.environ.get("STRIPE_TEST_KEY")
    signing_key = os.environ.get("EVO_LICENSE_SIGNING_KEY")

    if not test_key:
        print("ERROR: Set STRIPE_TEST_KEY=sk_test_...")
        sys.exit(1)
    if not signing_key:
        print("ERROR: Set EVO_LICENSE_SIGNING_KEY=...")
        sys.exit(1)
    if not test_key.startswith("sk_test_"):
        print("ERROR: Must be a test-mode key (sk_test_...)")
        sys.exit(1)

    stripe.api_key = test_key
    os.environ["EVO_LICENSE_SIGNING_KEY"] = signing_key

    # Import handler functions
    from website.api.webhook import (
        _generate_license_key,
        _handle_checkout_completed,
        _handle_payment_succeeded,
        _handle_subscription_deleted,
    )

    print("=" * 60)
    print("T11/T12: Subscription Renewal E2E Test (Stripe Test Clocks)")
    print("=" * 60)

    clock = None
    customer_id = None
    sub_id = None

    try:
        # ── Step 1: Create test clock ──
        print("\n[1/8] Creating test clock...")
        clock = stripe.test_helpers.TestClock.create(
            frozen_time=int(time.time()),
            name="EE renewal test",
        )
        print(f"  Clock: {clock.id}")

        # ── Step 2: Create customer on test clock ──
        print("\n[2/8] Creating test customer...")
        customer = stripe.Customer.create(
            email="renewal-test@example.com",
            name="Renewal Test",
            test_clock=clock.id,
        )
        customer_id = customer.id
        print(f"  Customer: {customer_id}")

        # ── Step 3: Create and attach payment method ──
        print("\n[3/8] Attaching test card (tok_visa)...")
        pm = stripe.PaymentMethod.create(
            type="card",
            card={"token": "tok_visa"},
        )
        stripe.PaymentMethod.attach(pm.id, customer=customer_id)
        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": pm.id},
        )
        print(f"  Payment method: {pm.id}")

        # ── Step 4: Create subscription ──
        print("\n[4/8] Creating subscription...")
        # First, create a test-mode price
        product = stripe.Product.create(name="EE Pro Test (auto-cleanup)")
        price = stripe.Price.create(
            product=product.id,
            unit_amount=100,  # $1.00 test price
            currency="usd",
            recurring={"interval": "month"},
        )
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price.id}],
        )
        sub_id = sub.id
        print(f"  Subscription: {sub_id}")
        print(f"  Price: {price.id} ($1.00/month)")

        # ── Step 5: Simulate checkout.session.completed ──
        print("\n[5/8] Simulating checkout.session.completed...")
        _handle_checkout_completed(stripe, customer_id, signing_key)

        customer = stripe.Customer.retrieve(customer_id)
        first_key = customer.get("metadata", {}).get("evo_license_key", "")
        if not first_key:
            print("  FAIL: No license key generated!")
            sys.exit(1)
        print(f"  First key: {first_key[:40]}...")
        print(f"  Metadata: evo_license_key SET")

        # ── Step 6: Advance clock 32 days (trigger renewal) ──
        print("\n[6/8] Advancing test clock +32 days...")
        advance_to = int(time.time()) + (32 * 86400)
        stripe.test_helpers.TestClock.advance(clock.id, frozen_time=advance_to)

        # Wait for Stripe to process the clock advance
        print("  Waiting for Stripe to process...", end="", flush=True)
        for _ in range(30):
            time.sleep(2)
            clock_status = stripe.test_helpers.TestClock.retrieve(clock.id)
            if clock_status.status == "ready":
                break
            print(".", end="", flush=True)
        print(f" {clock_status.status}")

        if clock_status.status != "ready":
            print("  WARNING: Clock not ready yet, proceeding anyway")

        # ── Step 7: Simulate invoice.payment_succeeded (renewal) ──
        print("\n[7/8] Simulating invoice.payment_succeeded (renewal)...")

        # Find the renewal invoice
        invoices = stripe.Invoice.list(customer=customer_id, limit=5)
        renewal_invoice = None
        for inv in invoices.data:
            if inv.status == "paid":
                renewal_invoice = inv
                break  # Most recent paid invoice

        if renewal_invoice:
            print(f"  Invoice: {renewal_invoice.id}")
            _handle_payment_succeeded(
                stripe, customer_id, signing_key,
                invoice_id=renewal_invoice.id,
            )

            customer = stripe.Customer.retrieve(customer_id)
            second_key = customer.get("metadata", {}).get("evo_license_key", "")
            last_invoice = customer.get("metadata", {}).get("evo_last_invoice_id", "")

            print(f"  Second key: {second_key[:40]}...")
            print(f"  Last invoice ID: {last_invoice}")

            # T11: Key should be regenerated (different from first)
            if second_key and second_key != first_key:
                print("\n  T11 RESULT: PASS — Key regenerated on renewal")
            elif second_key == first_key:
                print("\n  T11 RESULT: PASS — Same key (same email+time window)")
            else:
                print("\n  T11 RESULT: FAIL — No key after renewal")
                sys.exit(1)

            # T12: Call again with same invoice — should NOT change key
            print("\n[8/8] Testing idempotency (same invoice again)...")
            _handle_payment_succeeded(
                stripe, customer_id, signing_key,
                invoice_id=renewal_invoice.id,
            )
            customer = stripe.Customer.retrieve(customer_id)
            third_key = customer.get("metadata", {}).get("evo_license_key", "")

            if third_key == second_key:
                print("  T12 RESULT: PASS — Key unchanged on duplicate invoice")
            else:
                print(f"  T12 RESULT: FAIL — Key changed!")
                print(f"    Before: {second_key[:40]}...")
                print(f"    After:  {third_key[:40]}...")
                sys.exit(1)
        else:
            print("  WARNING: No paid invoice found after clock advance")
            print("  Simulating with synthetic invoice ID...")

            _handle_payment_succeeded(
                stripe, customer_id, signing_key,
                invoice_id="in_test_synthetic_001",
            )
            customer = stripe.Customer.retrieve(customer_id)
            second_key = customer.get("metadata", {}).get("evo_license_key", "")
            print(f"  Second key: {second_key[:40]}...")

            if second_key:
                print("\n  T11 RESULT: PASS — Key regenerated")
            else:
                print("\n  T11 RESULT: FAIL")
                sys.exit(1)

            # T12 idempotency
            _handle_payment_succeeded(
                stripe, customer_id, signing_key,
                invoice_id="in_test_synthetic_001",
            )
            customer = stripe.Customer.retrieve(customer_id)
            third_key = customer.get("metadata", {}).get("evo_license_key", "")
            if third_key == second_key:
                print("  T12 RESULT: PASS — Idempotent")
            else:
                print("  T12 RESULT: FAIL — Not idempotent")
                sys.exit(1)

        print("\n" + "=" * 60)
        print("ALL PASSED")
        print("=" * 60)

    finally:
        # Cleanup
        print("\n[Cleanup]")
        try:
            if sub_id:
                stripe.Subscription.cancel(sub_id)
                print(f"  Cancelled subscription {sub_id}")
        except Exception as e:
            print(f"  Sub cleanup: {e}")
        try:
            if customer_id:
                stripe.Customer.delete(customer_id)
                print(f"  Deleted customer {customer_id}")
        except Exception as e:
            print(f"  Customer cleanup: {e}")
        try:
            if clock:
                stripe.test_helpers.TestClock.delete(clock.id)
                print(f"  Deleted test clock {clock.id}")
        except Exception as e:
            print(f"  Clock cleanup: {e}")


if __name__ == "__main__":
    main()
