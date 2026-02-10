"""
Vercel serverless function: Stripe webhook handler.

POST /api/webhook
Handles:
  - checkout.session.completed → generate HMAC license key, store on Customer
  - customer.subscription.deleted → clear license key from Customer metadata

Environment variables:
  STRIPE_SECRET_KEY       — Stripe secret key
  STRIPE_WEBHOOK_SECRET   — Webhook endpoint signing secret
  EVO_LICENSE_SIGNING_KEY — HMAC signing key for license generation
"""

import base64
import hashlib
import hmac as hmac_mod
import json
import os
from datetime import datetime, timezone

from _axiom import send as axiom_send


def handler(request):
    """Handle Stripe webhook events."""
    import stripe

    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    signing_key = os.environ.get("EVO_LICENSE_SIGNING_KEY", "evo-license-v1-dev-key-replace-in-production")

    if not secret_key or not webhook_secret:
        return _response({"error": "Not configured"}, 500)

    stripe.api_key = secret_key

    # Verify webhook signature
    payload = request.body if hasattr(request, 'body') else request.get_data()
    sig_header = (
        request.headers.get("Stripe-Signature")
        or request.headers.get("stripe-signature", "")
    )

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.SignatureVerificationError):
        return _response({"error": "Invalid signature"}, 400)

    # Handle events
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        if customer_id:
            _handle_checkout_completed(stripe, customer_id, signing_key)

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")
        if customer_id:
            _handle_subscription_deleted(stripe, customer_id)

    return _response({"received": True})


def _handle_checkout_completed(stripe, customer_id, signing_key):
    """Generate license key and store on Stripe Customer metadata."""
    # Idempotent: check if key already exists
    customer = stripe.Customer.retrieve(customer_id)
    metadata = customer.get("metadata", {})
    if metadata.get("evo_license_key"):
        return  # Already has a key

    # Get customer email
    email = customer.get("email", "unknown@customer.com")

    # Generate HMAC-signed license key (same algorithm as evolution/license.py)
    license_key = _generate_license_key(
        tier="pro",
        email=email,
        signing_key=signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key,
    )

    # Store on customer metadata
    stripe.Customer.modify(
        customer_id,
        metadata={"evo_license_key": license_key},
    )

    # Log for observability
    log_entry = {
        "type": "webhook",
        "event": "license_generated",
        "customer_id": customer_id,
        "tier": "pro",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(log_entry))
    axiom_send(log_entry)


def _handle_subscription_deleted(stripe, customer_id):
    """Clear license key from Customer metadata on cancellation."""
    stripe.Customer.modify(
        customer_id,
        metadata={"evo_license_key": ""},
    )
    log_entry = {
        "type": "webhook",
        "event": "license_revoked",
        "customer_id": customer_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(log_entry))
    axiom_send(log_entry)


def _generate_license_key(tier, email, signing_key):
    """Generate HMAC-signed license key. Mirrors evolution/license.py:generate_key."""
    payload = {
        "tier": tier,
        "email": email,
        "issued": datetime.now(timezone.utc).isoformat(),
    }
    payload_str = json.dumps(payload, sort_keys=True)
    signature = hmac_mod.new(
        signing_key,
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    signed = f"{payload_str}.{signature}"
    return base64.b64encode(signed.encode("utf-8")).decode("utf-8")


def _response(body, status=200):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
