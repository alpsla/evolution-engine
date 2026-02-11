"""
Vercel serverless function: Handle adapter requests from the landing page.

POST /api/adapter-request
Body: { "adapter_name", "family", "description", "email", "use_case" }

Creates a GitHub Issue with the 'adapter-request' label.
Rate limit: 5 requests per IP per day.

Environment variables:
  GITHUB_BOT_TOKEN — GitHub token with repo:issues scope
  GITHUB_REPO      — Target repo (e.g. "alpsla/evolution_monitor")
"""

import json
import os
import re
import time
import urllib.request
from http.server import BaseHTTPRequestHandler

# In-memory rate limit (resets on cold start)
_rate_limits: dict[str, list[float]] = {}
_MAX_REQUESTS_PER_DAY = 5
_MAX_FIELD_LENGTH = 1000

_VALID_FAMILIES = {
    "ci", "deployment", "dependency", "security", "monitoring",
    "incidents", "work_items", "quality_gate", "error_tracking",
    "feature_flags", "code_review", "other",
}


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


def _sanitize(text, max_length):
    if not isinstance(text, str):
        return ""
    text = text.strip()[:max_length]
    return re.sub(r'[<>]', '', text)


class handler(BaseHTTPRequestHandler):
    """Handle adapter request submission."""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            return self._json({"error": "Invalid JSON"}, 400)

        adapter_name = _sanitize(data.get("adapter_name", ""), 100)
        family = data.get("family", "")
        description = _sanitize(data.get("description", ""), _MAX_FIELD_LENGTH)
        email = _sanitize(data.get("email", ""), 200)
        use_case = _sanitize(data.get("use_case", ""), 500)

        if not adapter_name:
            return self._json({"error": "Adapter name is required"}, 400)
        if family not in _VALID_FAMILIES:
            return self._json({"error": f"Invalid family. Must be one of: {', '.join(sorted(_VALID_FAMILIES))}"}, 400)

        client_ip = (self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                     or self.headers.get("X-Real-IP", "unknown"))
        rate_key = f"email:{email}" if email else f"ip:{client_ip}"

        now = time.time()
        if rate_key not in _rate_limits:
            _rate_limits[rate_key] = []
        _rate_limits[rate_key] = [t for t in _rate_limits[rate_key] if now - t < 86400]

        if len(_rate_limits[rate_key]) >= _MAX_REQUESTS_PER_DAY:
            return self._json({"error": "Rate limit exceeded. Try again tomorrow."}, 429)

        _rate_limits[rate_key].append(now)

        github_token = os.environ.get("GITHUB_BOT_TOKEN")
        github_repo = os.environ.get("GITHUB_REPO", "alpsla/evolution_monitor")

        if not github_token:
            log_entry = {
                "type": "adapter_request",
                "adapter_name": adapter_name,
                "family": family,
                "description": description,
                "use_case": use_case,
                "email": email,
                "timestamp": now,
            }
            print(json.dumps(log_entry))
            _axiom_send(log_entry)
            return self._json({"success": True, "message": "Request recorded."})

        issue_body = f"""## Adapter Request: {adapter_name}

**Family:** {family}

**Use Case:**
{use_case or '_Not specified_'}

**Additional Details:**
{description or '_Not specified_'}

---
_Submitted via codequal.dev adapter request form._
_Vote with a thumbs-up if you'd also like this adapter!_
"""

        # Log email to Axiom only (never in public GitHub issues)
        if email:
            _axiom_send({
                "type": "adapter_request_contact",
                "adapter_name": adapter_name,
                "family": family,
                "email": email,
                "timestamp": now,
            })

        issue_data = {
            "title": f"Adapter request: {adapter_name} ({family})",
            "body": issue_body,
            "labels": ["adapter-request"],
        }

        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{github_repo}/issues",
                data=json.dumps(issue_data).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode("utf-8"))
            return self._json({
                "success": True,
                "message": "Request submitted as a GitHub issue!",
                "issue_url": result.get("html_url", ""),
            })
        except Exception as e:
            error_entry = {"type": "adapter_request", "error": "github_issue_creation_failed", "detail": str(e), "timestamp": time.time()}
            print(json.dumps(error_entry))
            _axiom_send(error_entry)
            return self._json({"success": True, "message": "Request recorded. We'll follow up soon."})

    def _json(self, body, status=200):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass
