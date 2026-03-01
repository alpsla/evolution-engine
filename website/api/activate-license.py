"""
Vercel serverless function: Validate and activate a license key.

POST /api/activate-license
Body: { "key": "base64-encoded-license-key" }
Returns: { "valid": true, "tier": "pro", "email_hash": "...", "issued": "..." }

The CLI calls this endpoint during `evo license activate <key>`.
The key is validated server-side using the production signing key,
so the signing key never needs to ship in the CLI.

Environment variables:
  EVO_LICENSE_SIGNING_KEY — HMAC signing key (same one used by webhook.py)
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
_RATE_LIMIT = 10  # requests per window
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
    """Validate a signed license key using the given signing key.

    Returns parsed payload dict if valid, None otherwise.
    """
    try:
        decoded = base64.b64decode(key).decode("utf-8")
        if "." not in decoded:
            return None

        payload_str, signature = decoded.rsplit(".", 1)
        payload = json.loads(payload_str)

        expected_sig = hmac_mod.new(
            signing_key,
            payload_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac_mod.compare_digest(signature, expected_sig):
            return None

        # Check expiration if present
        if "expires" in payload:
            expires = datetime.fromisoformat(payload["expires"])
            now = datetime.now(expires.tzinfo)
            if now > expires:
                return None

        return payload
    except (ValueError, json.JSONDecodeError, KeyError):
        return None


class handler(BaseHTTPRequestHandler):
    """Validate a license key and return activation data."""

    def do_POST(self):
        signing_key = os.environ.get("EVO_LICENSE_SIGNING_KEY")
        if not signing_key:
            return self._json({"error": "Not configured"}, 500)

        # Rate limiting
        client_ip = self.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()
        if _is_rate_limited(client_ip):
            return self._json({"error": "Too many requests"}, 429)

        # Parse body
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "Invalid JSON"}, 400)

        key = body.get("key", "").strip()
        if not key:
            return self._json({"error": "Missing key"}, 400)

        # Validate key signature
        payload = _validate_key_server(key, signing_key.encode("utf-8"))
        if not payload:
            country = self.headers.get("x-vercel-ip-country", "")
            _axiom_send({
                "type": "activation",
                "event": "activation_failed",
                "country": country,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return self._json({"valid": False, "error": "Invalid or expired license key"}, 400)

        # Key is valid — return activation data
        now_iso = datetime.now(timezone.utc).isoformat()
        country = self.headers.get("x-vercel-ip-country", "")

        _axiom_send({
            "type": "activation",
            "event": "activation_success",
            "tier": payload.get("tier", "free"),
            "country": country,
            "timestamp": now_iso,
        })

        self._json({
            "valid": True,
            "tier": payload.get("tier", "free"),
            "email_hash": payload.get("email_hash"),
            "issued": payload.get("issued"),
            "activated_at": now_iso,
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
