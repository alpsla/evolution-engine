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

from _handler import JSONHandler


class handler(JSONHandler):
    """Retrieve license key from Stripe Customer metadata by session ID."""

    def do_GET(self):
        import stripe

        secret_key = os.environ.get("STRIPE_SECRET_KEY")
        if not secret_key:
            return self._send_json({"error": "Not configured"}, 500)

        stripe.api_key = secret_key

        session_id = self._get_query_param("session_id")
        if not session_id:
            return self._send_json({"error": "Missing session_id"}, 400)

        try:
            session = stripe.checkout.Session.retrieve(session_id)
            customer_id = session.get("customer")
            if not customer_id:
                return self._send_json({"license_key": None})

            customer = stripe.Customer.retrieve(customer_id)
            license_key = customer.get("metadata", {}).get("evo_license_key")
            self._send_json({"license_key": license_key or None})

        except stripe.StripeError as e:
            self._send_json({"error": str(e)}, 400)
