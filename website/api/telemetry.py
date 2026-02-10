"""
Vercel serverless function: Receive anonymous telemetry events.

POST /api/telemetry
Body: { "event": "cli_command", "properties": {...}, "anon_id": "uuid", "version": "0.1.0" }

Logs events as structured JSON to stdout (captured by Vercel's log viewer).
Rate limit: 100 events/hour per anon_id (in-memory, resets per cold start).
"""

import json
import time

from _axiom import send as axiom_send

# In-memory rate limit (resets on cold start)
_rate_limits: dict[str, list[float]] = {}
_MAX_EVENTS_PER_HOUR = 100
_MAX_PAYLOAD_SIZE = 4096  # bytes


def handler(request):
    """Receive and log telemetry events."""
    if request.method == "OPTIONS":
        return _cors_response()

    if request.method != "POST":
        return _response({"error": "Method not allowed"}, 405)

    # Parse body
    try:
        body = request.body if hasattr(request, 'body') else request.get_data()
        if isinstance(body, bytes):
            if len(body) > _MAX_PAYLOAD_SIZE:
                return _response({"error": "Payload too large"}, 413)
            body = body.decode("utf-8")
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return _response({"error": "Invalid JSON"}, 400)

    # Validate structure
    event_name = data.get("event")
    if not event_name or not isinstance(event_name, str):
        return _response({"error": "Missing event name"}, 400)

    anon_id = data.get("anon_id", "unknown")
    if not isinstance(anon_id, str) or len(anon_id) > 50:
        return _response({"error": "Invalid anon_id"}, 400)

    # Rate limit
    now = time.time()
    if anon_id not in _rate_limits:
        _rate_limits[anon_id] = []

    # Clean old entries (older than 1 hour)
    _rate_limits[anon_id] = [t for t in _rate_limits[anon_id] if now - t < 3600]

    if len(_rate_limits[anon_id]) >= _MAX_EVENTS_PER_HOUR:
        return _response({"error": "Rate limit exceeded"}, 429)

    _rate_limits[anon_id].append(now)

    # Log structured event (Vercel captures stdout)
    log_entry = {
        "type": "telemetry",
        "event": event_name,
        "properties": data.get("properties", {}),
        "anon_id": anon_id,
        "version": data.get("version", "unknown"),
        "timestamp": now,
    }
    print(json.dumps(log_entry))
    axiom_send(log_entry)

    return _response({"ok": True})


def _response(body, status=200):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }


def _cors_response():
    return {
        "statusCode": 204,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": "",
    }
