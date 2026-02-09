"""
KB Security — Pattern validation and integrity checks.

Prevents injection attacks when importing community/universal patterns.
All patterns entering the KB from external sources MUST pass through
validate_pattern() before storage.

Threat model:
  1. Malicious description fields (XSS, template injection, shell injection)
  2. Oversized payloads (DoS via huge strings or lists)
  3. Fingerprint spoofing (crafted fingerprint to overwrite local patterns)
  4. Path traversal in field values
  5. Type confusion (string where int expected, nested dicts as bombs)

All community/universal patterns are treated as untrusted input.
"""

import hashlib
import json
import re
from typing import Optional


# ─────────────────── Constants ───────────────────

# Max lengths for string fields
MAX_FINGERPRINT_LEN = 64
MAX_DESCRIPTION_LEN = 1000
MAX_METRIC_NAME_LEN = 100
MAX_SOURCE_NAME_LEN = 50
MAX_SIGNAL_REFS = 100
MAX_SOURCES = 20
MAX_METRICS = 20

# Allowed scope values for imported patterns
ALLOWED_IMPORT_SCOPES = {"community", "universal"}

# Allowed pattern types
ALLOWED_PATTERN_TYPES = {"co_occurrence", "temporal_sequence", "threshold_breach"}

# Allowed discovery methods
ALLOWED_DISCOVERY_METHODS = {"statistical", "semantic", "hybrid"}

# Allowed confidence tiers
ALLOWED_CONFIDENCE_TIERS = {"statistical", "speculative", "confirmed"}

# Dangerous patterns in text fields
_DANGEROUS_PATTERNS = [
    re.compile(r"<script", re.IGNORECASE),           # XSS
    re.compile(r"javascript:", re.IGNORECASE),         # XSS via protocol
    re.compile(r"\{\{.*\}\}"),                         # Template injection (Jinja2, etc.)
    re.compile(r"\$\{.*\}"),                           # Template injection (JS template literal)
    re.compile(r"`.*`"),                                # Backtick execution
    re.compile(r";\s*(rm|del|drop|exec|eval)\b", re.IGNORECASE),  # Shell/SQL injection
    re.compile(r"\.\./"),                               # Path traversal
    re.compile(r"\\\\"),                                # UNC path
    re.compile(r"file://", re.IGNORECASE),             # File protocol
    re.compile(r"data:", re.IGNORECASE),               # Data URI
]

# Allowed characters in fingerprint (hex only)
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]+$")

# Allowed characters in metric and source names
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-./]+$")


# ─────────────────── Validation Errors ───────────────────


class PatternValidationError(ValueError):
    """Raised when a pattern fails security validation."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"Pattern validation failed: {field} — {reason}")


# ─────────────────── Core Validator ───────────────────


def _check_text_safe(value: str, field_name: str, max_len: int) -> str:
    """Validate a text field for dangerous content.

    Returns the sanitized string (stripped of leading/trailing whitespace).
    Raises PatternValidationError if dangerous patterns are found.
    """
    if not isinstance(value, str):
        raise PatternValidationError(field_name, f"expected string, got {type(value).__name__}")

    if len(value) > max_len:
        raise PatternValidationError(field_name, f"exceeds max length {max_len}")

    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(value):
            raise PatternValidationError(
                field_name,
                f"contains dangerous content matching {pattern.pattern!r}"
            )

    return value.strip()


def _check_name(value: str, field_name: str, max_len: int) -> str:
    """Validate a name field (metric name, source name)."""
    value = _check_text_safe(value, field_name, max_len)
    if not _SAFE_NAME_RE.match(value):
        raise PatternValidationError(
            field_name,
            f"contains invalid characters (allowed: a-z, A-Z, 0-9, _, -, ., /)"
        )
    return value


def validate_pattern(pattern: dict, *, require_external_scope: bool = True) -> dict:
    """Validate an externally-sourced pattern before KB import.

    Args:
        pattern: Pattern dict from community/universal source.
        require_external_scope: If True, rejects 'local' scope (default for imports).

    Returns:
        Sanitized pattern dict with validated fields.

    Raises:
        PatternValidationError: If any field fails validation.
    """
    if not isinstance(pattern, dict):
        raise PatternValidationError("pattern", "must be a dict")

    validated = {}

    # ── Required fields ──

    # fingerprint: hex string
    fp = pattern.get("fingerprint")
    if not fp or not isinstance(fp, str):
        raise PatternValidationError("fingerprint", "required hex string")
    if len(fp) > MAX_FINGERPRINT_LEN:
        raise PatternValidationError("fingerprint", f"exceeds max length {MAX_FINGERPRINT_LEN}")
    if not _FINGERPRINT_RE.match(fp):
        raise PatternValidationError("fingerprint", "must be lowercase hex")
    validated["fingerprint"] = fp

    # scope
    scope = pattern.get("scope", "community")
    if require_external_scope and scope not in ALLOWED_IMPORT_SCOPES:
        raise PatternValidationError("scope", f"must be one of {ALLOWED_IMPORT_SCOPES} for imports")
    validated["scope"] = scope

    # pattern_type
    ptype = pattern.get("pattern_type", "")
    if ptype not in ALLOWED_PATTERN_TYPES:
        raise PatternValidationError("pattern_type", f"must be one of {ALLOWED_PATTERN_TYPES}")
    validated["pattern_type"] = ptype

    # discovery_method
    method = pattern.get("discovery_method", "")
    if method not in ALLOWED_DISCOVERY_METHODS:
        raise PatternValidationError("discovery_method", f"must be one of {ALLOWED_DISCOVERY_METHODS}")
    validated["discovery_method"] = method

    # sources: list of safe names
    sources = pattern.get("sources", [])
    if not isinstance(sources, list) or len(sources) == 0:
        raise PatternValidationError("sources", "required non-empty list")
    if len(sources) > MAX_SOURCES:
        raise PatternValidationError("sources", f"exceeds max count {MAX_SOURCES}")
    validated["sources"] = [_check_name(s, "sources[]", MAX_SOURCE_NAME_LEN) for s in sources]

    # metrics: list of safe names
    metrics = pattern.get("metrics", [])
    if not isinstance(metrics, list) or len(metrics) == 0:
        raise PatternValidationError("metrics", "required non-empty list")
    if len(metrics) > MAX_METRICS:
        raise PatternValidationError("metrics", f"exceeds max count {MAX_METRICS}")
    validated["metrics"] = [_check_name(m, "metrics[]", MAX_METRIC_NAME_LEN) for m in metrics]

    # ── Optional text fields ──

    desc_stat = pattern.get("description_statistical")
    if desc_stat is not None:
        validated["description_statistical"] = _check_text_safe(
            desc_stat, "description_statistical", MAX_DESCRIPTION_LEN
        )

    desc_sem = pattern.get("description_semantic")
    if desc_sem is not None:
        validated["description_semantic"] = _check_text_safe(
            desc_sem, "description_semantic", MAX_DESCRIPTION_LEN
        )

    # ── Numeric fields (strict type check) ──

    corr = pattern.get("correlation_strength")
    if corr is not None:
        if not isinstance(corr, (int, float)):
            raise PatternValidationError("correlation_strength", "must be numeric")
        if not -1.0 <= corr <= 1.0:
            raise PatternValidationError("correlation_strength", "must be in [-1, 1]")
        validated["correlation_strength"] = round(float(corr), 4)

    occ = pattern.get("occurrence_count")
    if occ is not None:
        if not isinstance(occ, int) or occ < 0:
            raise PatternValidationError("occurrence_count", "must be non-negative integer")
        validated["occurrence_count"] = occ

    # ── Timestamp fields ──

    for ts_field in ("first_seen", "last_seen"):
        ts = pattern.get(ts_field)
        if ts is not None:
            validated[ts_field] = _check_text_safe(ts, ts_field, 30)

    # ── Confidence fields ──

    tier = pattern.get("confidence_tier")
    if tier is not None:
        if tier not in ALLOWED_CONFIDENCE_TIERS:
            raise PatternValidationError("confidence_tier", f"must be one of {ALLOWED_CONFIDENCE_TIERS}")
        validated["confidence_tier"] = tier

    status = pattern.get("confidence_status")
    if status is not None:
        validated["confidence_status"] = _check_text_safe(status, "confidence_status", 50)

    # ── Signal refs: stripped on import (never trust external refs) ──
    # External patterns should NOT carry signal_refs as they could be
    # used for reference injection. We strip them.
    validated["signal_refs"] = []

    return validated


def verify_fingerprint_integrity(pattern: dict) -> bool:
    """Verify that a pattern's fingerprint matches its content.

    For community patterns, the fingerprint should be derivable from
    the (sources, metrics, direction) tuple. This prevents spoofing.

    Returns True if the fingerprint is plausibly valid.
    Note: We can't fully re-derive the fingerprint without direction info,
    so this is a format check + collision resistance check.
    """
    fp = pattern.get("fingerprint", "")
    if not fp or not _FINGERPRINT_RE.match(fp):
        return False
    if len(fp) < 8:
        return False
    return True


def compute_import_digest(pattern: dict) -> str:
    """Compute a content-addressable digest for an imported pattern.

    Used to detect duplicates and verify integrity during sync.
    """
    canonical = {
        "fingerprint": pattern.get("fingerprint", ""),
        "sources": sorted(pattern.get("sources", [])),
        "metrics": sorted(pattern.get("metrics", [])),
        "pattern_type": pattern.get("pattern_type", ""),
        "correlation_strength": pattern.get("correlation_strength"),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
