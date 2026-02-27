"""
Vercel serverless function: Pattern registry handler.

POST /api/patterns — Accept pattern pushes from CLI (kb_sync.push)
GET  /api/patterns — Serve aggregated patterns (kb_sync.pull)

Storage: Upstash Redis (Vercel KV) — single JSON blob at key evo:patterns.
Env vars: UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
"""

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# ─── Constants ───

_MAX_PAYLOAD_SIZE = 102400  # 100KB
_MAX_PUSHES_PER_HOUR = 10
_REDIS_KEY = "evo:patterns"

# Validation constants
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{8,64}$")
_INSTANCE_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-./]+$")
_ALLOWED_PATTERN_TYPES = {"co_occurrence", "temporal_sequence", "threshold_breach"}
_ALLOWED_DISCOVERY_METHODS = {"statistical", "semantic", "hybrid"}
_ALLOWED_CONFIDENCE_TIERS = {"statistical", "speculative", "confirmed"}
_MAX_DESCRIPTION_LEN = 1000
_MAX_SOURCES = 20
_MAX_METRICS = 20
_MAX_ATTESTATIONS = 50

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


# ─── Axiom Logging ───

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


# ─── Upstash Redis ───

def _redis_get() -> dict:
    """Read the patterns blob from Upstash Redis."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return {"patterns": {}, "submitters": {}}

    try:
        req = urllib.request.Request(
            f"{url}/get/{_REDIS_KEY}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode("utf-8"))
        result = data.get("result")
        if result is None:
            return {"patterns": {}, "submitters": {}}
        return json.loads(result)
    except Exception:
        return {"patterns": {}, "submitters": {}}


def _redis_set(data: dict) -> bool:
    """Write the patterns blob to Upstash Redis."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return False

    try:
        payload = json.dumps(["SET", _REDIS_KEY, json.dumps(data)]).encode("utf-8")
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


# ─── Validation ───

def _check_text_safe(value, field_name, max_len=_MAX_DESCRIPTION_LEN):
    """Validate a text field for dangerous content."""
    if not isinstance(value, str):
        return None, f"{field_name}: expected string"
    if len(value) > max_len:
        return None, f"{field_name}: exceeds max length {max_len}"
    for pat in _DANGEROUS_PATTERNS:
        if pat.search(value):
            return None, f"{field_name}: contains dangerous content"
    return value.strip(), None


def _validate_pattern(pattern: dict) -> tuple[dict | None, str | None]:
    """Validate a single pattern dict. Returns (validated, error)."""
    if not isinstance(pattern, dict):
        return None, "pattern must be a dict"

    validated = {}

    # fingerprint
    fp = pattern.get("fingerprint")
    if not isinstance(fp, str) or not _FINGERPRINT_RE.match(fp):
        return None, "invalid fingerprint (must be 8-64 char hex)"
    validated["fingerprint"] = fp

    # pattern_type
    ptype = pattern.get("pattern_type", "")
    if ptype not in _ALLOWED_PATTERN_TYPES:
        return None, f"invalid pattern_type (must be one of {_ALLOWED_PATTERN_TYPES})"
    validated["pattern_type"] = ptype

    # discovery_method
    method = pattern.get("discovery_method", "")
    if method not in _ALLOWED_DISCOVERY_METHODS:
        return None, f"invalid discovery_method (must be one of {_ALLOWED_DISCOVERY_METHODS})"
    validated["discovery_method"] = method

    # sources
    sources = pattern.get("sources", [])
    if not isinstance(sources, list) or len(sources) == 0:
        return None, "sources: required non-empty list"
    if len(sources) > _MAX_SOURCES:
        return None, f"sources: exceeds max count {_MAX_SOURCES}"
    safe_sources = []
    for s in sources:
        if not isinstance(s, str) or not _SAFE_NAME_RE.match(s) or len(s) > 100:
            return None, f"sources: invalid name '{s}'"
        safe_sources.append(s)
    validated["sources"] = safe_sources

    # metrics
    metrics = pattern.get("metrics", [])
    if not isinstance(metrics, list) or len(metrics) == 0:
        return None, "metrics: required non-empty list"
    if len(metrics) > _MAX_METRICS:
        return None, f"metrics: exceeds max count {_MAX_METRICS}"
    safe_metrics = []
    for m in metrics:
        if not isinstance(m, str) or not _SAFE_NAME_RE.match(m) or len(m) > 100:
            return None, f"metrics: invalid name '{m}'"
        safe_metrics.append(m)
    validated["metrics"] = safe_metrics

    # description_statistical (optional)
    desc_stat = pattern.get("description_statistical")
    if desc_stat is not None:
        val, err = _check_text_safe(desc_stat, "description_statistical")
        if err:
            return None, err
        validated["description_statistical"] = val

    # description_semantic (optional)
    desc_sem = pattern.get("description_semantic")
    if desc_sem is not None:
        val, err = _check_text_safe(desc_sem, "description_semantic")
        if err:
            return None, err
        validated["description_semantic"] = val

    # correlation_strength (optional)
    corr = pattern.get("correlation_strength")
    if corr is not None:
        if not isinstance(corr, (int, float)):
            return None, "correlation_strength: must be numeric"
        if not -5.0 <= corr <= 5.0:
            return None, "correlation_strength: must be in [-5, 5]"
        validated["correlation_strength"] = round(float(corr), 4)

    # occurrence_count (optional)
    occ = pattern.get("occurrence_count")
    if occ is not None:
        if not isinstance(occ, int) or occ < 0:
            return None, "occurrence_count: must be non-negative integer"
        validated["occurrence_count"] = occ

    # confidence_tier (optional)
    tier = pattern.get("confidence_tier")
    if tier is not None:
        if tier not in _ALLOWED_CONFIDENCE_TIERS:
            return None, f"confidence_tier: must be one of {_ALLOWED_CONFIDENCE_TIERS}"
        validated["confidence_tier"] = tier

    # scope (optional, default community)
    scope = pattern.get("scope", "community")
    if not isinstance(scope, str) or len(scope) > 50:
        return None, "scope: invalid"
    validated["scope"] = scope

    # attestations (optional)
    attestations = pattern.get("attestations", [])
    if isinstance(attestations, list):
        validated["attestations"] = _validate_attestations(attestations)
    else:
        validated["attestations"] = []

    return validated, None


def _validate_attestations(attestations: list) -> list[dict]:
    """Validate attestation records."""
    valid = []
    seen_ids = set()

    for att in attestations:
        if not isinstance(att, dict):
            continue
        if len(valid) >= _MAX_ATTESTATIONS:
            break

        iid = att.get("instance_id", "")
        sig = att.get("signature", "")
        ts = att.get("timestamp")

        if not isinstance(iid, str) or not _INSTANCE_ID_RE.match(iid):
            continue
        if not isinstance(sig, str) or len(sig) != 64 or not re.match(r"^[0-9a-f]+$", sig):
            continue
        if not isinstance(ts, (int, float)) or ts < 0 or ts > time.time() + 3600:
            continue

        if iid in seen_ids:
            continue
        seen_ids.add(iid)

        ver = att.get("ee_version", "unknown")
        if not isinstance(ver, str) or len(ver) > 20:
            ver = "unknown"

        valid.append({
            "instance_id": iid,
            "signature": sig,
            "timestamp": int(ts),
            "ee_version": ver,
        })

    return valid


# ─── Rate Limiting ───

def _check_rate_limit(instance_id: str) -> bool:
    """Check if instance is within rate limit. Returns True if allowed."""
    now = time.time()
    if instance_id not in _rate_limits:
        _rate_limits[instance_id] = []
    _rate_limits[instance_id] = [t for t in _rate_limits[instance_id] if now - t < 3600]
    if len(_rate_limits[instance_id]) >= _MAX_PUSHES_PER_HOUR:
        return False
    _rate_limits[instance_id].append(now)
    return True


# ─── Merge Logic ───

def _merge_pattern(store: dict, pattern: dict, instance_id: str) -> None:
    """Merge a validated pattern into the store."""
    fp = pattern["fingerprint"]
    now = datetime.now(timezone.utc).isoformat()

    if "patterns" not in store:
        store["patterns"] = {}
    if "submitters" not in store:
        store["submitters"] = {}

    if fp not in store["patterns"]:
        # New pattern
        pattern["independent_count"] = 1
        pattern["last_updated"] = now
        store["patterns"][fp] = pattern
        store["submitters"][fp] = [instance_id]
    else:
        # Existing pattern — merge
        existing = store["patterns"][fp]

        # Merge attestations (deduplicate by instance_id)
        existing_atts = existing.get("attestations", [])
        new_atts = pattern.get("attestations", [])
        seen_ids = {a["instance_id"] for a in existing_atts}
        for att in new_atts:
            if att["instance_id"] not in seen_ids and len(existing_atts) < _MAX_ATTESTATIONS:
                existing_atts.append(att)
                seen_ids.add(att["instance_id"])
        existing["attestations"] = existing_atts

        # Update occurrence_count (take max)
        if "occurrence_count" in pattern:
            existing["occurrence_count"] = max(
                existing.get("occurrence_count", 0),
                pattern.get("occurrence_count", 0),
            )

        # Track independent submitters
        submitters = store["submitters"].get(fp, [])
        if instance_id not in submitters:
            submitters.append(instance_id)
            existing["independent_count"] = len(submitters)
        store["submitters"][fp] = submitters

        # Update timestamp
        existing["last_updated"] = now

        # Update confidence tier based on independent count
        if existing["independent_count"] >= 2:
            existing["confidence_tier"] = "confirmed"

        store["patterns"][fp] = existing


# ─── Handler ───

class handler(BaseHTTPRequestHandler):
    """Pattern registry: push and pull community patterns."""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """Serve aggregated patterns, optionally filtered by ?since=ISO8601."""
        try:
            store = _redis_get()
            patterns = list(store.get("patterns", {}).values())

            # Parse ?since parameter
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            since = params.get("since", [None])[0]

            if since:
                patterns = [
                    p for p in patterns
                    if p.get("last_updated", "") >= since
                ]

            # Count patterns that have met quorum (2+ independent submitters)
            quorum_met = sum(1 for p in patterns if p.get("independent_count", 0) >= 2)
            # Collect unique source families
            pattern_families = sorted(set(
                src for p in patterns for src in p.get("sources", [])
            ))

            _axiom_send({
                "type": "pattern_pull",
                "pattern_count": len(patterns),
                "quorum_met_count": quorum_met,
                "pattern_families": pattern_families,
                "since": since,
                "country": self.headers.get("x-vercel-ip-country", ""),
                "timestamp": time.time(),
            })

            self._json({"patterns": patterns})
        except Exception:
            self._json({"error": "Internal server error"}, 500)

    def do_POST(self):
        """Accept pattern push from CLI."""
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

        level = data.get("level")
        if not isinstance(level, int) or level not in (1, 2):
            return self._json({"error": "Invalid level (must be 1 or 2)"}, 400)

        # Level 1: metadata only — just log it
        if level == 1:
            _axiom_send({
                "type": "pattern_push_metadata",
                "metadata": data.get("metadata", {}),
                "timestamp": time.time(),
            })
            return self._json({"accepted": 0})

        # Level 2: full pattern push
        instance_id = data.get("instance_id", "")
        if not isinstance(instance_id, str) or not _INSTANCE_ID_RE.match(instance_id):
            return self._json({"error": "Invalid instance_id (must be 16-char hex)"}, 400)

        if not _check_rate_limit(instance_id):
            return self._json({"error": "Rate limit exceeded"}, 429)

        patterns = data.get("patterns", [])
        if not isinstance(patterns, list):
            return self._json({"error": "patterns must be a list"}, 400)

        # Validate all patterns
        validated = []
        errors = []
        for i, p in enumerate(patterns):
            v, err = _validate_pattern(p)
            if err:
                errors.append(f"pattern[{i}]: {err}")
            else:
                validated.append(v)

        if not validated and errors:
            return self._json({"error": "All patterns rejected", "details": errors}, 400)

        # Merge into store
        store = _redis_get()
        for p in validated:
            _merge_pattern(store, p, instance_id)

        if not _redis_set(store):
            return self._json({"error": "Storage write failed"}, 500)

        # Compute quorum and family stats for the entire store
        all_patterns = list(store.get("patterns", {}).values())
        quorum_met = sum(1 for p in all_patterns if p.get("independent_count", 0) >= 2)
        pattern_families = sorted(set(
            src for p in all_patterns for src in p.get("sources", [])
        ))

        _axiom_send({
            "type": "pattern_push",
            "instance_id": instance_id,
            "accepted": len(validated),
            "rejected": len(errors),
            "total_patterns": len(all_patterns),
            "quorum_met_count": quorum_met,
            "pattern_families": pattern_families,
            "country": self.headers.get("x-vercel-ip-country", ""),
            "timestamp": time.time(),
        })

        result = {"accepted": len(validated)}
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
