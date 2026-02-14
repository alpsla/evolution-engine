"""
Unit tests for pattern CLI commands.

Covers: new, validate, packages, add, remove, block, unblock, check-updates.

Uses Click's CliRunner for isolated command testing.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from evolution.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def isolate_user_paths(tmp_path, monkeypatch):
    """Redirect user config paths to tmp_path."""
    monkeypatch.setattr(
        "evolution.pattern_registry.PATTERN_CACHE_PATH",
        tmp_path / "pattern_cache.json",
    )
    monkeypatch.setattr(
        "evolution.pattern_registry.USER_SOURCES_PATH",
        tmp_path / "pattern_sources.json",
    )
    monkeypatch.setattr(
        "evolution.pattern_registry.USER_BLOCKLIST_PATH",
        tmp_path / "pattern_blocklist.json",
    )
    return tmp_path


# ─── evo patterns new ───


class TestPatternsNew:
    def test_scaffolds_package(self, runner, tmp_path):
        result = runner.invoke(main, [
            "patterns", "new", "test-pack",
            "--output", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "evo-patterns-test-pack" in result.output
        assert (tmp_path / "evo-patterns-test-pack" / "pyproject.toml").exists()

    def test_shows_next_steps(self, runner, tmp_path):
        result = runner.invoke(main, [
            "patterns", "new", "my-patterns",
            "--output", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Next steps" in result.output


# ─── evo patterns validate ───


class TestPatternsValidate:
    def test_validates_example_package(self, runner):
        example_path = Path(__file__).parent.parent.parent / "examples" / "evo-patterns-example"
        if not example_path.exists():
            pytest.skip("Example package not found")

        result = runner.invoke(main, ["patterns", "validate", str(example_path)])
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_fails_on_missing_patterns(self, runner, tmp_path):
        # Empty directory
        result = runner.invoke(main, ["patterns", "validate", str(tmp_path)])
        assert result.exit_code != 0

    def test_validates_scaffolded_package(self, runner, tmp_path):
        # Scaffold then validate
        runner.invoke(main, [
            "patterns", "new", "val-test",
            "--output", str(tmp_path),
        ])
        pkg_path = tmp_path / "evo-patterns-val-test"
        result = runner.invoke(main, ["patterns", "validate", str(pkg_path)])
        assert result.exit_code == 0
        assert "PASSED" in result.output


# ─── evo patterns packages ───


class TestPatternsPackages:
    def test_lists_packages(self, runner):
        result = runner.invoke(main, ["patterns", "packages"])
        assert result.exit_code == 0
        assert "evo-patterns-example" in result.output

    def test_shows_cache_status(self, runner, tmp_path):
        import time
        cache = {
            "evo-patterns-example": {
                "version": "0.1.0",
                "last_fetched": time.time(),
                "families": ["ci", "git"],
                "patterns": [{"fingerprint": "abc"}],
            }
        }
        (tmp_path / "pattern_cache.json").write_text(json.dumps(cache))

        result = runner.invoke(main, ["patterns", "packages"])
        assert result.exit_code == 0
        assert "v0.1.0" in result.output


# ─── evo patterns add/remove ───


class TestPatternsAddRemove:
    def test_add_source(self, runner):
        result = runner.invoke(main, ["patterns", "add", "evo-patterns-custom"])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_duplicate(self, runner):
        runner.invoke(main, ["patterns", "add", "evo-patterns-custom"])
        result = runner.invoke(main, ["patterns", "add", "evo-patterns-custom"])
        assert result.exit_code == 0
        assert "already" in result.output

    def test_remove_source(self, runner):
        runner.invoke(main, ["patterns", "add", "evo-patterns-custom"])
        result = runner.invoke(main, ["patterns", "remove", "evo-patterns-custom"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_nonexistent(self, runner):
        result = runner.invoke(main, ["patterns", "remove", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output


# ─── evo patterns block/unblock ───


class TestPatternsBlockUnblock:
    def test_block_package(self, runner):
        result = runner.invoke(main, [
            "patterns", "block", "bad-pkg", "--reason", "malicious",
        ])
        assert result.exit_code == 0
        assert "Blocked" in result.output

    def test_block_duplicate(self, runner):
        runner.invoke(main, ["patterns", "block", "bad-pkg"])
        result = runner.invoke(main, ["patterns", "block", "bad-pkg"])
        assert result.exit_code == 0
        assert "already" in result.output

    def test_unblock_package(self, runner):
        runner.invoke(main, ["patterns", "block", "bad-pkg"])
        result = runner.invoke(main, ["patterns", "unblock", "bad-pkg"])
        assert result.exit_code == 0
        assert "Unblocked" in result.output

    def test_unblock_nonexistent(self, runner):
        result = runner.invoke(main, ["patterns", "unblock", "nonexistent"])
        assert result.exit_code == 0
        assert "not blocked" in result.output
