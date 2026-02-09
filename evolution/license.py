"""
License System — Open-core feature gating.

Free tier: git + dependency + config analysis, local KB, template explanations.
Pro tier: CI/deployment/security adapters, LLM features, community sync.

License is checked via:
  1. EVO_LICENSE_KEY environment variable
  2. ~/.evo/license.json file
  3. .evo/license.json in repo directory
"""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# Hardcoded signing key (v1 only — will move to proper key management later)
_SIGNING_KEY = b"evo-license-v1-dev-key-replace-in-production"


class ProFeatureError(Exception):
    """Raised when attempting to use a Pro feature without a valid license."""

    def __init__(self, feature_name: str):
        self.feature_name = feature_name
        message = (
            f"\n\n{feature_name} requires Evolution Engine Pro.\n\n"
            "Upgrade to unlock:\n"
            "  - CI, deployment, and security adapters\n"
            "  - LLM-enhanced explanations and semantic patterns\n"
            "  - Community knowledge base sync (coming soon)\n\n"
            "Set EVO_LICENSE_KEY or visit https://evo.dev/pro\n"
        )
        super().__init__(message)


@dataclass
class License:
    """Represents the current license state."""

    tier: str  # "free" or "pro"
    valid: bool
    source: str  # "default", "env", "file", "trial"
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

    def is_pro(self) -> bool:
        """Check if this is a valid Pro license."""
        return self.valid and self.tier == "pro"


def get_license(repo_path: Optional[str] = None) -> License:
    """Get the current license status.

    Checks in order:
      1. EVO_LICENSE_KEY environment variable
      2. ~/.evo/license.json
      3. <repo_path>/.evo/license.json (if repo_path provided)

    Returns:
        License object (defaults to free tier if no license found).
    """
    # 1. Check environment variable
    env_key = os.environ.get("EVO_LICENSE_KEY")
    if env_key:
        # Special trial key
        if env_key == "pro-trial":
            return License(
                tier="pro",
                valid=True,
                source="trial",
                email="trial@example.com",
                issued=datetime.now().isoformat(),
                expires="2099-12-31",
            )

        # Validate signed key
        license_data = _validate_key(env_key)
        if license_data:
            return License(
                tier=license_data.get("tier", "free"),
                valid=True,
                source="env",
                email=license_data.get("email"),
                issued=license_data.get("issued"),
                expires=license_data.get("expires"),
            )

    # 2. Check ~/.evo/license.json
    home_license = Path.home() / ".evo" / "license.json"
    if home_license.exists():
        try:
            data = json.loads(home_license.read_text())
            key = data.get("license_key")
            if key:
                if key == "pro-trial":
                    return License(
                        tier="pro",
                        valid=True,
                        source="trial",
                        email="trial@example.com",
                        issued=datetime.now().isoformat(),
                        expires="2099-12-31",
                    )
                license_data = _validate_key(key)
                if license_data:
                    return License(
                        tier=license_data.get("tier", "free"),
                        valid=True,
                        source="file",
                        email=license_data.get("email"),
                        issued=license_data.get("issued"),
                        expires=license_data.get("expires"),
                    )
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. Check <repo_path>/.evo/license.json
    if repo_path:
        repo_license = Path(repo_path) / ".evo" / "license.json"
        if repo_license.exists():
            try:
                data = json.loads(repo_license.read_text())
                key = data.get("license_key")
                if key:
                    if key == "pro-trial":
                        return License(
                            tier="pro",
                            valid=True,
                            source="trial",
                            email="trial@example.com",
                            issued=datetime.now().isoformat(),
                            expires="2099-12-31",
                        )
                    license_data = _validate_key(key)
                    if license_data:
                        return License(
                            tier=license_data.get("tier", "free"),
                            valid=True,
                            source="file",
                            email=license_data.get("email"),
                            issued=license_data.get("issued"),
                            expires=license_data.get("expires"),
                        )
            except (json.JSONDecodeError, KeyError):
                pass

    # Default: free tier
    return License(tier="free", valid=True, source="default")


def is_pro(repo_path: Optional[str] = None) -> bool:
    """Quick check if the current license is Pro tier.

    Args:
        repo_path: Optional repo path to check for repo-local license.

    Returns:
        True if Pro tier is active, False otherwise.
    """
    return get_license(repo_path).is_pro()


def require_pro(feature_name: str, repo_path: Optional[str] = None):
    """Raise ProFeatureError if the current license is not Pro tier.

    Args:
        feature_name: Human-readable name of the feature being gated.
        repo_path: Optional repo path to check for repo-local license.

    Raises:
        ProFeatureError: If not on Pro tier.
    """
    if not is_pro(repo_path):
        raise ProFeatureError(feature_name)


def _validate_key(key: str) -> Optional[dict]:
    """Validate a signed license key.

    Format: base64(json_payload + "." + hmac_signature)

    Returns:
        Parsed license data dict if valid, None otherwise.
    """
    try:
        decoded = base64.b64decode(key).decode("utf-8")
        if "." not in decoded:
            return None

        payload_str, signature = decoded.rsplit(".", 1)
        payload = json.loads(payload_str)

        # Verify HMAC signature
        expected_sig = hmac.new(
            _SIGNING_KEY,
            payload_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Check expiration if present
        if "expires" in payload:
            expires = datetime.fromisoformat(payload["expires"])
            if datetime.now() > expires:
                return None

        return payload

    except (ValueError, json.JSONDecodeError, KeyError):
        return None


def generate_key(
    tier: str,
    email: str,
    issued: Optional[str] = None,
    expires: Optional[str] = None,
) -> str:
    """Generate a signed license key.

    This is a utility for license generation (not used by the CLI).

    Args:
        tier: "free" or "pro"
        email: Licensee email
        issued: ISO format date (defaults to now)
        expires: ISO format date (optional)

    Returns:
        Base64-encoded signed license key.
    """
    payload = {
        "tier": tier,
        "email": email,
        "issued": issued or datetime.now().isoformat(),
    }
    if expires:
        payload["expires"] = expires

    payload_str = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        _SIGNING_KEY,
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    signed = f"{payload_str}.{signature}"
    return base64.b64encode(signed.encode("utf-8")).decode("utf-8")
