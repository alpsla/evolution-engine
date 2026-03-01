"""
Vercel serverless function: License heartbeat / status check.

POST /api/license-check
Body: { "key": "base64-encoded-license-key" }
Returns: { "status": "active"|"cancelled"|"past_due"|"revoked"|"unknown", "checked_at": "..." }

The CLI calls this periodically (every 7 days) to verify that the license
is still backed by an active subscription. Even if the HMAC-signed key
itself has no expiry, this endpoint reflects the real subscription state
as recorded by the Stripe webhook handler.

Environment variables:
  EVO_LICENSE_SIGNING_KEY    — HMAC signing key (validates key authenticity)
  UPSTASH_REDIS_REST_URL     — Upstash Redis REST URL
  UPSTASH_REDIS_REST_TOKEN   — Upstash Redis REST token
"""

import base64
import hashlib
import hmac as hmac_mod
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler


# ─── Simple in-memory rate limiter ───

_rate_store: dict[str, list[float]] = {}
_RATE_LIMIT = 20  # requests per window
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


def _validate_key_server(key: str, signing_key: bytes) -> dict | None:
    """Validate a signed license key. Returns payload dict if valid."""
    try:
        decoded = base64.b64decode(key).decode("utf-8")
        if "." not in decoded:
            return None
        payload_str, signature = decoded.rsplit(".", 1)
        payload = json.loads(payload_str)
        expected_sig = hmac_mod.new(
            signing_key, payload_str.encode("utf-8"), hashlib.sha256,
        ).hexdigest()
        if not hmac_mod.compare_digest(signature, expected_sig):
            return None
        return payload
    except (ValueError, json.JSONDecodeError, KeyError):
        return None


def _redis_get_license_status(key_hash: str) -> dict | None:
    """Look up license subscription status from Redis."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None

    redis_key = f"evo:license:{key_hash}"
    try:
        req = urllib.request.Request(
            f"{url}/get/{redis_key}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode("utf-8"))
        result = data.get("result")
        if result is None:
            return None
        return json.loads(result)
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    """Check license subscription status via Redis lookup."""

    def do_POST(self):
        signing_key = os.environ.get("EVO_LICENSE_SIGNING_KEY")
        if not signing_key:
            return self._json({"error": "Not configured"}, 503)

        # Rate limiting
        client_ip = self.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()
        if _is_rate_limited(client_ip):
            return self._json({"error": "Too many requests"}, 429)

        # Parse body
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 4096:
                return self._json({"error": "Payload too large"}, 413)
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "Invalid JSON"}, 400)

        key = body.get("key", "").strip()
        if not key:
            return self._json({"error": "Missing key"}, 400)

        # Step 1: Validate HMAC — rejects forged keys
        payload = _validate_key_server(key, signing_key.encode("utf-8"))
        if not payload:
            return self._json({"valid": False, "status": "invalid"}, 400)

        # Step 2: Look up subscription status in Redis
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        redis_data = _redis_get_license_status(key_hash)

        now_iso = datetime.now(timezone.utc).isoformat()

        if redis_data is None:
            # No record in Redis — key is valid (HMAC OK) but was issued
            # before heartbeat tracking was deployed, or Redis is down.
            # Return "active" to avoid breaking existing customers.
            status = "active"
        else:
            status = redis_data.get("status", "unknown")

        _axiom_send({
            "type": "license_check",
            "event": "heartbeat",
            "status": status,
            "tier": payload.get("tier", "free"),
            "country": self.headers.get("x-vercel-ip-country", ""),
            "timestamp": now_iso,
        })

        self._json({
            "valid": status in ("active", "unknown"),
            "status": status,
            "tier": payload.get("tier", "free"),
            "checked_at": now_iso,
        })

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "https://codequal.dev")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, body, status=200):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "https://codequal.dev")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass
