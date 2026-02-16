"""Unit tests for the report server (accept API + report serving)."""

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from evolution.report_server import ReportServer


@pytest.fixture
def evo_dir(tmp_path):
    """Create a minimal .evo directory with advisory data."""
    phase5 = tmp_path / "phase5"
    phase5.mkdir()

    advisory = {
        "advisory_id": "adv-001",
        "scope": "test/repo",
        "generated_at": "2026-02-16T00:00:00Z",
        "period": {"from": "2026-01-01", "to": "2026-02-16"},
        "summary": {
            "significant_changes": 2,
            "families_affected": ["git", "ci"],
        },
        "changes": [
            {"family": "git", "metric": "files_touched",
             "current": 50, "normal": {"median": 5}, "deviation_stddev": 6.0},
            {"family": "ci", "metric": "run_duration",
             "current": 300, "normal": {"median": 60}, "deviation_stddev": 4.0},
        ],
        "pattern_matches": [],
        "candidate_patterns": [],
    }
    (phase5 / "advisory.json").write_text(json.dumps(advisory))

    report_html = "<html><body>Test Report</body></html>"
    (tmp_path / "report.html").write_text(report_html)

    return tmp_path


class _FakeHandler:
    """Minimal BaseHTTPRequestHandler stub for testing."""

    def __init__(self, method="GET", path="/", body=None, headers=None):
        self.path = path
        self._method = method
        self._body = body or b""
        self.headers = headers or {}
        self._response_code = None
        self._response_headers = {}
        self.wfile = io.BytesIO()
        self.rfile = io.BytesIO(self._body)

    def send_response(self, code):
        self._response_code = code

    def send_header(self, key, value):
        self._response_headers[key] = value

    def end_headers(self):
        pass

    def response_json(self):
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class TestHandleAcceptPermanent:
    def test_accept_first_change(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        body = json.dumps({"index": 1, "scope": "permanent", "reason": "Expected"}).encode()
        handler = _FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        server._handle_post_accept(handler)

        assert handler._response_code == 200
        data = handler.response_json()
        assert data["accepted"] is True
        assert data["key"] == "git:files_touched"

        # Verify persisted
        accepted = json.loads((evo_dir / "accepted.json").read_text())
        assert len(accepted["accepted"]) == 1
        assert accepted["accepted"][0]["key"] == "git:files_touched"
        assert accepted["accepted"][0]["scope"]["type"] == "permanent"

    def test_accept_second_change(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        body = json.dumps({"index": 2, "scope": "permanent"}).encode()
        handler = _FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        server._handle_post_accept(handler)

        data = handler.response_json()
        assert data["key"] == "ci:run_duration"


class TestHandleAcceptThisRun:
    def test_this_run_scope(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        body = json.dumps({"index": 1, "scope": "this-run", "reason": "One-time"}).encode()
        handler = _FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        server._handle_post_accept(handler)

        assert handler._response_code == 200
        accepted = json.loads((evo_dir / "accepted.json").read_text())
        entry = accepted["accepted"][0]
        assert entry["scope"]["type"] == "this-run"
        assert entry["scope"]["advisory_id"] == "adv-001"


class TestHandleAcceptInvalidIndex:
    def test_index_zero(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        body = json.dumps({"index": 0}).encode()
        handler = _FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        server._handle_post_accept(handler)
        assert handler._response_code == 400

    def test_index_out_of_range(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        body = json.dumps({"index": 99}).encode()
        handler = _FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        server._handle_post_accept(handler)
        assert handler._response_code == 400

    def test_index_not_integer(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        body = json.dumps({"index": "abc"}).encode()
        handler = _FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        server._handle_post_accept(handler)
        assert handler._response_code == 400


class TestHandleAcceptNoAdvisory:
    def test_missing_advisory(self, tmp_path):
        (tmp_path / "report.html").write_text("<html></html>")
        server = ReportServer(tmp_path, tmp_path / "report.html")
        body = json.dumps({"index": 1}).encode()
        handler = _FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        server._handle_post_accept(handler)
        assert handler._response_code == 404
        assert "No advisory" in handler.response_json()["error"]


class TestHandleGetAccepted:
    def test_empty_accepted(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        handler = _FakeHandler()
        server._handle_get_accepted(handler)
        assert handler._response_code == 200
        data = handler.response_json()
        assert data["accepted"] == []

    def test_with_existing_accepted(self, evo_dir):
        # Write an acceptance first
        from evolution.accepted import AcceptedDeviations
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion", reason="test")

        server = ReportServer(evo_dir, evo_dir / "report.html")
        handler = _FakeHandler()
        server._handle_get_accepted(handler)
        data = handler.response_json()
        assert len(data["accepted"]) == 1
        assert data["accepted"][0]["key"] == "git:dispersion"


class TestHandleGetReport:
    def test_serves_html(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        handler = _FakeHandler()
        server._handle_get_report(handler)
        assert handler._response_code == 200
        assert handler._response_headers["Content-Type"] == "text/html; charset=utf-8"
        assert b"Test Report" in handler.wfile.getvalue()

    def test_missing_report(self, tmp_path):
        server = ReportServer(tmp_path, tmp_path / "nonexistent.html")
        handler = _FakeHandler()
        server._handle_get_report(handler)
        assert handler._response_code == 404


class TestFindAvailablePort:
    def test_returns_port_in_range(self):
        port = ReportServer.find_available_port()
        assert 8485 <= port <= 8499

    def test_custom_range(self):
        port = ReportServer.find_available_port(start=9100, end=9110)
        assert 9100 <= port <= 9110

    def test_no_available_port_raises(self):
        """When entire range is exhausted, raises RuntimeError."""
        import socket
        # Bind a single port and ask for that exact range
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        try:
            with pytest.raises(RuntimeError, match="No available port"):
                ReportServer.find_available_port(start=port, end=port)
        finally:
            s.close()


class TestInvalidJson:
    def test_bad_json_body(self, evo_dir):
        server = ReportServer(evo_dir, evo_dir / "report.html")
        body = b"not json"
        handler = _FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        server._handle_post_accept(handler)
        assert handler._response_code == 400
        assert "Invalid JSON" in handler.response_json()["error"]
