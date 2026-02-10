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


def handler(request):
    """Retrieve license key from Stripe Customer metadata by session ID."""
    import stripe

    if request.method != "GET":
        return _response({"error": "Method not allowed"}, 405)

    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key:
        return _response({"error": "Not configured"}, 500)

    stripe.api_key = secret_key

    # Get session_id from query params
    session_id = (
        request.args.get("session_id")
        if hasattr(request, 'args')
        else _get_query_param(request, "session_id")
    )

    if not session_id:
        return _response({"error": "Missing session_id"}, 400)

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        customer_id = session.get("customer")
        if not customer_id:
            return _response({"license_key": None})

        customer = stripe.Customer.retrieve(customer_id)
        license_key = customer.get("metadata", {}).get("evo_license_key")
        return _response({"license_key": license_key or None})

    except stripe.StripeError as e:
        return _response({"error": str(e)}, 400)


def _get_query_param(request, key):
    """Extract query parameter from various request formats."""
    if hasattr(request, 'query') and request.query:
        from urllib.parse import parse_qs
        params = parse_qs(request.query)
        values = params.get(key, [])
        return values[0] if values else None
    return None


def _response(body, status=200):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
