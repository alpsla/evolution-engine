"""
Unit tests for pattern scaffold (evolution/pattern_scaffold.py).
"""

import json

import pytest

from evolution.pattern_scaffold import scaffold_pattern_pack


class TestScaffoldPatternPack:
    def test_creates_basic_structure(self, tmp_path):
        result = scaffold_pattern_pack("test-pack", output_dir=str(tmp_path))

        assert result["package_name"] == "evo-patterns-test-pack"
        assert result["module_name"] == "evo_patterns_test_pack"

        pkg_dir = tmp_path / "evo-patterns-test-pack"
        assert pkg_dir.exists()
        assert (pkg_dir / "pyproject.toml").exists()
        assert (pkg_dir / "README.md").exists()
        assert (pkg_dir / "evo_patterns_test_pack" / "__init__.py").exists()
        assert (pkg_dir / "evo_patterns_test_pack" / "patterns.json").exists()
        assert (pkg_dir / "tests" / "test_patterns.py").exists()

    def test_patterns_json_valid(self, tmp_path):
        scaffold_pattern_pack("my-patterns", output_dir=str(tmp_path))

        patterns_path = tmp_path / "evo-patterns-my-patterns" / "evo_patterns_my_patterns" / "patterns.json"
        patterns = json.loads(patterns_path.read_text())
        assert isinstance(patterns, list)
        assert len(patterns) == 1  # template pattern
        assert patterns[0]["scope"] == "community"

    def test_pyproject_has_entry_points(self, tmp_path):
        scaffold_pattern_pack("foobar", output_dir=str(tmp_path))

        pyproject = (tmp_path / "evo-patterns-foobar" / "pyproject.toml").read_text()
        assert "evo.patterns" in pyproject
        assert "evo_patterns_foobar:register" in pyproject
        assert "evo-patterns-foobar" in pyproject

    def test_strips_prefix_if_already_present(self, tmp_path):
        result = scaffold_pattern_pack("evo-patterns-redundant", output_dir=str(tmp_path))
        assert result["package_name"] == "evo-patterns-redundant"

    def test_normalizes_underscores_to_dashes(self, tmp_path):
        result = scaffold_pattern_pack("my_pack", output_dir=str(tmp_path))
        assert result["package_name"] == "evo-patterns-my-pack"

    def test_custom_description(self, tmp_path):
        scaffold_pattern_pack(
            "custom", description="Custom patterns for CI", output_dir=str(tmp_path)
        )

        pyproject = (tmp_path / "evo-patterns-custom" / "pyproject.toml").read_text()
        assert "Custom patterns for CI" in pyproject

    def test_readme_content(self, tmp_path):
        scaffold_pattern_pack("readme-test", output_dir=str(tmp_path))

        readme = (tmp_path / "evo-patterns-readme-test" / "README.md").read_text()
        assert "evo-patterns-readme-test" in readme
        assert "evo patterns validate" in readme

    def test_files_created_list(self, tmp_path):
        result = scaffold_pattern_pack("files-test", output_dir=str(tmp_path))
        assert "pyproject.toml" in result["files_created"]
        assert "README.md" in result["files_created"]
        assert len(result["files_created"]) == 5
