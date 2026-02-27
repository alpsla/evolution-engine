"""
Vercel serverless function: Create Stripe Checkout session.

POST /api/create-checkout
Returns: { "url": "https://checkout.stripe.com/..." }

Environment variables:
  STRIPE_SECRET_KEY  — Stripe secret key
  STRIPE_PRICE_ID   — Price ID for Pro subscription ($19/month)
  BASE_URL           — Site base URL (e.g. https://codequal.dev)
"""

import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler


def _axiom_send(event: dict) -> None:
    """Fire-and-forget: send a single event to Axiom. Never raises."""
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
    """Create a Stripe Checkout session for Pro subscription."""

    def do_POST(self):
        import stripe

        secret_key = os.environ.get("STRIPE_SECRET_KEY")
        price_id = os.environ.get("STRIPE_PRICE_ID")
        base_url = os.environ.get("BASE_URL", "https://codequal.dev")

        if not secret_key or not price_id:
            return self._json({"error": "Stripe not configured"}, 500)

        stripe.api_key = secret_key

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{base_url}/#pricing",
                metadata={"product": "evolution-engine-pro"},
                allow_promotion_codes=True,
            )

            _axiom_send({
                "type": "checkout",
                "event": "checkout_started",
                "country": self.headers.get("x-vercel-ip-country", ""),
                "timestamp": time.time(),
            })

            self._json({"url": session.url})
        except stripe.StripeError as e:
            self._json({"error": str(e)}, 400)

    def _json(self, body, status=200):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass
