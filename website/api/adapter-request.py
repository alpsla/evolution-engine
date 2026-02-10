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

from _axiom import send as axiom_send
from _handler import JSONHandler

# In-memory rate limit (resets on cold start)
_rate_limits: dict[str, list[float]] = {}
_MAX_REQUESTS_PER_DAY = 5
_MAX_FIELD_LENGTH = 1000

# Valid families
_VALID_FAMILIES = {
    "ci", "deployment", "dependency", "security", "monitoring",
    "incidents", "work_items", "quality_gate", "error_tracking",
    "feature_flags", "code_review", "other",
}


class handler(JSONHandler):
    """Handle adapter request submission."""

    def do_OPTIONS(self):
        self._send_cors()

    def do_POST(self):
        # Parse body
        try:
            data = self._read_json()
        except (json.JSONDecodeError, ValueError):
            return self._send_json({"error": "Invalid JSON"}, 400)

        # Validate required fields
        adapter_name = _sanitize(data.get("adapter_name", ""), 100)
        family = data.get("family", "")
        description = _sanitize(data.get("description", ""), _MAX_FIELD_LENGTH)
        email = _sanitize(data.get("email", ""), 200)
        use_case = _sanitize(data.get("use_case", ""), 500)

        if not adapter_name:
            return self._send_json({"error": "Adapter name is required"}, 400)
        if family not in _VALID_FAMILIES:
            return self._send_json({"error": f"Invalid family. Must be one of: {', '.join(sorted(_VALID_FAMILIES))}"}, 400)

        # Rate limit by IP
        client_ip = self._get_client_ip()
        rate_key = f"ip:{client_ip}"
        if email:
            rate_key = f"email:{email}"

        now = time.time()
        if rate_key not in _rate_limits:
            _rate_limits[rate_key] = []
        _rate_limits[rate_key] = [t for t in _rate_limits[rate_key] if now - t < 86400]

        if len(_rate_limits[rate_key]) >= _MAX_REQUESTS_PER_DAY:
            return self._send_json({"error": "Rate limit exceeded. Try again tomorrow."}, 429)

        _rate_limits[rate_key].append(now)

        # Create GitHub issue
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
            axiom_send(log_entry)
            return self._send_json({"success": True, "message": "Request recorded."})

        # Build issue body
        issue_body = f"""## Adapter Request: {adapter_name}

**Family:** {family}

**Use Case:**
{use_case or '_Not specified_'}

**Additional Details:**
{description or '_Not specified_'}

**Requested by:** {email or '_Anonymous_'}

---
_Submitted via codequal.dev adapter request form._
_Vote with a thumbs-up if you'd also like this adapter!_
"""

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
            issue_url = result.get("html_url", "")

            return self._send_json({
                "success": True,
                "message": "Request submitted as a GitHub issue!",
                "issue_url": issue_url,
            })
        except Exception as e:
            error_entry = {"type": "adapter_request", "error": "github_issue_creation_failed", "detail": str(e), "timestamp": time.time()}
            print(json.dumps(error_entry))
            axiom_send(error_entry)
            return self._send_json({
                "success": True,
                "message": "Request recorded. We'll follow up soon.",
            })


def _sanitize(text, max_length):
    """Sanitize user input."""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    text = text[:max_length]
    text = re.sub(r'[<>]', '', text)
    return text
