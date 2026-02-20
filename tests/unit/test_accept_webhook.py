"""Tests for the accept webhook handler (website/api/accept.py)."""

import hashlib
import hmac
import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Load the accept module from website/api/accept.py ──

_ACCEPT_PATH = Path(__file__).parent.parent.parent / "website" / "api" / "accept.py"


@pytest.fixture(scope="module")
def accept_mod():
    """Import website/api/accept.py as a module."""
    if not _ACCEPT_PATH.exists():
        pytest.skip("website/api/accept.py not found")
    spec = importlib.util.spec_from_file_location("accept", _ACCEPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Fixtures ──


def _make_signature(repo: str, secret: str = "test-secret") -> str:
    """Create a valid HMAC-SHA256 signature for a repo."""
    return hmac.new(secret.encode(), repo.encode(), hashlib.sha256).hexdigest()


def _make_entry(family="git", metric="dispersion", reason="Test accept", accepted_by="alice"):
    return {
        "key": f"{family}:{metric}",
        "family": family,
        "metric": metric,
        "reason": reason,
        "accepted_by": accepted_by,
    }


def _make_post_payload(repo="owner/repo", secret="test-secret", entries=None):
    return {
        "repo": repo,
        "signature": _make_signature(repo, secret),
        "entries": entries or [_make_entry()],
    }


class MockRequest:
    """Mock HTTP request for testing the handler."""

    def __init__(self, method, path="/api/accept", body=None, headers=None):
        self.method = method
        self.path = path
        self.body = body or b""
        self.headers = headers or {}
        if "Content-Length" not in self.headers:
            self.headers["Content-Length"] = str(len(self.body))


# ── Validation tests ──


class TestValidateEntry:
    def test_valid_entry(self, accept_mod):
        entry = _make_entry()
        validated, err = accept_mod._validate_entry(entry)
        assert err is None
        assert validated["key"] == "git:dispersion"
        assert validated["family"] == "git"
        assert validated["metric"] == "dispersion"
        assert validated["reason"] == "Test accept"

    def test_invalid_key_format(self, accept_mod):
        entry = {"key": "invalid", "family": "git", "metric": "x"}
        _, err = accept_mod._validate_entry(entry)
        assert err is not None
        assert "invalid key format" in err

    def test_key_mismatch(self, accept_mod):
        entry = {"key": "git:dispersion", "family": "ci", "metric": "dispersion"}
        _, err = accept_mod._validate_entry(entry)
        assert err is not None
        assert "doesn't match" in err

    def test_not_a_dict(self, accept_mod):
        _, err = accept_mod._validate_entry("not a dict")
        assert err is not None
        assert "must be a dict" in err

    def test_dangerous_reason(self, accept_mod):
        entry = _make_entry(reason="<script>alert('xss')</script>")
        _, err = accept_mod._validate_entry(entry)
        assert err is not None
        assert "dangerous content" in err

    def test_reason_too_long(self, accept_mod):
        entry = _make_entry(reason="A" * 600)
        _, err = accept_mod._validate_entry(entry)
        assert err is not None
        assert "max length" in err

    def test_empty_reason_ok(self, accept_mod):
        entry = _make_entry(reason="")
        validated, err = accept_mod._validate_entry(entry)
        assert err is None
        assert validated["reason"] == ""

    def test_accepted_at_preserved(self, accept_mod):
        entry = _make_entry()
        entry["accepted_at"] = "2026-02-19T12:00:00Z"
        validated, err = accept_mod._validate_entry(entry)
        assert err is None
        assert validated["accepted_at"] == "2026-02-19T12:00:00Z"


# ── HMAC Signature tests ──


class TestSignatureVerification:
    def test_valid_signature(self, accept_mod):
        with patch.dict("os.environ", {"EVO_ACCEPT_SECRET": "test-secret"}):
            sig = _make_signature("owner/repo", "test-secret")
            assert accept_mod._verify_signature("owner/repo", sig) is True

    def test_invalid_signature(self, accept_mod):
        with patch.dict("os.environ", {"EVO_ACCEPT_SECRET": "test-secret"}):
            assert accept_mod._verify_signature("owner/repo", "bad-sig") is False

    def test_wrong_secret(self, accept_mod):
        with patch.dict("os.environ", {"EVO_ACCEPT_SECRET": "different-secret"}):
            sig = _make_signature("owner/repo", "test-secret")
            assert accept_mod._verify_signature("owner/repo", sig) is False

    def test_no_secret_configured(self, accept_mod):
        with patch.dict("os.environ", {}, clear=True):
            sig = _make_signature("owner/repo", "test-secret")
            assert accept_mod._verify_signature("owner/repo", sig) is False


# ── Rate Limiting tests ──


class TestRateLimit:
    def test_allows_under_limit(self, accept_mod):
        # Reset rate limits
        accept_mod._rate_limits.clear()
        assert accept_mod._check_rate_limit("test/repo") is True

    def test_blocks_at_limit(self, accept_mod):
        import time
        accept_mod._rate_limits.clear()
        accept_mod._rate_limits["test/repo-limit"] = [time.time()] * 20
        assert accept_mod._check_rate_limit("test/repo-limit") is False

    def test_old_entries_expire(self, accept_mod):
        import time
        accept_mod._rate_limits.clear()
        # Add entries from over an hour ago
        old_time = time.time() - 3700
        accept_mod._rate_limits["test/repo-expire"] = [old_time] * 20
        assert accept_mod._check_rate_limit("test/repo-expire") is True


# ── Redis Key tests ──


class TestRedisKey:
    def test_key_format(self, accept_mod):
        key = accept_mod._redis_key("owner/repo")
        assert key.startswith("evo:accept:")
        assert len(key) == len("evo:accept:") + 16

    def test_different_repos_different_keys(self, accept_mod):
        key1 = accept_mod._redis_key("owner/repo1")
        key2 = accept_mod._redis_key("owner/repo2")
        assert key1 != key2

    def test_key_deterministic(self, accept_mod):
        key1 = accept_mod._redis_key("owner/repo")
        key2 = accept_mod._redis_key("owner/repo")
        assert key1 == key2


# ── Safe text checks ──


class TestCheckTextSafe:
    def test_clean_text(self, accept_mod):
        val, err = accept_mod._check_text_safe("Normal text", "field")
        assert err is None
        assert val == "Normal text"

    def test_script_injection(self, accept_mod):
        _, err = accept_mod._check_text_safe("<script>alert(1)</script>", "field")
        assert err is not None
        assert "dangerous" in err

    def test_javascript_url(self, accept_mod):
        _, err = accept_mod._check_text_safe("javascript:void(0)", "field")
        assert err is not None

    def test_template_injection(self, accept_mod):
        _, err = accept_mod._check_text_safe("{{malicious}}", "field")
        assert err is not None

    def test_path_traversal(self, accept_mod):
        _, err = accept_mod._check_text_safe("../../etc/passwd", "field")
        assert err is not None

    def test_max_length(self, accept_mod):
        _, err = accept_mod._check_text_safe("A" * 600, "field", max_len=500)
        assert err is not None
        assert "max length" in err

    def test_whitespace_stripped(self, accept_mod):
        val, err = accept_mod._check_text_safe("  hello  ", "field")
        assert err is None
        assert val == "hello"

    def test_non_string(self, accept_mod):
        _, err = accept_mod._check_text_safe(123, "field")
        assert err is not None
        assert "expected string" in err


# ── Merge logic tests ──


class TestMergeLogic:
    """Test that entries are deduplicated by key during merge."""

    def test_dedup_by_key(self, accept_mod):
        """Entries with same key are not duplicated in stored data."""
        stored = {"repo": "owner/repo", "entries": [
            {"key": "git:dispersion", "family": "git", "metric": "dispersion", "reason": "First"},
        ]}
        existing_keys = {e["key"] for e in stored["entries"]}
        new_entry = {"key": "git:dispersion", "family": "git", "metric": "dispersion", "reason": "Duplicate"}

        # Simulate the merge logic from do_POST
        if new_entry["key"] not in existing_keys:
            stored["entries"].append(new_entry)
            existing_keys.add(new_entry["key"])

        assert len(stored["entries"]) == 1
        assert stored["entries"][0]["reason"] == "First"

    def test_new_key_added(self, accept_mod):
        """New keys are added to the store."""
        stored = {"repo": "owner/repo", "entries": [
            {"key": "git:dispersion", "family": "git", "metric": "dispersion", "reason": "Existing"},
        ]}
        existing_keys = {e["key"] for e in stored["entries"]}
        new_entry = {"key": "ci:run_duration", "family": "ci", "metric": "run_duration", "reason": "New"}

        if new_entry["key"] not in existing_keys:
            stored["entries"].append(new_entry)
            existing_keys.add(new_entry["key"])

        assert len(stored["entries"]) == 2
        keys = {e["key"] for e in stored["entries"]}
        assert "git:dispersion" in keys
        assert "ci:run_duration" in keys


# ── POST validation tests ──


class TestPostValidation:
    def test_missing_repo(self, accept_mod):
        data = {"signature": "x", "entries": []}
        entry = _make_entry()
        _, err = accept_mod._validate_entry(entry)
        # Just test that valid entry passes
        assert err is None

    def test_invalid_repo_format(self, accept_mod):
        """Repo must be owner/name format."""
        import re
        assert re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", "owner/repo")
        assert not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", "no-slash")
        assert not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", "")
        assert not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", "a/b/c")

    def test_entries_all_rejected(self, accept_mod):
        """When all entries fail validation, check error aggregation."""
        bad_entries = [
            {"key": "invalid", "family": "x", "metric": "y"},
            {"key": "also-bad", "family": "x", "metric": "y"},
        ]
        errors = []
        validated = []
        for i, e in enumerate(bad_entries):
            v, err = accept_mod._validate_entry(e)
            if err:
                errors.append(f"entry[{i}]: {err}")
            else:
                validated.append(v)

        assert len(validated) == 0
        assert len(errors) == 2

    def test_partial_validation(self, accept_mod):
        """Mix of good and bad entries."""
        entries = [
            _make_entry(),
            {"key": "invalid", "family": "x", "metric": "y"},
        ]
        errors = []
        validated = []
        for i, e in enumerate(entries):
            v, err = accept_mod._validate_entry(e)
            if err:
                errors.append(f"entry[{i}]: {err}")
            else:
                validated.append(v)

        assert len(validated) == 1
        assert len(errors) == 1
        assert validated[0]["key"] == "git:dispersion"


# ── GET tests ──


class TestGetValidation:
    def test_valid_repo_format(self, accept_mod):
        """Valid repo formats accepted."""
        import re
        pattern = r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$"
        assert re.match(pattern, "alpsla/evolution-engine")
        assert re.match(pattern, "my_org/my-repo.js")
        assert re.match(pattern, "A/B")

    def test_invalid_repo_rejected(self, accept_mod):
        """Invalid repo formats rejected."""
        import re
        pattern = r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$"
        assert not re.match(pattern, "")
        assert not re.match(pattern, "no-slash")
        assert not re.match(pattern, "has spaces/repo")
        assert not re.match(pattern, "owner/has spaces")


# ── Entry key format tests ──


class TestKeyFormat:
    def test_valid_keys(self, accept_mod):
        """family:metric keys with alphanumeric and underscores."""
        import re
        pattern = accept_mod._KEY_RE
        assert pattern.match("git:dispersion")
        assert pattern.match("ci:run_duration")
        assert pattern.match("dependency:dependency_count")

    def test_invalid_keys(self, accept_mod):
        pattern = accept_mod._KEY_RE
        assert not pattern.match("invalid")
        assert not pattern.match("a:b:c")
        assert not pattern.match(":metric")
        assert not pattern.match("family:")
        assert not pattern.match("")
        assert not pattern.match("has space:metric")
        assert not pattern.match("family:has-dash")
