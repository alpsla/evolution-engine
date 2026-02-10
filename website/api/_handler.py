"""Base handler for Vercel Python serverless functions.

Vercel's Python runtime expects `handler` to be a class extending
BaseHTTPRequestHandler (not a function returning dicts). This module
provides a JSONHandler base class with convenience methods for JSON
responses and CORS headers.
"""

import json
from http.server import BaseHTTPRequestHandler


class JSONHandler(BaseHTTPRequestHandler):
    """Base handler with JSON response and CORS helpers."""

    def _read_body(self):
        """Read and return the raw request body as bytes."""
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _read_json(self):
        """Read and parse the request body as JSON."""
        body = self._read_body()
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        return json.loads(body)

    def _send_json(self, body, status=200):
        """Send a JSON response with CORS headers."""
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(payload)

    def _send_cors(self):
        """Send a 204 CORS preflight response."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _get_header(self, name, default=""):
        """Get a request header value."""
        return self.headers.get(name, default)

    def _get_query_param(self, key):
        """Extract a query parameter from the URL."""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        values = params.get(key, [])
        return values[0] if values else None

    def _get_client_ip(self):
        """Get the client IP from forwarded headers."""
        forwarded = self._get_header("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self._get_header("X-Real-IP", "unknown")

    def log_message(self, format, *args):
        """Suppress default stderr logging."""
        pass
