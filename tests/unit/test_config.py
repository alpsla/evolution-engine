"""Tests for evolution.config — user configuration management."""

import pytest
from pathlib import Path

from evolution.config import EvoConfig, _parse_value, _format_value, _DEFAULTS


class TestParseValue:
    def test_bool_true(self):
        assert _parse_value("true") is True
        assert _parse_value("True") is True
        assert _parse_value("TRUE") is True

    def test_bool_false(self):
        assert _parse_value("false") is False

    def test_int(self):
        assert _parse_value("42") == 42
        assert _parse_value("0") == 0
        assert _parse_value("-1") == -1

    def test_float(self):
        assert _parse_value("3.14") == 3.14

    def test_quoted_string(self):
        assert _parse_value('"hello world"') == "hello world"
        assert _parse_value("'hello world'") == "hello world"

    def test_bare_string(self):
        assert _parse_value("anthropic") == "anthropic"

    def test_url(self):
        assert _parse_value("https://example.com") == "https://example.com"


class TestFormatValue:
    def test_bool(self):
        assert _format_value(True) == "true"
        assert _format_value(False) == "false"

    def test_string_no_spaces(self):
        assert _format_value("hello") == "hello"

    def test_string_with_spaces(self):
        assert _format_value("hello world") == '"hello world"'

    def test_empty_string(self):
        assert _format_value("") == '""'

    def test_int(self):
        assert _format_value(42) == "42"

    def test_float(self):
        assert _format_value(3.14) == "3.14"


class TestEvoConfig:
    def test_defaults_loaded(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        assert cfg.get("sync.privacy_level") == 0
        assert cfg.get("llm.enabled") is False
        assert cfg.get("sync.registry_url") == "https://registry.evo.dev/v1"

    def test_get_unknown_key(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        assert cfg.get("nonexistent") is None
        assert cfg.get("nonexistent", "fallback") == "fallback"

    def test_set_and_get(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("sync.privacy_level", 2)
        assert cfg.get("sync.privacy_level") == 2

    def test_persistence(self, tmp_path):
        path = tmp_path / "config.toml"
        cfg1 = EvoConfig(path=path)
        cfg1.set("llm.enabled", True)

        # New instance should read from disk
        cfg2 = EvoConfig(path=path)
        assert cfg2.get("llm.enabled") is True

    def test_delete(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("custom.key", "value")
        assert cfg.get("custom.key") == "value"
        assert cfg.delete("custom.key") is True
        assert cfg.get("custom.key") is None

    def test_delete_nonexistent(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        assert cfg.delete("nonexistent") is False

    def test_all_includes_defaults_and_overrides(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("sync.privacy_level", 1)
        all_settings = cfg.all()
        assert all_settings["sync.privacy_level"] == 1
        assert "llm.enabled" in all_settings  # default

    def test_user_overrides_only_set_values(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("sync.privacy_level", 2)
        overrides = cfg.user_overrides()
        assert "sync.privacy_level" in overrides
        assert "llm.enabled" not in overrides

    def test_comments_preserved(self, tmp_path):
        path = tmp_path / "config.toml"
        cfg = EvoConfig(path=path)
        cfg.set("sync.privacy_level", 1)
        content = path.read_text()
        assert "# Evolution Engine" in content

    def test_config_dir_created(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "config.toml"
        cfg = EvoConfig(path=deep_path)
        cfg.set("test.key", "val")
        assert deep_path.exists()

    def test_empty_file_handled(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("")
        cfg = EvoConfig(path=path)
        assert cfg.get("sync.privacy_level") == 0  # falls back to default

    def test_malformed_lines_skipped(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("not_a_valid_line\nsync.privacy_level = 1\n")
        cfg = EvoConfig(path=path)
        assert cfg.get("sync.privacy_level") == 1

    def test_path_property(self, tmp_path):
        path = tmp_path / "config.toml"
        cfg = EvoConfig(path=path)
        assert cfg.path == path
