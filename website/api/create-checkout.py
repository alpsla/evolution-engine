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

_ALLOWED_ORIGIN = "https://codequal.dev"

# ─── In-memory rate limiter ───
_rate_store: dict[str, list[float]] = {}
_RATE_LIMIT = 5  # requests per window
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
    """Create a Stripe Checkout session for Pro subscription."""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", _ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        import stripe

        # Rate limiting
        client_ip = self.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()
        if _is_rate_limited(client_ip):
            return self._json({"error": "Too many requests"}, 429)

        secret_key = os.environ.get("STRIPE_SECRET_KEY")
        price_id = os.environ.get("STRIPE_PRICE_ID")
        base_url = os.environ.get("BASE_URL", "https://codequal.dev")

        if not secret_key or not price_id:
            return self._json({"error": "Stripe not configured"}, 500)

        stripe.api_key = secret_key

        # Read optional utm_source from request body
        utm_source = ""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = json.loads(self.rfile.read(content_length))
                raw = body.get("utm_source", "")
                if isinstance(raw, str):
                    utm_source = raw[:64]
        except Exception:
            pass

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{base_url}/#pricing",
                metadata={"product": "evolution-engine-pro", "utm_source": utm_source},
                allow_promotion_codes=True,
            )

            _axiom_send({
                "type": "checkout",
                "event": "checkout_started",
                "country": self.headers.get("x-vercel-ip-country", ""),
                "utm_source": utm_source,
                "timestamp": time.time(),
            })

            self._json({"url": session.url})
        except stripe.StripeError:
            self._json({"error": "Payment service unavailable. Please try again."}, 502)
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
