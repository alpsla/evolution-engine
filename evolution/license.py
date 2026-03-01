"""
License System — Open-core feature gating.

Free tier: git + dependency + config analysis, local KB, template explanations.
Pro tier: CI/deployment/security adapters, LLM features, community sync.

License is checked via:
  1. EVO_LICENSE_KEY environment variable
  2. ~/.evo/license.json file (with server-side activation)
  3. .evo/license.json in repo directory

Key validation modes:
  - Cython builds: signing key embedded at compile time → offline HMAC validation
  - Pure-Python:   server-side activation → local integrity token
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# Build marker — replaced with production key during Cython compilation.
# In pure-Python wheels this stays as the placeholder; _get_signing_key()
# will return None and the CLI falls back to server-side activation.
_EMBEDDED_SIGNING_KEY = b"__EVO_SIGNING_KEY_PLACEHOLDER__"

_ACTIVATION_URL = "https://codequal.dev/api/activate-license"
_HEARTBEAT_URL = "https://codequal.dev/api/license-check"
_HEARTBEAT_INTERVAL_DAYS = 7
_HEARTBEAT_GRACE_DAYS = 14


def _is_test_environment() -> bool:
    """Check if running in a test environment (pytest or EVO_TEST_MODE)."""
    return "_pytest" in sys.modules or os.environ.get("EVO_TEST_MODE") == "1"


def _get_signing_key() -> Optional[bytes]:
    """Get the license signing key if available.

    Priority: environment variable > embedded key (Cython builds).
    Returns None for pure-Python installs without the env var — those
    must use server-side activation instead.
    """
    custom = os.environ.get("EVO_LICENSE_SIGNING_KEY")
    if custom:
        return custom.encode("utf-8") if isinstance(custom, str) else custom
    if _EMBEDDED_SIGNING_KEY != b"__EVO_SIGNING_KEY_PLACEHOLDER__":
        return _EMBEDDED_SIGNING_KEY
    return None


class ProFeatureError(Exception):
    """Raised when attempting to use a Pro feature without a valid license."""

    def __init__(self, feature_name: str):
        self.feature_name = feature_name
        message = (
            f"\n\n{feature_name} requires Evolution Engine Pro.\n\n"
            "Upgrade to unlock:\n"
            "  - 20+ adapters across 9 signal families\n"
            "  - CI, deployment, security & error tracking\n"
            "  - AI investigation & fix loop\n"
            "  - Git hooks & CI workflow actions\n"
            "  - GitHub Action & GitLab CI integration\n\n"
            "Visit https://codequal.dev/#pricing or set EVO_LICENSE_KEY\n"
        )
        super().__init__(message)


@dataclass
class License:
    """Represents the current license state."""

    tier: str  # "free" or "pro"
    valid: bool
    source: str  # "default", "env", "file", "activated", "trial"
    email: Optional[str] = None
    issued: Optional[str] = None
    expires: Optional[str] = None
    error: Optional[str] = None

    @property
    def features(self) -> dict[str, bool]:
        """Return a dict of feature name -> enabled status."""
        if not self.valid or self.tier != "pro":
            return {
                "tier1_adapters": True,  # git, dependency, config
                "tier2_adapters": False,  # CI, deployment, security
                "llm_explanations": False,
                "llm_patterns": False,
                "local_kb": True,
                "community_sync": False,
            }
        return {
            "tier1_adapters": True,
            "tier2_adapters": True,
            "llm_explanations": True,
            "llm_patterns": True,
            "local_kb": True,
            "community_sync": True,
        }

    def is_valid(self) -> bool:
        """Check if the license is valid (any tier)."""
        return self.valid

    def is_pro(self) -> bool:
        """Check if this is a valid Pro license."""
        return self.valid and self.tier == "pro"


# ─── Activation integrity ───


def _compute_activation_token(key: str, tier: str, email_hash: str, issued: str) -> str:
    """Compute a local integrity token for an activated license.

    This detects casual tampering of the license.json file. It is NOT
    a substitute for HMAC verification — the real validation happened
    server-side during activation.
    """
    data = f"{key}:{tier}:{email_hash}:{issued}:evo-activation-v1"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:32]


def _validate_activation(data: dict) -> Optional[dict]:
    """Validate an activated license stored in license.json.

    Returns the license data dict if the activation token matches,
    None otherwise.
    """
    key = data.get("license_key", "")
    tier = data.get("tier", "")
    email_hash = data.get("email_hash", "")
    issued = data.get("issued", "")
    stored_token = data.get("activation_token", "")

    if not all([key, tier, email_hash, issued, stored_token]):
        return None

    expected = _compute_activation_token(key, tier, email_hash, issued)
    if not hmac.compare_digest(stored_token, expected):
        return None

    return {"tier": tier, "email_hash": email_hash, "issued": issued}


def activate_license(key: str, server_url: str = _ACTIVATION_URL) -> dict:
    """Activate a license key via server-side validation.

    Calls the activation endpoint to validate the key's HMAC signature,
    then stores the result locally with an integrity token.

    Args:
        key: The base64-encoded license key.
        server_url: Activation endpoint URL.

    Returns:
        Dict with "success" bool, "tier", "error" etc.
    """
    # First, try local HMAC validation (Cython builds or env var)
    signing_key = _get_signing_key()
    if signing_key:
        local_result = _validate_key(key)
        if local_result:
            _save_activation(key, local_result)
            return {"success": True, "tier": local_result.get("tier", "free"), "source": "local"}

    # Fall back to server-side activation
    try:
        body = json.dumps({"key": key}).encode("utf-8")
        req = urllib.request.Request(
            server_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read().decode("utf-8"))

        if result.get("valid"):
            activation_data = {
                "tier": result["tier"],
                "email_hash": result.get("email_hash", ""),
                "issued": result.get("issued", ""),
            }
            _save_activation(key, activation_data)
            return {"success": True, "tier": result["tier"], "source": "server"}
        else:
            return {"success": False, "error": result.get("error", "Invalid key")}

    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return {"success": False, "error": err_body.get("error", f"Server error ({e.code})")}
        except Exception:
            return {"success": False, "error": f"Server error ({e.code})"}
    except urllib.error.URLError:
        return {"success": False, "error": "Cannot reach activation server. Check your internet connection."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _save_activation(key: str, license_data: dict) -> None:
    """Save activation result to ~/.evo/license.json with integrity token."""
    tier = license_data.get("tier", "free")
    email_hash = license_data.get("email_hash", "")
    issued = license_data.get("issued", "")

    token = _compute_activation_token(key, tier, email_hash, issued)

    evo_home = Path.home() / ".evo"
    evo_home.mkdir(exist_ok=True)
    license_file = evo_home / "license.json"

    data = {
        "license_key": key,
        "tier": tier,
        "email_hash": email_hash,
        "issued": issued,
        "activation_token": token,
    }
    license_file.write_text(json.dumps(data, indent=2))
    try:
        license_file.chmod(0o600)
    except OSError:
        pass


# ─── Heartbeat (server-side subscription verification) ───


def _heartbeat_check(license_key: str) -> Optional[str]:
    """Check license subscription status with the server.

    Returns the status string ("active", "cancelled", "past_due", "revoked")
    or None if the check failed (network error, server down, etc.).

    This is the safety net: even if a key has no expiry and passes local
    HMAC validation, the server knows whether the subscription is still active.
    """
    try:
        body = json.dumps({"key": license_key}).encode("utf-8")
        req = urllib.request.Request(
            _HEARTBEAT_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("status")
    except Exception:
        return None


def _get_heartbeat_path() -> Path:
    return Path.home() / ".evo" / "license_check.json"


def _read_heartbeat_cache() -> dict:
    """Read cached heartbeat state."""
    path = _get_heartbeat_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_heartbeat_cache(data: dict) -> None:
    """Write heartbeat cache."""
    path = _get_heartbeat_path()
    try:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        path.chmod(0o600)
    except OSError:
        pass


def _apply_heartbeat(license_obj: License, license_key: str) -> License:
    """Apply server-side heartbeat check to a Pro license.

    Called after local validation succeeds. Checks every 7 days whether
    the subscription is still active. If cancelled/revoked, degrades to
    free tier. If past_due, allows a 14-day grace period.

    If the server is unreachable, a 14-day grace period from the last
    successful check is applied.
    """
    if not license_obj.is_pro():
        return license_obj

    # Skip heartbeat in test environments
    if _is_test_environment():
        return license_obj

    # Skip if DO_NOT_TRACK is set (respect privacy)
    if os.environ.get("DO_NOT_TRACK") == "1":
        return license_obj

    cache = _read_heartbeat_cache()
    now = datetime.now()

    # Check if we need to call the server
    last_checked_str = cache.get("last_checked")
    if last_checked_str:
        try:
            last_checked = datetime.fromisoformat(last_checked_str)
            days_since = (now - last_checked).days
            if days_since < _HEARTBEAT_INTERVAL_DAYS:
                # Recently checked — use cached status
                cached_status = cache.get("status", "active")
                return _apply_cached_status(license_obj, cached_status, cache)
        except (ValueError, TypeError):
            pass

    # Time to check with the server
    server_status = _heartbeat_check(license_key)

    if server_status is not None:
        # Server responded — update cache
        cache_data = {
            "status": server_status,
            "last_checked": now.isoformat(),
            "last_success": now.isoformat(),
        }
        if server_status == "past_due":
            # Preserve existing grace_start or set a new one
            cache_data["grace_start"] = cache.get("grace_start", now.isoformat())
        # active/cancelled/revoked: no grace_start needed

        _write_heartbeat_cache(cache_data)
        return _apply_cached_status(license_obj, server_status, cache_data)
    else:
        # Server unreachable — apply grace period from last success
        last_success_str = cache.get("last_success")
        if last_success_str:
            try:
                last_success = datetime.fromisoformat(last_success_str)
                grace_days = (now - last_success).days
                if grace_days > _HEARTBEAT_GRACE_DAYS:
                    # Grace period expired — degrade to free
                    return License(
                        tier="free", valid=True, source="default",
                        error="License check failed — grace period expired",
                    )
            except (ValueError, TypeError):
                pass

        # No last success recorded or within grace — allow
        return license_obj


def _apply_cached_status(license_obj: License, status: str, cache: dict) -> License:
    """Apply a cached heartbeat status to a license."""
    if status in ("cancelled", "revoked"):
        return License(
            tier="free", valid=True, source="default",
            error=f"Subscription {status} — license deactivated",
        )

    if status == "past_due":
        # Allow a grace period for payment recovery
        grace_start_str = cache.get("grace_start")
        if grace_start_str:
            try:
                grace_start = datetime.fromisoformat(grace_start_str)
                grace_days = (datetime.now() - grace_start).days
                if grace_days > _HEARTBEAT_GRACE_DAYS:
                    return License(
                        tier="free", valid=True, source="default",
                        error="Payment past due — grace period expired",
                    )
            except (ValueError, TypeError):
                pass
        # Within grace period — keep Pro
        return license_obj

    # "active" or "unknown" — keep Pro
    return license_obj


# ─── License retrieval ───


def get_license(repo_path: Optional[str] = None) -> License:
    """Get the current license status.

    Checks in order:
      1. EVO_LICENSE_KEY environment variable (HMAC or trial)
      2. ~/.evo/license.json (activated or HMAC-validated)
      3. <repo_path>/.evo/license.json (activated or HMAC-validated)

    Returns:
        License object (defaults to free tier if no license found).
    """
    # 1. Check environment variable
    env_key = os.environ.get("EVO_LICENSE_KEY")
    if env_key:
        # Test-only trial key — only works inside pytest
        if env_key == "pro-trial" and _is_test_environment():
            return License(
                tier="pro",
                valid=True,
                source="trial",
                email="trial@example.com",
                issued=datetime.now().isoformat(),
                expires="2099-12-31",
            )

        # Validate signed key (requires signing key)
        license_data = _validate_key(env_key)
        if license_data:
            lic = License(
                tier=license_data.get("tier", "free"),
                valid=True,
                source="env",
                email=license_data.get("email") or license_data.get("email_hash"),
                issued=license_data.get("issued"),
                expires=license_data.get("expires"),
            )
            return _apply_heartbeat(lic, env_key)

    # 2. Check ~/.evo/license.json
    home_license = Path.home() / ".evo" / "license.json"
    result, key = _check_license_file(home_license)
    if result:
        return _apply_heartbeat(result, key) if key else result

    # 3. Check <repo_path>/.evo/license.json
    if repo_path:
        repo_license = Path(repo_path) / ".evo" / "license.json"
        result, key = _check_license_file(repo_license)
        if result:
            return _apply_heartbeat(result, key) if key else result

    # Default: free tier
    return License(tier="free", valid=True, source="default")


def _check_license_file(license_file: Path) -> tuple[Optional[License], Optional[str]]:
    """Check a license.json file for a valid license.

    Supports both:
      - Activated licenses (with activation_token)
      - HMAC-validated keys (Cython builds with embedded signing key)
      - Test trial keys (pytest only)

    Returns:
        Tuple of (License or None, license_key string or None).
        The key is returned so the heartbeat can use it.
    """
    if not license_file.exists():
        return None, None

    try:
        data = json.loads(license_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None, None

    key = data.get("license_key")
    if not key:
        return None, None

    # Test-only trial key
    if key == "pro-trial" and _is_test_environment():
        return License(
            tier="pro",
            valid=True,
            source="trial",
            email="trial@example.com",
            issued=datetime.now().isoformat(),
            expires="2099-12-31",
        ), key

    # Check for server-side activation (has activation_token)
    if "activation_token" in data:
        validated = _validate_activation(data)
        if validated:
            return License(
                tier=validated["tier"],
                valid=True,
                source="activated",
                email=validated.get("email_hash"),
                issued=validated.get("issued"),
            ), key

    # Try HMAC validation (Cython builds or env var with signing key)
    license_data = _validate_key(key)
    if license_data:
        return License(
            tier=license_data.get("tier", "free"),
            valid=True,
            source="file",
            email=license_data.get("email") or license_data.get("email_hash"),
            issued=license_data.get("issued"),
            expires=license_data.get("expires"),
        ), key

    return None, None


def is_pro(repo_path: Optional[str] = None) -> bool:
    """Quick check if the current license is Pro tier."""
    return get_license(repo_path).is_pro()


def require_pro(feature_name: str, repo_path: Optional[str] = None):
    """Raise ProFeatureError if the current license is not Pro tier."""
    if not is_pro(repo_path):
        raise ProFeatureError(feature_name)


# ─── Key validation ───


def _validate_key(key: str) -> Optional[dict]:
    """Validate a signed license key using HMAC.

    Requires a signing key (from env var or embedded in Cython build).
    Returns None if no signing key is available or signature is invalid.

    Format: base64(json_payload + "." + hmac_signature)
    """
    signing_key = _get_signing_key()
    if signing_key is None:
        return None

    try:
        decoded = base64.b64decode(key).decode("utf-8")
        if "." not in decoded:
            return None

        payload_str, signature = decoded.rsplit(".", 1)
        payload = json.loads(payload_str)

        # Verify HMAC signature
        expected_sig = hmac.new(
            signing_key,
            payload_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
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


def generate_key(
    tier: str,
    email: str,
    signing_key: bytes,
    issued: Optional[str] = None,
    expires: Optional[str] = None,
) -> str:
    """Generate a signed license key.

    Args:
        tier: "free" or "pro"
        email: Licensee email
        signing_key: HMAC signing key bytes (required — no default).
        issued: ISO format date (defaults to now)
        expires: ISO format date (optional)

    Returns:
        Base64-encoded signed license key.
    """
    email_hash = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()[:16]
    payload = {
        "tier": tier,
        "email_hash": email_hash,
        "issued": issued or datetime.now().isoformat(),
    }
    if expires:
        payload["expires"] = expires

    payload_str = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        signing_key,
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    signed = f"{payload_str}.{signature}"
    return base64.b64encode(signed.encode("utf-8")).decode("utf-8")
