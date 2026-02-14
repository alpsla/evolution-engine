"""
Local HTTP settings page for Evolution Engine.

Starts a lightweight HTTP server on localhost that serves a standalone
HTML settings page. Config changes are POSTed back and saved to config.toml.

Usage:
    from evolution.setup_ui import SetupUI
    ui = SetupUI(port=8484)
    ui.serve()  # Opens browser, blocks until Done or timeout
"""

import json
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from evolution.config import (
    EvoConfig,
    _GROUPS,
    _METADATA,
    _DEFAULTS,
    config_groups,
    config_keys_for_group,
)


# ─── HTML / CSS ───

_CSS = """
:root {
  --color-primary: #0A4D4A;
  --color-primary-light: #0F6B67;
  --color-secondary: #2CA58D;
  --color-bg: #fafbfc;
  --color-bg-card: #ffffff;
  --color-border: #e1e4e8;
  --color-text: #24292e;
  --color-text-secondary: #586069;
  --color-danger: #d73a49;
  --color-success: #2CA58D;
  --color-warning: #f59e0b;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  background: var(--color-bg);
  color: var(--color-text);
  line-height: 1.6;
  padding: 2em;
  max-width: 800px;
  margin: 0 auto;
}

h1 {
  color: var(--color-primary);
  font-size: 1.75em;
  margin-bottom: 0.25em;
}

.subtitle {
  color: var(--color-text-secondary);
  margin-bottom: 2em;
  font-size: 0.95em;
}

.info-bar {
  display: flex;
  gap: 0.75em;
  flex-wrap: wrap;
  margin-bottom: 2em;
}

.badge {
  display: inline-block;
  padding: 0.25em 0.75em;
  border-radius: 12px;
  font-size: 0.8em;
  font-weight: 600;
}

.badge-tier {
  background: var(--color-primary);
  color: white;
}

.badge-hook {
  background: var(--color-success);
  color: white;
}

.badge-hook-missing {
  background: var(--color-text-secondary);
  color: white;
}

.badge-adapter {
  background: var(--color-secondary);
  color: white;
}

.group-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  margin-bottom: 1em;
  overflow: hidden;
}

.group-header {
  background: var(--color-bg);
  padding: 0.75em 1em;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--color-border);
  user-select: none;
}

.group-header:hover {
  background: #f0f2f4;
}

.group-title {
  font-weight: 600;
  color: var(--color-primary);
  font-size: 1.05em;
}

.group-desc {
  color: var(--color-text-secondary);
  font-size: 0.85em;
}

.group-chevron {
  font-size: 0.8em;
  color: var(--color-text-secondary);
  transition: transform 0.2s;
}

.group-card.collapsed .group-body { display: none; }
.group-card.collapsed .group-chevron { transform: rotate(-90deg); }

.group-body {
  padding: 1em;
}

.setting-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75em 0;
  border-bottom: 1px solid #f0f2f4;
}

.setting-row:last-child { border-bottom: none; }

.setting-info {
  flex: 1;
  padding-right: 1em;
}

.setting-label {
  font-weight: 500;
  font-size: 0.95em;
}

.setting-desc {
  color: var(--color-text-secondary);
  font-size: 0.8em;
}

.setting-key {
  font-family: monospace;
  font-size: 0.75em;
  color: var(--color-text-secondary);
  opacity: 0.7;
}

.pro-badge {
  background: var(--color-warning);
  color: #fff;
  font-size: 0.65em;
  padding: 0.15em 0.5em;
  border-radius: 4px;
  margin-left: 0.5em;
  vertical-align: middle;
  font-weight: 700;
}

.setting-control {
  flex-shrink: 0;
}

/* Toggle switch */
.toggle {
  position: relative;
  width: 44px;
  height: 24px;
}

.toggle input { opacity: 0; width: 0; height: 0; }

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background: #ccc;
  border-radius: 24px;
  transition: 0.2s;
}

.toggle-slider:before {
  content: "";
  position: absolute;
  height: 18px; width: 18px;
  left: 3px; bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: 0.2s;
}

.toggle input:checked + .toggle-slider {
  background: var(--color-secondary);
}

.toggle input:checked + .toggle-slider:before {
  transform: translateX(20px);
}

select, input[type="text"], input[type="number"], input[type="password"] {
  padding: 0.4em 0.6em;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 0.9em;
  min-width: 180px;
  background: white;
}

select:focus, input:focus {
  outline: none;
  border-color: var(--color-secondary);
  box-shadow: 0 0 0 2px rgba(44, 165, 141, 0.2);
}

.group-actions {
  padding: 0.5em 1em 1em;
  text-align: right;
}

.btn {
  padding: 0.5em 1.25em;
  border: none;
  border-radius: 6px;
  font-size: 0.9em;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-save {
  background: var(--color-secondary);
  color: white;
}

.btn-save:hover {
  background: var(--color-primary-light);
}

.btn-done {
  background: var(--color-primary);
  color: white;
  font-size: 1em;
  padding: 0.75em 2em;
  margin-top: 1.5em;
  display: block;
  width: 100%;
}

.btn-done:hover {
  background: var(--color-primary-light);
}

.toast {
  position: fixed;
  bottom: 2em;
  right: 2em;
  background: var(--color-primary);
  color: white;
  padding: 0.75em 1.5em;
  border-radius: 8px;
  font-weight: 500;
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
  z-index: 1000;
}

.toast.show { opacity: 1; }
"""

_JS = """
function toggleGroup(el) {
  el.closest('.group-card').classList.toggle('collapsed');
}

function saveGroup(groupId) {
  var card = document.getElementById('group-' + groupId);
  var inputs = card.querySelectorAll('[data-key]');
  var changes = {};
  inputs.forEach(function(el) {
    var key = el.getAttribute('data-key');
    var type = el.getAttribute('data-type');
    if (type === 'bool') {
      changes[key] = el.checked;
    } else if (type === 'int') {
      changes[key] = parseInt(el.value, 10) || 0;
    } else if (type === 'float') {
      changes[key] = parseFloat(el.value) || 0.0;
    } else if (type === 'choice') {
      var raw = el.value;
      /* Try to parse as int for numeric choices */
      var asNum = Number(raw);
      if (!isNaN(asNum) && raw !== '') {
        changes[key] = asNum;
      } else {
        changes[key] = raw;
      }
    } else {
      changes[key] = el.value;
    }
  });
  fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(changes)
  }).then(function(r) { return r.json(); })
    .then(function(data) {
      showToast(data.saved ? 'Settings saved' : 'Error saving');
    })
    .catch(function() { showToast('Error saving settings'); });
}

function shutdownServer() {
  fetch('/api/shutdown', {method: 'POST'}).catch(function(){});
  document.body.innerHTML = '<div style="text-align:center;padding:4em;">' +
    '<h2 style="color:#0A4D4A;">Settings saved. You can close this tab.</h2></div>';
}

function showToast(msg) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function() { t.classList.remove('show'); }, 2000);
}
"""


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _is_api_key_field(key: str) -> bool:
    """Check whether a config key looks like an API key / secret."""
    lower = key.lower()
    return any(term in lower for term in ("api_key", "secret", "token", "password"))


class SetupUI:
    """Local HTTP settings UI for Evolution Engine.

    Starts a localhost-only web server that serves an HTML settings page.
    Config changes are submitted via POST and persisted to config.toml.

    Args:
        port: TCP port for the local HTTP server (default 8484).
        config: An existing EvoConfig instance, or None to create one.
        timeout: Auto-shutdown timeout in seconds (default 600 = 10 minutes).
    """

    def __init__(
        self,
        port: int = 8484,
        config: Optional[EvoConfig] = None,
        timeout: int = 600,
    ):
        self.port = port
        self.config = config or EvoConfig()
        self.timeout = timeout
        self._server: Optional[HTTPServer] = None
        self._shutdown_event = threading.Event()

    # ─── Public ───

    def serve(self):
        """Start the HTTP server, open the browser, and block until done."""
        handler = self._make_handler()
        self._server = HTTPServer(("127.0.0.1", self.port), handler)

        # Auto-shutdown timer
        if self.timeout > 0:
            timer = threading.Timer(self.timeout, self._auto_shutdown)
            timer.daemon = True
            timer.start()

        # Open browser
        webbrowser.open(f"http://127.0.0.1:{self.port}")

        # Block
        self._server.serve_forever()

    # ─── HTML Generation ───

    def _generate_html(self) -> str:
        """Build the standalone HTML settings page."""
        groups = config_groups()
        all_settings = self.config.all()

        body_parts = []

        # Header
        body_parts.append('<h1>Evolution Engine Settings</h1>')
        body_parts.append(
            '<p class="subtitle">Configure your local EE installation. '
            "Changes are saved to <code>{}</code></p>".format(
                _escape_html(str(self.config.path))
            )
        )

        # Info badges
        body_parts.append(self._render_info_bar())

        # Groups
        for group_id, group_info in groups.items():
            keys = config_keys_for_group(group_id, include_internal=False)
            if not keys:
                continue
            body_parts.append(
                self._render_group(group_id, group_info, keys, all_settings)
            )

        # Done button
        body_parts.append(
            '<button class="btn btn-done" onclick="shutdownServer()">Done</button>'
        )

        # Toast notification
        body_parts.append('<div id="toast" class="toast"></div>')

        html = (
            "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>Evolution Engine Settings</title>\n"
            "<style>{css}</style>\n"
            "</head>\n<body>\n{body}\n"
            "<script>{js}</script>\n"
            "</body>\n</html>"
        ).format(
            css=_CSS,
            body="\n".join(body_parts),
            js=_JS,
        )
        return html

    def _render_info_bar(self) -> str:
        """Render the info badge bar (license tier, hook status, adapters)."""
        badges = []

        # License tier
        try:
            from evolution.license import get_license
            lic = get_license()
            tier_label = lic.tier.title()
            badges.append(
                '<span class="badge badge-tier">Tier: {}</span>'.format(
                    _escape_html(tier_label)
                )
            )
        except Exception:
            badges.append('<span class="badge badge-tier">Tier: Free</span>')

        # Hook status — check common git hook paths
        try:
            from pathlib import Path
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                repo = Path(result.stdout.strip())
                hook_path = repo / ".git" / "hooks" / "post-commit"
                if hook_path.exists() and "evo" in hook_path.read_text(errors="replace"):
                    badges.append(
                        '<span class="badge badge-hook">Hook: Installed</span>'
                    )
                else:
                    badges.append(
                        '<span class="badge badge-hook-missing">Hook: Not installed</span>'
                    )
        except Exception:
            pass

        # Detected adapters
        try:
            from evolution.registry import _discover_tier3
            adapters = _discover_tier3()
            if adapters:
                for name in adapters[:5]:
                    badges.append(
                        '<span class="badge badge-adapter">{}</span>'.format(
                            _escape_html(str(name))
                        )
                    )
        except Exception:
            pass

        if not badges:
            return ""
        return '<div class="info-bar">{}</div>'.format("".join(badges))

    def _render_group(
        self, group_id: str, group_info: dict, keys: list[str], all_settings: dict
    ) -> str:
        """Render a single group card."""
        rows = []
        for key in keys:
            meta = _METADATA.get(key, {})
            rows.append(self._render_setting(key, meta, all_settings.get(key)))

        return (
            '<div class="group-card" id="group-{gid}">'
            '<div class="group-header" onclick="toggleGroup(this)">'
            '<div>'
            '<span class="group-title">{label}</span>'
            ' <span class="group-desc">&mdash; {desc}</span>'
            "</div>"
            '<span class="group-chevron">&#9660;</span>'
            "</div>"
            '<div class="group-body">{rows}</div>'
            '<div class="group-actions">'
            '<button class="btn btn-save" onclick="saveGroup(\'{gid}\')">Save</button>'
            "</div>"
            "</div>"
        ).format(
            gid=_escape_html(group_id),
            label=_escape_html(group_info["label"]),
            desc=_escape_html(group_info.get("description", "")),
            rows="\n".join(rows),
        )

    def _render_setting(self, key: str, meta: dict, current_value) -> str:
        """Render a single setting row."""
        stype = meta.get("type", "str")
        display = meta.get("display", key)
        desc = meta.get("description", "")
        is_pro = meta.get("pro", False)

        pro_html = '<span class="pro-badge">PRO</span>' if is_pro else ""

        control = self._render_control(key, meta, stype, current_value)

        return (
            '<div class="setting-row">'
            '<div class="setting-info">'
            '<div class="setting-label">{display}{pro}</div>'
            '<div class="setting-desc">{desc}</div>'
            '<div class="setting-key">{key}</div>'
            "</div>"
            '<div class="setting-control">{control}</div>'
            "</div>"
        ).format(
            display=_escape_html(display),
            pro=pro_html,
            desc=_escape_html(desc),
            key=_escape_html(key),
            control=control,
        )

    def _render_control(self, key: str, meta: dict, stype: str, value) -> str:
        """Render the form control for a setting."""
        esc_key = _escape_html(key)

        if stype == "bool":
            checked = "checked" if value else ""
            return (
                '<label class="toggle">'
                '<input type="checkbox" data-key="{key}" data-type="bool" {checked}>'
                '<span class="toggle-slider"></span>'
                "</label>"
            ).format(key=esc_key, checked=checked)

        if stype == "choice":
            allowed = meta.get("allowed", [])
            labels = meta.get("allowed_labels", {})
            options = []
            for opt in allowed:
                label = labels.get(opt, str(opt))
                sel = "selected" if str(opt) == str(value) else ""
                options.append(
                    '<option value="{val}" {sel}>{label}</option>'.format(
                        val=_escape_html(str(opt)),
                        sel=sel,
                        label=_escape_html(str(label)),
                    )
                )
            return (
                '<select data-key="{key}" data-type="choice">{opts}</select>'
            ).format(key=esc_key, opts="".join(options))

        if stype in ("int", "float"):
            return (
                '<input type="number" data-key="{key}" data-type="{stype}" '
                'value="{val}" step="{step}">'
            ).format(
                key=esc_key,
                stype=_escape_html(stype),
                val=_escape_html(str(value if value is not None else "")),
                step="1" if stype == "int" else "any",
            )

        # str type — mask API keys
        input_type = "password" if _is_api_key_field(key) else "text"
        placeholder = meta.get("placeholder", "")
        return (
            '<input type="{itype}" data-key="{key}" data-type="str" '
            'value="{val}" placeholder="{ph}">'
        ).format(
            itype=input_type,
            key=esc_key,
            val=_escape_html(str(value) if value else ""),
            ph=_escape_html(placeholder),
        )

    # ─── Request Handlers ───

    def _handle_get(self, handler: BaseHTTPRequestHandler):
        """Serve the HTML settings page."""
        html = self._generate_html()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(html.encode("utf-8"))))
        handler.end_headers()
        handler.wfile.write(html.encode("utf-8"))

    def _handle_post(self, handler: BaseHTTPRequestHandler):
        """Accept JSON body with config changes and save to config.toml."""
        content_length = int(handler.headers.get("Content-Length", 0))
        body = handler.rfile.read(content_length)
        try:
            changes = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            handler.send_response(400)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
            return

        for key, value in changes.items():
            self.config.set(key, value)

        response = json.dumps({"saved": True, "count": len(changes)})
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(response.encode("utf-8"))

    def _handle_status(self, handler: BaseHTTPRequestHandler):
        """Return current config as JSON."""
        data = self.config.all()
        # Convert any non-serializable values
        safe_data = {k: v for k, v in data.items()}
        response = json.dumps(safe_data, default=str)
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(response.encode("utf-8"))

    def _handle_shutdown(self, handler: BaseHTTPRequestHandler):
        """Shut down the server."""
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"shutdown": True}).encode("utf-8"))
        # Schedule shutdown on a separate thread to avoid deadlock
        threading.Thread(target=self._do_shutdown, daemon=True).start()

    # ─── Internal ───

    def _auto_shutdown(self):
        """Called by the timeout timer."""
        self._do_shutdown()

    def _do_shutdown(self):
        """Actually shut down the server."""
        if self._server:
            self._server.shutdown()
        self._shutdown_event.set()

    def _make_handler(self):
        """Create a request handler class bound to this SetupUI instance."""
        ui = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/status":
                    ui._handle_status(self)
                else:
                    ui._handle_get(self)

            def do_POST(self):
                if self.path == "/api/config":
                    ui._handle_post(self)
                elif self.path == "/api/shutdown":
                    ui._handle_shutdown(self)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress request logging

        return Handler
