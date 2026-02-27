"""
Vercel serverless function: Receive anonymous telemetry events.

POST /api/telemetry
Body: { "event": "cli_command", "properties": {...}, "anon_id": "uuid", "version": "0.1.0" }

Logs events as structured JSON to stdout (captured by Vercel's log viewer).
Rate limit: 100 events/hour per anon_id (in-memory, resets per cold start).
"""

import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler

# In-memory rate limit (resets on cold start)
_rate_limits: dict[str, list[float]] = {}
_MAX_EVENTS_PER_HOUR = 100
_MAX_PAYLOAD_SIZE = 4096  # bytes


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
    """Receive and log telemetry events."""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            if len(raw) > _MAX_PAYLOAD_SIZE:
                return self._json({"error": "Payload too large"}, 413)
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            return self._json({"error": "Invalid JSON"}, 400)

        event_name = data.get("event")
        if not event_name or not isinstance(event_name, str):
            return self._json({"error": "Missing event name"}, 400)

        anon_id = data.get("anon_id", "unknown")
        if not isinstance(anon_id, str) or len(anon_id) > 50:
            return self._json({"error": "Invalid anon_id"}, 400)

        now = time.time()
        if anon_id not in _rate_limits:
            _rate_limits[anon_id] = []
        _rate_limits[anon_id] = [t for t in _rate_limits[anon_id] if now - t < 3600]

        if len(_rate_limits[anon_id]) >= _MAX_EVENTS_PER_HOUR:
            return self._json({"error": "Rate limit exceeded"}, 429)

        _rate_limits[anon_id].append(now)

        # Extract User-Agent for CLI version tracking
        user_agent = self.headers.get("User-Agent", "")

        # Geo: country code from Vercel header (no IP, no city)
        country = self.headers.get("x-vercel-ip-country", "")

        log_entry = {
            "type": "telemetry",
            "event": event_name,
            "properties": data.get("properties", {}),
            "anon_id": anon_id,
            "version": data.get("version", "unknown"),
            "user_agent": user_agent,
            "country": country,
            "timestamp": now,
        }
        print(json.dumps(log_entry))
        _axiom_send(log_entry)

        self._json({"ok": True})

    def _json(self, body, status=200):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass
