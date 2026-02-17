"""Tests for evolution.config — user configuration management."""

import pytest
from pathlib import Path

from evolution.config import (
    EvoConfig, _parse_value, _format_value, _DEFAULTS,
    _GROUPS, _METADATA, config_groups, config_metadata, config_keys_for_group,
)


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
        assert cfg.get("telemetry.enabled") is False
        assert cfg.get("sync.registry_url") == "https://codequal.dev/api"

    def test_get_unknown_key(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        assert cfg.get("nonexistent") is None
        assert cfg.get("nonexistent", "fallback") == "fallback"

    def test_set_and_get(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("sync.privacy_level", 1)
        assert cfg.get("sync.privacy_level") == 1

    def test_persistence(self, tmp_path):
        path = tmp_path / "config.toml"
        cfg1 = EvoConfig(path=path)
        cfg1.set("hooks.notify", False)

        # New instance should read from disk
        cfg2 = EvoConfig(path=path)
        assert cfg2.get("hooks.notify") is False

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
        assert "telemetry.enabled" in all_settings  # default

    def test_user_overrides_only_set_values(self, tmp_path):
        cfg = EvoConfig(path=tmp_path / "config.toml")
        cfg.set("sync.privacy_level", 1)
        overrides = cfg.user_overrides()
        assert "sync.privacy_level" in overrides
        assert "telemetry.enabled" not in overrides

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


class TestConfigMetadata:
    def test_all_defaults_have_metadata(self):
        """Every key in _DEFAULTS should have metadata (except internal-only)."""
        for key in _DEFAULTS:
            assert key in _METADATA, f"Missing metadata for default key: {key}"

    def test_all_metadata_have_defaults(self):
        """Every key in _METADATA should have a default."""
        for key in _METADATA:
            assert key in _DEFAULTS, f"Missing default for metadata key: {key}"

    def test_metadata_required_fields(self):
        """Each metadata entry must have description, type, and group."""
        for key, meta in _METADATA.items():
            assert "description" in meta, f"{key} missing description"
            assert "type" in meta, f"{key} missing type"
            assert "group" in meta, f"{key} missing group"

    def test_all_groups_exist(self):
        """Every group referenced in metadata must exist in _GROUPS."""
        for key, meta in _METADATA.items():
            group = meta["group"]
            assert group in _GROUPS, f"{key} references unknown group: {group}"

    def test_config_groups_sorted(self):
        """config_groups() returns groups sorted by order."""
        groups = config_groups()
        orders = [v["order"] for v in groups.values()]
        assert orders == sorted(orders)

    def test_config_metadata_known_key(self):
        meta = config_metadata("sync.privacy_level")
        assert meta["type"] == "choice"
        assert meta["group"] == "sync"

    def test_config_metadata_unknown_key(self):
        assert config_metadata("nonexistent.key") == {}

    def test_config_keys_for_group(self):
        keys = config_keys_for_group("sync")
        assert "sync.privacy_level" in keys
        assert "sync.registry_url" in keys
        assert "sync.auto_pull" in keys

    def test_config_keys_excludes_internal(self):
        keys = config_keys_for_group("telemetry", include_internal=False)
        assert "telemetry.enabled" in keys
        assert "telemetry.prompted" not in keys

    def test_config_keys_includes_internal(self):
        keys = config_keys_for_group("telemetry", include_internal=True)
        assert "telemetry.enabled" in keys
        assert "telemetry.prompted" in keys

    def test_config_keys_empty_group(self):
        assert config_keys_for_group("nonexistent") == []

    def test_non_internal_keys_have_display(self):
        """Non-internal keys should have a display prompt for evo setup."""
        for key, meta in _METADATA.items():
            if not meta.get("internal"):
                assert "display" in meta, f"{key} missing display prompt"

    def test_choice_types_have_allowed(self):
        """Choice-type keys must have allowed values."""
        for key, meta in _METADATA.items():
            if meta["type"] == "choice":
                assert "allowed" in meta, f"{key} is choice type but missing allowed values"
                assert len(meta["allowed"]) >= 2, f"{key} needs at least 2 choices"
