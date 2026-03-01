"""
Vercel serverless function: Retrieve license key after checkout.

GET /api/get-license?session_id=cs_xxx
Returns: { "license_key": "..." } or { "license_key": null }

Used by success.html to display the license key after Stripe checkout.

Environment variables:
  STRIPE_SECRET_KEY — Stripe secret key
"""

import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

_ALLOWED_ORIGIN = "https://codequal.dev"

# ─── In-memory rate limiter ───
_rate_store: dict[str, list[float]] = {}
_RATE_LIMIT = 20  # requests per window (higher: success.html polls every 2s)
_RATE_WINDOW = 60  # seconds


def _is_rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    hits = _rate_store.get(client_ip, [])
    hits = [t for t in hits if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_LIMIT:
        return True
    hits.append(now)
    _rate_store[client_ip] = hits
    return False


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
    """Retrieve license key from Stripe Customer metadata by session ID."""

    def do_GET(self):
        import stripe

        # Rate limiting
        client_ip = self.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()
        if _is_rate_limited(client_ip):
            return self._json({"error": "Too many requests"}, 429)

        secret_key = os.environ.get("STRIPE_SECRET_KEY")
        if not secret_key:
            return self._json({"error": "Not configured"}, 500)

        stripe.api_key = secret_key

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        session_id = params.get("session_id", [None])[0]
        if not session_id:
            return self._json({"error": "Missing session_id"}, 400)

        # Basic session_id format validation (Stripe IDs start with cs_)
        if not session_id.startswith("cs_") or len(session_id) > 200:
            return self._json({"error": "Invalid session_id"}, 400)

        try:
            session = stripe.checkout.Session.retrieve(session_id)
            customer_id = session.get("customer")
            if not customer_id:
                return self._json({"license_key": None})

            customer = stripe.Customer.retrieve(customer_id)
            license_key = customer.get("metadata", {}).get("evo_license_key")

            _axiom_send({
                "type": "checkout",
                "event": "license_retrieved",
                "has_key": bool(license_key),
                "country": self.headers.get("x-vercel-ip-country", ""),
                "timestamp": time.time(),
            })

            self._json({"license_key": license_key or None})

        except stripe.StripeError:
            self._json({"error": "Could not retrieve license. Please try again."}, 502)
        except Exception:
            self._json({"error": "Internal error"}, 500)

    def _json(self, body, status=200):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", _ALLOWED_ORIGIN)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass
