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
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


class handler(BaseHTTPRequestHandler):
    """Retrieve license key from Stripe Customer metadata by session ID."""

    def do_GET(self):
        import stripe

        secret_key = os.environ.get("STRIPE_SECRET_KEY")
        if not secret_key:
            return self._json({"error": "Not configured"}, 500)

        stripe.api_key = secret_key

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        session_id = params.get("session_id", [None])[0]
        if not session_id:
            return self._json({"error": "Missing session_id"}, 400)

        try:
            session = stripe.checkout.Session.retrieve(session_id)
            customer_id = session.get("customer")
            if not customer_id:
                return self._json({"license_key": None})

            customer = stripe.Customer.retrieve(customer_id)
            license_key = customer.get("metadata", {}).get("evo_license_key")
            self._json({"license_key": license_key or None})

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
