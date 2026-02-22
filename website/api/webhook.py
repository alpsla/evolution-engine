"""
Vercel serverless function: Stripe webhook handler.

POST /api/webhook
Handles:
  - checkout.session.completed → generate HMAC license key, store on Customer
  - customer.subscription.deleted → clear license key from Customer metadata
  - invoice.payment_failed → flag customer with payment_status=past_due

Environment variables:
  STRIPE_SECRET_KEY       — Stripe secret key
  STRIPE_WEBHOOK_SECRET   — Webhook endpoint signing secret
"""

import base64
import hashlib
import hmac as hmac_mod
import json
import os
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler


def _axiom_send(event: dict) -> None:
    token = os.environ.get("AXIOM_TOKEN")
    if not token:
        return
    dataset = os.environ.get("AXIOM_DATASET", "evo")
    try:
        req = urllib.request.Request(
            f"https://api.axiom.co/v1/datasets/{dataset}/ingest",
            data=json.dumps([event]).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


class handler(BaseHTTPRequestHandler):
    """Handle Stripe webhook events."""

    def do_POST(self):
        import stripe

        secret_key = os.environ.get("STRIPE_SECRET_KEY")
        webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        signing_key = os.environ.get("EVO_LICENSE_SIGNING_KEY")

        if not secret_key or not webhook_secret or not signing_key:
            return self._json({"error": "Not configured"}, 500)

        stripe.api_key = secret_key

        length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(length)
        sig_header = self.headers.get("Stripe-Signature") or self.headers.get("stripe-signature", "")

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except (ValueError, stripe.SignatureVerificationError):
            return self._json({"error": "Invalid signature", "v": 2}, 400)

        event_type = event["type"]
        result = {"received": True, "event_type": event_type}

        try:
            if event_type == "checkout.session.completed":
                session = event["data"]["object"]
                customer_id = session.get("customer")
                result["customer_id"] = customer_id
                if customer_id:
                    _handle_checkout_completed(stripe, customer_id, signing_key)
                    result["action"] = "license_generated"
                else:
                    result["action"] = "skipped_no_customer"

            elif event_type == "customer.subscription.deleted":
                subscription = event["data"]["object"]
                customer_id = subscription.get("customer")
                if customer_id:
                    _handle_subscription_deleted(stripe, customer_id)
                    result["action"] = "license_revoked"

            elif event_type == "invoice.payment_failed":
                invoice = event["data"]["object"]
                customer_id = invoice.get("customer")
                attempt_count = invoice.get("attempt_count", 0)
                result["customer_id"] = customer_id
                result["attempt_count"] = attempt_count
                if customer_id:
                    _handle_payment_failed(stripe, customer_id, attempt_count)
                    result["action"] = "payment_failed_flagged"
        except Exception as exc:
            _axiom_send({
                "type": "webhook_error",
                "event_type": event_type,
                "error": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return self._json({"error": "Internal processing error"}, 500)

        self._json(result)

    def _json(self, body, status=200):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


def _handle_checkout_completed(stripe, customer_id, signing_key):
    customer = stripe.Customer.retrieve(customer_id)
    metadata = customer.get("metadata", {})
    if metadata.get("evo_license_key"):
        return

    email = customer.get("email", "unknown@customer.com")
    license_key = _generate_license_key(
        tier="pro",
        email=email,
        signing_key=signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key,
    )

    stripe.Customer.modify(customer_id, metadata={"evo_license_key": license_key})

    log_entry = {
        "type": "webhook",
        "event": "license_generated",
        "customer_id": customer_id,
        "tier": "pro",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(log_entry))
    _axiom_send(log_entry)


def _handle_subscription_deleted(stripe, customer_id):
    stripe.Customer.modify(customer_id, metadata={"evo_license_key": ""})
    log_entry = {
        "type": "webhook",
        "event": "license_revoked",
        "customer_id": customer_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(log_entry))
    _axiom_send(log_entry)


def _handle_payment_failed(stripe, customer_id, attempt_count):
    """Flag customer when invoice payment fails."""
    stripe.Customer.modify(customer_id, metadata={
        "evo_payment_status": "past_due",
        "evo_payment_failed_at": datetime.now(timezone.utc).isoformat(),
        "evo_payment_attempt": str(attempt_count),
    })
    log_entry = {
        "type": "webhook",
        "event": "payment_failed",
        "customer_id": customer_id,
        "attempt_count": attempt_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(log_entry))
    _axiom_send(log_entry)


def _generate_license_key(tier, email, signing_key):
    email_hash = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()[:16]
    payload = {
        "tier": tier,
        "email_hash": email_hash,
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
