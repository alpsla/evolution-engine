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


def handler(request):
    """Create a Stripe Checkout session for Pro subscription."""
    import stripe

    if request.method != "POST":
        return _response({"error": "Method not allowed"}, 405)

    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    price_id = os.environ.get("STRIPE_PRICE_ID")
    base_url = os.environ.get("BASE_URL", "https://codequal.dev")

    if not secret_key or not price_id:
        return _response({"error": "Stripe not configured"}, 500)

    stripe.api_key = secret_key

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/#pricing",
            metadata={"product": "evolution-engine-pro"},
        )
        return _response({"url": session.url})
    except stripe.StripeError as e:
        return _response({"error": str(e)}, 400)


def _response(body, status=200):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
