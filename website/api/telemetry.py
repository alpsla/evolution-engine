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
from _handler import JSONHandler

# In-memory rate limit (resets on cold start)
_rate_limits: dict[str, list[float]] = {}
_MAX_EVENTS_PER_HOUR = 100
_MAX_PAYLOAD_SIZE = 4096  # bytes


class handler(JSONHandler):
    """Receive and log telemetry events."""

    def do_OPTIONS(self):
        self._send_cors()

    def do_POST(self):
        # Parse body
        try:
            raw = self._read_body()
            if len(raw) > _MAX_PAYLOAD_SIZE:
                return self._send_json({"error": "Payload too large"}, 413)
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            return self._send_json({"error": "Invalid JSON"}, 400)

        # Validate structure
        event_name = data.get("event")
        if not event_name or not isinstance(event_name, str):
            return self._send_json({"error": "Missing event name"}, 400)

        anon_id = data.get("anon_id", "unknown")
        if not isinstance(anon_id, str) or len(anon_id) > 50:
            return self._send_json({"error": "Invalid anon_id"}, 400)

        # Rate limit
        now = time.time()
        if anon_id not in _rate_limits:
            _rate_limits[anon_id] = []

        # Clean old entries (older than 1 hour)
        _rate_limits[anon_id] = [t for t in _rate_limits[anon_id] if now - t < 3600]

        if len(_rate_limits[anon_id]) >= _MAX_EVENTS_PER_HOUR:
            return self._send_json({"error": "Rate limit exceeded"}, 429)

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

        self._send_json({"ok": True})
