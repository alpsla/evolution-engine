"""Tests for evolution.setup_ui — local HTTP settings page."""

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.config import (
    EvoConfig,
    _GROUPS,
    _METADATA,
    config_groups,
    config_keys_for_group,
)
from evolution.setup_ui import SetupUI, _escape_html, _is_api_key_field


# ─── Helpers ───


def _make_ui(tmp_path) -> SetupUI:
    """Create a SetupUI with a temporary config file."""
    cfg = EvoConfig(path=tmp_path / "config.toml")
    return SetupUI(port=0, config=cfg, timeout=0)


def _make_mock_handler(body: bytes = b"", path: str = "/"):
    """Create a mock BaseHTTPRequestHandler for testing."""
    handler = MagicMock()
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.path = path

    # Capture what gets written
    written_chunks = []
    original_write = handler.wfile.write

    def capture_write(data):
        written_chunks.append(data)
        return original_write(data)

    handler.wfile.write = capture_write
    handler._written = written_chunks
    return handler


# ─── TestEscapeHtml ───


class TestEscapeHtml:
    def test_basic_escaping(self):
        assert _escape_html("<script>") == "&lt;script&gt;"
        assert _escape_html('a"b') == "a&quot;b"
        assert _escape_html("a&b") == "a&amp;b"
        assert _escape_html("a'b") == "a&#39;b"

    def test_no_escaping_needed(self):
        assert _escape_html("hello world") == "hello world"

    def test_empty_string(self):
        assert _escape_html("") == ""


class TestIsApiKeyField:
    def test_detects_api_key(self):
        assert _is_api_key_field("llm.api_key") is True
        assert _is_api_key_field("sync.secret") is True
        assert _is_api_key_field("auth.token") is True

    def test_normal_fields(self):
        assert _is_api_key_field("sync.privacy_level") is False
        assert _is_api_key_field("analyze.families") is False


# ─── TestGenerateHtml ───


class TestGenerateHtml:
    def test_html_contains_all_visible_groups(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()

        groups = config_groups()
        for group_id, info in groups.items():
            keys = config_keys_for_group(group_id, include_internal=False)
            if keys:
                # Label is HTML-escaped in the output
                escaped_label = _escape_html(info["label"])
                assert escaped_label in html, (
                    f"Group label '{info['label']}' missing"
                )

    def test_html_contains_setting_keys(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()

        # Check a sample of non-internal keys
        for key, meta in _METADATA.items():
            if meta.get("internal"):
                continue
            assert key in html, f"Setting key '{key}' not in HTML"

    def test_html_has_toggle_for_bool(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()

        # hooks.notify is a bool type
        assert 'data-key="hooks.notify"' in html
        assert 'data-type="bool"' in html
        assert 'type="checkbox"' in html

    def test_html_has_select_for_choice(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()

        # hooks.trigger is a choice type
        assert 'data-key="hooks.trigger"' in html
        assert 'data-type="choice"' in html
        assert "<select" in html
        assert "post-commit" in html
        assert "pre-push" in html

    def test_html_has_text_input_for_str(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()

        # analyze.families is a str type
        assert 'data-key="analyze.families"' in html
        assert 'data-type="str"' in html
        assert 'type="text"' in html

    def test_html_has_number_input_for_int(self, tmp_path):
        """int type fields should render as number inputs."""
        ui = _make_ui(tmp_path)
        html = ui._generate_html()

        # init.first_run_count is int but internal, so let's check
        # there's at least no crash. We can also verify number input
        # by checking the rendering function directly.
        control = ui._render_control(
            "test.count", {"type": "int"}, "int", 5
        )
        assert 'type="number"' in control
        assert 'data-type="int"' in control
        assert 'step="1"' in control

    def test_html_has_float_input(self, tmp_path):
        ui = _make_ui(tmp_path)
        control = ui._render_control(
            "test.ratio", {"type": "float"}, "float", 3.14
        )
        assert 'type="number"' in control
        assert 'data-type="float"' in control
        assert 'step="any"' in control

    def test_html_masks_api_key_fields(self, tmp_path):
        ui = _make_ui(tmp_path)
        control = ui._render_control(
            "llm.api_key", {"type": "str"}, "str", "sk-12345"
        )
        assert 'type="password"' in control

    def test_html_has_done_button(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()
        assert "shutdownServer()" in html
        assert "Done" in html

    def test_html_has_save_buttons(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()
        assert "saveGroup(" in html
        assert "btn-save" in html

    def test_html_has_inline_css_and_js(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()
        assert "<style>" in html
        assert "--color-primary: #0A4D4A" in html
        assert "<script>" in html
        assert "function saveGroup" in html

    def test_html_shows_descriptions(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()

        # Check that some descriptions appear
        for key, meta in _METADATA.items():
            if meta.get("internal"):
                continue
            desc = meta.get("description", "")
            if desc:
                assert _escape_html(desc) in html, (
                    f"Description for '{key}' not found"
                )

    def test_html_shows_pro_badge(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()
        assert "pro-badge" in html
        assert "PRO" in html

    def test_html_excludes_internal_settings(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()

        # telemetry.prompted is internal and should not appear as a control
        assert 'data-key="telemetry.prompted"' not in html
        assert 'data-key="init.first_run_count"' not in html
        assert 'data-key="adapter.last_version_check"' not in html

    def test_html_shows_current_values(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("analyze.families", "git,ci")
        ui = SetupUI(port=0, config=cfg, timeout=0)
        html = ui._generate_html()
        assert 'value="git,ci"' in html

    def test_html_choice_selected_value(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("hooks.trigger", "pre-push")
        ui = SetupUI(port=0, config=cfg, timeout=0)
        html = ui._generate_html()
        # "pre-push" option should be selected
        assert 'value="pre-push" selected' in html

    def test_info_bar_rendered(self, tmp_path):
        """Info bar should render (even if badges are minimal)."""
        ui = _make_ui(tmp_path)
        html = ui._generate_html()
        # Should at least have the tier badge
        assert "info-bar" in html

    def test_complete_html_structure(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._generate_html()
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "<head>" in html
        assert "</head>" in html
        assert "<body>" in html
        assert "</body>" in html
        assert "Evolution Engine Settings" in html


# ─── TestHandlePost ───


class TestHandlePost:
    def test_save_single_setting(self, tmp_path):
        ui = _make_ui(tmp_path)
        body = json.dumps({"hooks.notify": False}).encode("utf-8")
        handler = _make_mock_handler(body, "/api/config")

        ui._handle_post(handler)

        handler.send_response.assert_called_with(200)
        assert ui.config.get("hooks.notify") is False

        # Check response body
        response_body = b"".join(handler._written)
        data = json.loads(response_body)
        assert data["saved"] is True
        assert data["count"] == 1

    def test_save_multiple_settings(self, tmp_path):
        ui = _make_ui(tmp_path)
        changes = {
            "hooks.notify": False,
            "analyze.families": "git,ci",
            "hooks.trigger": "pre-push",
        }
        body = json.dumps(changes).encode("utf-8")
        handler = _make_mock_handler(body, "/api/config")

        ui._handle_post(handler)

        assert ui.config.get("hooks.notify") is False
        assert ui.config.get("analyze.families") == "git,ci"
        assert ui.config.get("hooks.trigger") == "pre-push"

        response_body = b"".join(handler._written)
        data = json.loads(response_body)
        assert data["count"] == 3

    def test_save_persists_to_disk(self, tmp_path):
        ui = _make_ui(tmp_path)
        body = json.dumps({"sync.privacy_level": 1}).encode("utf-8")
        handler = _make_mock_handler(body)

        ui._handle_post(handler)

        # Read back from disk
        cfg2 = EvoConfig(path=tmp_path / "config.toml")
        assert cfg2.get("sync.privacy_level") == 1

    def test_invalid_json_returns_400(self, tmp_path):
        ui = _make_ui(tmp_path)
        handler = _make_mock_handler(b"not json", "/api/config")

        ui._handle_post(handler)

        handler.send_response.assert_called_with(400)
        response_body = b"".join(handler._written)
        data = json.loads(response_body)
        assert "error" in data

    def test_empty_body_returns_400(self, tmp_path):
        ui = _make_ui(tmp_path)
        handler = _make_mock_handler(b"", "/api/config")

        ui._handle_post(handler)

        handler.send_response.assert_called_with(400)

    def test_save_bool_false(self, tmp_path):
        ui = _make_ui(tmp_path)
        # First set to non-default
        ui.config.set("hooks.notify", False)
        # Then save True via POST (back to default)
        body = json.dumps({"hooks.notify": True}).encode("utf-8")
        handler = _make_mock_handler(body)

        ui._handle_post(handler)

        assert ui.config.get("hooks.notify") is True

    def test_save_numeric_value(self, tmp_path):
        ui = _make_ui(tmp_path)
        body = json.dumps({"sync.privacy_level": 1}).encode("utf-8")
        handler = _make_mock_handler(body)

        ui._handle_post(handler)

        assert ui.config.get("sync.privacy_level") == 1


# ─── TestHandleStatus ───


class TestHandleStatus:
    def test_returns_json(self, tmp_path):
        ui = _make_ui(tmp_path)
        handler = _make_mock_handler()

        ui._handle_status(handler)

        handler.send_response.assert_called_with(200)
        response_body = b"".join(handler._written)
        data = json.loads(response_body)
        assert isinstance(data, dict)

    def test_contains_default_values(self, tmp_path):
        ui = _make_ui(tmp_path)
        handler = _make_mock_handler()

        ui._handle_status(handler)

        response_body = b"".join(handler._written)
        data = json.loads(response_body)

        assert "sync.privacy_level" in data
        assert data["sync.privacy_level"] == 0
        assert "hooks.notify" in data
        assert data["hooks.notify"] is True

    def test_reflects_user_overrides(self, tmp_path):
        ui = _make_ui(tmp_path)
        ui.config.set("hooks.notify", False)
        ui.config.set("analyze.families", "git,ci")

        handler = _make_mock_handler()
        ui._handle_status(handler)

        response_body = b"".join(handler._written)
        data = json.loads(response_body)
        assert data["hooks.notify"] is False
        assert data["analyze.families"] == "git,ci"

    def test_contains_all_default_keys(self, tmp_path):
        ui = _make_ui(tmp_path)
        handler = _make_mock_handler()

        ui._handle_status(handler)

        response_body = b"".join(handler._written)
        data = json.loads(response_body)

        from evolution.config import _DEFAULTS
        for key in _DEFAULTS:
            assert key in data, f"Key '{key}' missing from status response"


# ─── TestHandleGet ───


class TestHandleGet:
    def test_returns_html(self, tmp_path):
        ui = _make_ui(tmp_path)
        handler = _make_mock_handler()

        ui._handle_get(handler)

        handler.send_response.assert_called_with(200)
        handler.send_header.assert_any_call(
            "Content-Type", "text/html; charset=utf-8"
        )
        response_body = b"".join(handler._written)
        assert b"<!DOCTYPE html>" in response_body
        assert b"Evolution Engine Settings" in response_body


# ─── TestShutdown ───


class TestShutdown:
    def test_shutdown_handler_responds(self, tmp_path):
        ui = _make_ui(tmp_path)
        ui._server = MagicMock()
        handler = _make_mock_handler()

        ui._handle_shutdown(handler)

        handler.send_response.assert_called_with(200)
        response_body = b"".join(handler._written)
        data = json.loads(response_body)
        assert data["shutdown"] is True

    def test_shutdown_event(self, tmp_path):
        ui = _make_ui(tmp_path)
        ui._server = MagicMock()
        assert not ui._shutdown_event.is_set()
        ui._do_shutdown()
        assert ui._shutdown_event.is_set()


# ─── TestMakeHandler ───


class TestMakeHandler:
    def test_handler_class_created(self, tmp_path):
        ui = _make_ui(tmp_path)
        handler_cls = ui._make_handler()
        assert handler_cls is not None
        # It should be a class with do_GET and do_POST
        assert hasattr(handler_cls, "do_GET")
        assert hasattr(handler_cls, "do_POST")


# ─── TestRenderGroup ───


class TestRenderGroup:
    def test_render_group_contains_label(self, tmp_path):
        ui = _make_ui(tmp_path)
        html = ui._render_group(
            "analyze",
            _GROUPS["analyze"],
            config_keys_for_group("analyze"),
            ui.config.all(),
        )
        assert "Analysis" in html
        assert "group-analyze" in html

    def test_render_group_contains_all_keys(self, tmp_path):
        ui = _make_ui(tmp_path)
        keys = config_keys_for_group("hooks")
        html = ui._render_group(
            "hooks",
            _GROUPS["hooks"],
            keys,
            ui.config.all(),
        )
        for key in keys:
            assert key in html


# ─── TestInfoBar ───


class TestInfoBar:
    def test_info_bar_has_tier_badge(self, tmp_path):
        ui = _make_ui(tmp_path)
        bar = ui._render_info_bar()
        assert "badge-tier" in bar
        assert "Tier:" in bar

    def test_info_bar_shows_pro_tier(self, tmp_path):
        from evolution.license import License
        ui = _make_ui(tmp_path)
        with patch("evolution.license.get_license") as mock_license:
            mock_license.return_value = License(
                tier="pro", valid=True, source="env"
            )
            bar = ui._render_info_bar()
        assert "Pro" in bar
