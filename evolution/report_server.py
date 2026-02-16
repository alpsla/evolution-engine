"""
Local HTTP server for serving Evolution Engine HTML reports.

Serves the report via localhost so that Accept buttons can POST back
to persist acceptances to .evo/accepted.json (impossible from file:// URLs).

Usage:
    # As a module (used by CLI subprocess):
    python -m evolution.report_server <evo_dir> <report_path> [port]

    # Programmatically:
    from evolution.report_server import ReportServer
    server = ReportServer(evo_dir, report_path)
    server.serve()  # Opens browser, blocks until timeout
"""

import json
import socket
import sys
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional


_PORT_START = 8485
_PORT_END = 8499


class ReportServer:
    """Local HTTP server for serving report + accept API.

    Args:
        evo_dir: Path to .evo directory.
        report_path: Path to the HTML report file.
        port: TCP port (default: auto-find from 8485-8499).
        timeout: Auto-shutdown in seconds (default 600 = 10 min).
    """

    def __init__(
        self,
        evo_dir: str | Path,
        report_path: str | Path,
        port: int = 0,
        timeout: int = 600,
    ):
        self.evo_dir = Path(evo_dir)
        self.report_path = Path(report_path)
        self.port = port or self.find_available_port()
        self.timeout = timeout
        self._server: Optional[HTTPServer] = None

    def serve(self):
        """Start server, open browser, block until shutdown or timeout."""
        handler = self._make_handler()
        self._server = HTTPServer(("127.0.0.1", self.port), handler)

        if self.timeout > 0:
            timer = threading.Timer(self.timeout, self._shutdown)
            timer.daemon = True
            timer.start()

        webbrowser.open(f"http://127.0.0.1:{self.port}")
        self._server.serve_forever()

    def _shutdown(self):
        if self._server:
            self._server.shutdown()

    @staticmethod
    def find_available_port(start: int = _PORT_START, end: int = _PORT_END) -> int:
        """Find an available port in range. Raises RuntimeError if none free."""
        for port in range(start, end + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue
        raise RuntimeError(f"No available port in range {start}-{end}")

    # ---- Request handlers ----

    def _handle_get_report(self, handler: BaseHTTPRequestHandler):
        """Serve the HTML report from disk."""
        try:
            html = self.report_path.read_bytes()
        except FileNotFoundError:
            handler.send_response(404)
            handler.end_headers()
            handler.wfile.write(b"Report not found")
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(html)))
        handler.end_headers()
        handler.wfile.write(html)

    def _handle_get_accepted(self, handler: BaseHTTPRequestHandler):
        """Return current accepted list as JSON."""
        from evolution.accepted import AcceptedDeviations
        ad = AcceptedDeviations(self.evo_dir)
        entries = ad.load()
        body = json.dumps({"accepted": entries}).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_post_accept(self, handler: BaseHTTPRequestHandler):
        """Accept a deviation and persist to accepted.json."""
        content_length = int(handler.headers.get("Content-Length", 0))
        raw = handler.rfile.read(content_length)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._json_error(handler, 400, "Invalid JSON")
            return

        index = data.get("index")  # 1-based
        scope_type = data.get("scope", "permanent")
        reason = data.get("reason", "")

        # Load advisory to map index -> family:metric
        advisory_path = self.evo_dir / "phase5" / "advisory.json"
        if not advisory_path.exists():
            self._json_error(handler, 404, "No advisory found")
            return

        advisory = json.loads(advisory_path.read_text())
        changes = advisory.get("changes", [])
        advisory_id = advisory.get("advisory_id", "")

        if not isinstance(index, int) or index < 1 or index > len(changes):
            self._json_error(handler, 400, f"Invalid index: {index} (valid: 1-{len(changes)})")
            return

        change = changes[index - 1]
        family = change["family"]
        metric = change["metric"]
        key = f"{family}:{metric}"

        # Build scope dict
        scope_dict = {"type": scope_type}
        if scope_type == "this-run":
            scope_dict["advisory_id"] = advisory_id

        from evolution.accepted import AcceptedDeviations
        ad = AcceptedDeviations(self.evo_dir)
        ad.add(key, family, metric, reason=reason, advisory_id=advisory_id, scope=scope_dict)

        body = json.dumps({"accepted": True, "key": key}).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    @staticmethod
    def _json_error(handler: BaseHTTPRequestHandler, code: int, message: str):
        body = json.dumps({"error": message}).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/accepted":
                    server._handle_get_accepted(self)
                else:
                    server._handle_get_report(self)

            def do_POST(self):
                if self.path == "/api/accept":
                    server._handle_post_accept(self)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress request logging

        return Handler


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m evolution.report_server <evo_dir> <report_path> [port]")
        sys.exit(1)
    evo_dir = sys.argv[1]
    report_path = sys.argv[2]
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    srv = ReportServer(evo_dir, report_path, port=port)
    srv.serve()
