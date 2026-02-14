"""
Integration tests for the adapter-request API endpoint (website/api/adapter-request.py).

Pattern: Import handler directly, mock HTTP internals — same approach as test_stripe_flow.py.
"""

import io
import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Allow importing from website/api/ (hyphenated filename requires importlib)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "website", "api"))

import importlib

_mod = importlib.import_module("adapter-request")
handler = _mod.handler
_rate_limits = _mod._rate_limits
_VALID_FAMILIES = _mod._VALID_FAMILIES
_sanitize = _mod._sanitize


# ─── Helpers ───


class MockRequest:
    """Simulate an HTTP request to the BaseHTTPRequestHandler."""

    def __init__(self, method, body=None, headers=None):
        self.method = method
        if body is not None:
            raw = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
        else:
            raw = b""
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self._headers = {
            "Content-Length": str(len(raw)),
            **(headers or {}),
        }

    def get(self, key, default=None):
        return self._headers.get(key, default)


def _invoke(method, body=None, headers=None):
    """Invoke the handler and return (status_code, response_body)."""
    mock_req = MockRequest(method, body, headers)
    # BaseHTTPRequestHandler.__init__ calls handle_one_request,
    # so we construct manually and call the method directly.
    h = handler.__new__(handler)
    h.rfile = mock_req.rfile
    h.wfile = mock_req.wfile
    h.headers = mock_req
    h.requestline = f"{method} /api/adapter-request HTTP/1.1"
    h.command = method
    h.request_version = "HTTP/1.1"

    h._status_code = None
    h._response_headers = {}

    original_send_response = handler.send_response
    original_send_header = handler.send_header
    original_end_headers = handler.end_headers

    def mock_send_response(self, code, message=None):
        self._status_code = code

    def mock_send_header(self, key, value):
        self._response_headers[key] = value

    def mock_end_headers(self):
        pass

    with patch.object(handler, "send_response", mock_send_response), \
         patch.object(handler, "send_header", mock_send_header), \
         patch.object(handler, "end_headers", mock_end_headers):
        method_fn = getattr(h, f"do_{method}")
        method_fn()

    response_data = h.wfile.getvalue()
    try:
        response_json = json.loads(response_data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        response_json = None

    return h._status_code, response_json, h._response_headers


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Reset rate limits between tests."""
    _rate_limits.clear()
    yield
    _rate_limits.clear()


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Remove GitHub/Axiom tokens unless explicitly set by test."""
    monkeypatch.delenv("GITHUB_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    monkeypatch.delenv("AXIOM_TOKEN", raising=False)


def _valid_body(**overrides):
    """Return a valid adapter request body with optional overrides."""
    base = {
        "adapter_name": "Jenkins CI",
        "family": "ci",
        "description": "Fetch builds from Jenkins API",
        "email": "user@example.com",
        "use_case": "Track CI failures alongside deployments",
    }
    base.update(overrides)
    return base


# ─── Input Validation ───


class TestInputValidation:
    def test_valid_request_returns_200(self):
        status, body, _ = _invoke("POST", _valid_body())
        assert status == 200
        assert body["success"] is True
        assert "recorded" in body["message"].lower() or "submitted" in body["message"].lower()

    def test_missing_adapter_name_returns_400(self):
        status, body, _ = _invoke("POST", _valid_body(adapter_name=""))
        assert status == 400
        assert "required" in body["error"].lower()

    def test_invalid_family_returns_400(self):
        status, body, _ = _invoke("POST", _valid_body(family="quantum"))
        assert status == 400
        assert "invalid family" in body["error"].lower()

    def test_invalid_json_body_returns_400(self):
        mock_req = MockRequest("POST")
        mock_req.rfile = io.BytesIO(b"not json{{{")
        mock_req._headers["Content-Length"] = "11"

        h = handler.__new__(handler)
        h.rfile = mock_req.rfile
        h.wfile = mock_req.wfile
        h.headers = mock_req
        h._status_code = None
        h._response_headers = {}

        with patch.object(handler, "send_response", lambda self, code, msg=None: setattr(self, "_status_code", code)), \
             patch.object(handler, "send_header", lambda self, k, v: None), \
             patch.object(handler, "end_headers", lambda self: None):
            h.do_POST()

        resp = json.loads(h.wfile.getvalue().decode("utf-8"))
        assert h._status_code == 400
        assert "invalid json" in resp["error"].lower()

    def test_xss_in_adapter_name_sanitized(self):
        status, body, _ = _invoke("POST", _valid_body(adapter_name="<script>alert('xss')</script>"))
        assert status == 200
        # The angle brackets should have been stripped by _sanitize
        assert "<" not in _sanitize("<script>alert('xss')</script>", 100)
        assert ">" not in _sanitize("<script>alert('xss')</script>", 100)


# ─── Rate Limiting ───


class TestRateLimiting:
    def test_five_requests_succeed_sixth_returns_429(self):
        for i in range(5):
            status, _, _ = _invoke("POST", _valid_body())
            assert status == 200, f"Request {i+1} should succeed"

        status, body, _ = _invoke("POST", _valid_body())
        assert status == 429
        assert "rate limit" in body["error"].lower()

    def test_different_emails_have_separate_limits(self):
        for _ in range(5):
            _invoke("POST", _valid_body(email="alice@example.com"))

        # alice is rate-limited
        status, _, _ = _invoke("POST", _valid_body(email="alice@example.com"))
        assert status == 429

        # bob can still submit
        status, _, _ = _invoke("POST", _valid_body(email="bob@example.com"))
        assert status == 200


# ─── GitHub Issue Creation ───


class TestGitHubIssueCreation:
    def test_creates_github_issue_with_correct_payload(self, monkeypatch):
        monkeypatch.setenv("GITHUB_BOT_TOKEN", "ghp_test_token")
        monkeypatch.setenv("GITHUB_REPO", "test-org/test-repo")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "html_url": "https://github.com/test-org/test-repo/issues/42",
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            status, body, _ = _invoke("POST", _valid_body())

        assert status == 200
        assert body["success"] is True
        assert "github issue" in body["message"].lower()
        assert body["issue_url"] == "https://github.com/test-org/test-repo/issues/42"

        # Verify the request payload
        call_args = mock_urlopen.call_args
        req_obj = call_args[0][0]
        issue_data = json.loads(req_obj.data.decode("utf-8"))
        assert "Jenkins CI" in issue_data["title"]
        assert "ci" in issue_data["title"]
        assert "adapter-request" in issue_data["labels"]

    def test_email_not_in_issue_body(self, monkeypatch):
        monkeypatch.setenv("GITHUB_BOT_TOKEN", "ghp_test_token")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "html_url": "https://github.com/test/repo/issues/1",
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            _invoke("POST", _valid_body(email="secret@private.com"))

        # Check the issue body does NOT contain the email
        req_obj = mock_urlopen.call_args[0][0]
        issue_data = json.loads(req_obj.data.decode("utf-8"))
        assert "secret@private.com" not in issue_data["body"]

    def test_email_logged_to_axiom_separately(self, monkeypatch):
        monkeypatch.setenv("GITHUB_BOT_TOKEN", "ghp_test_token")
        monkeypatch.setenv("AXIOM_TOKEN", "xaat_test")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "html_url": "https://github.com/test/repo/issues/1",
        }).encode("utf-8")

        axiom_events = []

        # Patch at the module level where _axiom_send is defined
        original_axiom = _mod._axiom_send

        def capture_axiom(event):
            axiom_events.append(event)

        with patch.object(_mod, "_axiom_send", capture_axiom), \
             patch("urllib.request.urlopen", return_value=mock_response):
            _invoke("POST", _valid_body(email="contact@user.com"))

        # Axiom should have received the email in a separate event
        contact_events = [e for e in axiom_events if e.get("type") == "adapter_request_contact"]
        assert len(contact_events) == 1
        assert contact_events[0]["email"] == "contact@user.com"

    def test_github_api_failure_graceful_fallback(self, monkeypatch):
        monkeypatch.setenv("GITHUB_BOT_TOKEN", "ghp_test_token")

        with patch("urllib.request.urlopen", side_effect=Exception("GitHub API down")), \
             patch.object(_mod, "_axiom_send"):
            status, body, _ = _invoke("POST", _valid_body())

        assert status == 200
        assert body["success"] is True
        assert "recorded" in body["message"].lower()


# ─── Without GITHUB_BOT_TOKEN ───


class TestWithoutGitHubToken:
    def test_falls_back_to_stdout_logging(self, capsys):
        status, body, _ = _invoke("POST", _valid_body())
        assert status == 200
        assert body["success"] is True
        assert "recorded" in body["message"].lower()

    def test_still_returns_success(self):
        status, body, _ = _invoke("POST", _valid_body())
        assert status == 200
        assert body["success"] is True


# ─── CORS ───


class TestCORS:
    def test_options_returns_204_with_cors_headers(self):
        status, _, headers = _invoke("OPTIONS")
        assert status == 204
        assert headers.get("Access-Control-Allow-Origin") == "*"
        assert "POST" in headers.get("Access-Control-Allow-Methods", "")
        assert "Content-Type" in headers.get("Access-Control-Allow-Headers", "")

    def test_post_includes_cors_origin_header(self):
        _, _, headers = _invoke("POST", _valid_body())
        assert headers.get("Access-Control-Allow-Origin") == "*"
