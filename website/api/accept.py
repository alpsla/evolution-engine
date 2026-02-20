"""
Vercel serverless function: Acceptance webhook handler.

POST /api/accept — Store permanent acceptances for a repo
GET  /api/accept?repo=owner/repo — Retrieve acceptances for a repo

Storage: Upstash Redis at key evo:accept:{sha256(repo)[:16]}
Auth: HMAC-SHA256 of repo name using EVO_ACCEPT_SECRET
Env vars: UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN, EVO_ACCEPT_SECRET
"""

import hashlib
import hmac as hmac_mod
import json
import os
import re
import time
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# ── Constants ──

_MAX_PAYLOAD_SIZE = 51200  # 50KB
_MAX_ENTRIES = 100
_MAX_ACCEPTS_PER_HOUR = 20
_KEY_RE = re.compile(r"^[a-zA-Z0-9_]+:[a-zA-Z0-9_]+$")
_SAFE_TEXT_MAX = 500

_DANGEROUS_PATTERNS = [
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"\{\{.*\}\}"),
    re.compile(r"\$\{.*\}"),
    re.compile(r";\s*(rm|del|drop|exec|eval)\b", re.IGNORECASE),
    re.compile(r"\.\./"),
]

# In-memory rate limit (resets on cold start)
_rate_limits: dict[str, list[float]] = {}


# ── Axiom Logging ──

def _axiom_send(event: dict) -> None:
    """Fire-and-forget: send a single event to Axiom."""
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


# ── Upstash Redis ──

def _redis_key(repo: str) -> str:
    """Compute the Redis key for a repo's acceptances."""
    repo_hash = hashlib.sha256(repo.encode("utf-8")).hexdigest()[:16]
    return f"evo:accept:{repo_hash}"


def _redis_get(key: str) -> dict | None:
    """Read a JSON blob from Upstash Redis."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None

    try:
        req = urllib.request.Request(
            f"{url}/get/{key}",
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


def _redis_set(key: str, data: dict) -> bool:
    """Write a JSON blob to Upstash Redis."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return False

    try:
        payload = json.dumps(["SET", key, json.dumps(data)]).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False


# ── Validation ──

def _check_text_safe(value: str, field_name: str, max_len: int = _SAFE_TEXT_MAX) -> tuple[str | None, str | None]:
    """Validate a text field for dangerous content."""
    if not isinstance(value, str):
        return None, f"{field_name}: expected string"
    if len(value) > max_len:
        return None, f"{field_name}: exceeds max length {max_len}"
    for pat in _DANGEROUS_PATTERNS:
        if pat.search(value):
            return None, f"{field_name}: contains dangerous content"
    return value.strip(), None


def _verify_signature(repo: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature of repo name."""
    secret = os.environ.get("EVO_ACCEPT_SECRET")
    if not secret:
        return False
    expected = hmac_mod.new(
        secret.encode("utf-8"),
        repo.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac_mod.compare_digest(expected, signature)


def _check_rate_limit(repo: str) -> bool:
    """Check if repo is within rate limit. Returns True if allowed."""
    now = time.time()
    if repo not in _rate_limits:
        _rate_limits[repo] = []
    _rate_limits[repo] = [t for t in _rate_limits[repo] if now - t < 3600]
    if len(_rate_limits[repo]) >= _MAX_ACCEPTS_PER_HOUR:
        return False
    _rate_limits[repo].append(now)
    return True


def _validate_entry(entry: dict) -> tuple[dict | None, str | None]:
    """Validate a single acceptance entry. Returns (validated, error)."""
    if not isinstance(entry, dict):
        return None, "entry must be a dict"

    key = entry.get("key", "")
    if not isinstance(key, str) or not _KEY_RE.match(key):
        return None, f"invalid key format: {key!r} (expected family:metric)"

    family = entry.get("family", "")
    metric = entry.get("metric", "")
    if not isinstance(family, str) or not isinstance(metric, str):
        return None, "family and metric must be strings"
    if f"{family}:{metric}" != key:
        return None, f"key {key!r} doesn't match family:metric"

    validated = {"key": key, "family": family, "metric": metric}

    reason = entry.get("reason", "")
    if reason:
        safe, err = _check_text_safe(reason, "reason")
        if err:
            return None, err
        validated["reason"] = safe
    else:
        validated["reason"] = ""

    accepted_by = entry.get("accepted_by", "")
    if accepted_by:
        safe, err = _check_text_safe(accepted_by, "accepted_by", max_len=100)
        if err:
            return None, err
        validated["accepted_by"] = safe
    else:
        validated["accepted_by"] = ""

    accepted_at = entry.get("accepted_at", "")
    if accepted_at:
        if not isinstance(accepted_at, str) or len(accepted_at) > 50:
            return None, "accepted_at: invalid"
        validated["accepted_at"] = accepted_at

    return validated, None


# ── Handler ──

class handler(BaseHTTPRequestHandler):
    """Acceptance webhook: store and retrieve permanent acceptances."""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """Retrieve acceptances for a repo."""
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            repo = params.get("repo", [None])[0]

            if not repo:
                return self._json({"error": "Missing ?repo= parameter"}, 400)

            # Validate repo format (owner/name)
            if not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", repo):
                return self._json({"error": "Invalid repo format"}, 400)

            key = _redis_key(repo)
            data = _redis_get(key)

            if data is None:
                return self._json({"repo": repo, "entries": []})

            _axiom_send({
                "type": "accept_get",
                "repo_hash": hashlib.sha256(repo.encode("utf-8")).hexdigest()[:8],
                "entry_count": len(data.get("entries", [])),
                "timestamp": time.time(),
            })

            self._json({"repo": repo, "entries": data.get("entries", [])})
        except Exception:
            self._json({"error": "Internal server error"}, 500)

    def do_POST(self):
        """Store acceptances for a repo."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > _MAX_PAYLOAD_SIZE:
                return self._json({"error": "Payload too large"}, 413)

            raw = self.rfile.read(length)
            if len(raw) > _MAX_PAYLOAD_SIZE:
                return self._json({"error": "Payload too large"}, 413)

            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            return self._json({"error": "Invalid JSON"}, 400)

        repo = data.get("repo", "")
        if not isinstance(repo, str) or not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", repo):
            return self._json({"error": "Invalid or missing repo"}, 400)

        signature = data.get("signature", "")
        if not isinstance(signature, str) or not _verify_signature(repo, signature):
            return self._json({"error": "Invalid signature"}, 403)

        if not _check_rate_limit(repo):
            return self._json({"error": "Rate limit exceeded"}, 429)

        entries = data.get("entries", [])
        if not isinstance(entries, list):
            return self._json({"error": "entries must be a list"}, 400)

        if len(entries) > _MAX_ENTRIES:
            return self._json({"error": f"Too many entries (max {_MAX_ENTRIES})"}, 400)

        # Validate all entries
        validated = []
        errors = []
        for i, e in enumerate(entries):
            v, err = _validate_entry(e)
            if err:
                errors.append(f"entry[{i}]: {err}")
            else:
                validated.append(v)

        if not validated and errors:
            return self._json({"error": "All entries rejected", "details": errors}, 400)

        # Merge into stored data
        key = _redis_key(repo)
        stored = _redis_get(key) or {"repo": repo, "entries": []}
        existing_keys = {e["key"] for e in stored.get("entries", [])}

        added = 0
        for v in validated:
            if v["key"] not in existing_keys:
                stored.setdefault("entries", []).append(v)
                existing_keys.add(v["key"])
                added += 1

        if not _redis_set(key, stored):
            return self._json({"error": "Storage write failed"}, 500)

        _axiom_send({
            "type": "accept_post",
            "repo_hash": hashlib.sha256(repo.encode("utf-8")).hexdigest()[:8],
            "added": added,
            "rejected": len(errors),
            "total": len(stored.get("entries", [])),
            "timestamp": time.time(),
        })

        result = {"accepted": added, "total": len(stored.get("entries", []))}
        if errors:
            result["rejected"] = len(errors)
            result["errors"] = errors
        self._json(result)

    def _json(self, body, status=200):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass
