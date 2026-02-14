"""
End-to-end tests: scaffold_adapter() → validate_adapter() round-trip.

Verifies that scaffolded adapters pass validation without modification.
"""

import importlib.util
import sys

import pytest

from evolution.adapter_scaffold import VALID_FAMILIES, scaffold_adapter
from evolution.adapter_validator import validate_adapter


ALL_FAMILIES = sorted(VALID_FAMILIES)


class TestScaffoldValidateRoundTrip:
    """Scaffold an adapter, load it, and run validation."""

    def test_scaffold_then_validate_passes(self, tmp_path):
        """A freshly scaffolded adapter should pass validation."""
        result = scaffold_adapter("jenkins", "ci", output_dir=str(tmp_path))

        # Dynamically load the scaffolded module
        pkg_dir = tmp_path / "evo-adapter-jenkins"
        mod_dir = pkg_dir / "evo_jenkins"
        init_file = mod_dir / "__init__.py"
        assert init_file.exists()

        spec = importlib.util.spec_from_file_location("evo_jenkins", str(init_file))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["evo_jenkins"] = mod
        spec.loader.exec_module(mod)

        try:
            adapter_cls = getattr(mod, "JenkinsAdapter")
            report = validate_adapter(adapter_cls)

            # Should have zero errors (warnings are OK — e.g. no real events)
            assert report.passed, (
                f"Validation failed for scaffolded 'jenkins' adapter:\n{report.summary()}"
            )
        finally:
            sys.modules.pop("evo_jenkins", None)

    @pytest.mark.parametrize("family", ALL_FAMILIES)
    def test_all_families_scaffold_correctly(self, tmp_path, family):
        """Every supported family scaffolds and validates without errors."""
        result = scaffold_adapter("testadapter", family, output_dir=str(tmp_path))

        pkg_dir = tmp_path / "evo-adapter-testadapter"
        mod_dir = pkg_dir / "evo_testadapter"
        init_file = mod_dir / "__init__.py"
        assert init_file.exists(), f"No __init__.py for family={family}"

        mod_name = f"evo_testadapter_{family}"
        spec = importlib.util.spec_from_file_location(mod_name, str(init_file))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)

        try:
            adapter_cls = getattr(mod, "TestadapterAdapter")
            report = validate_adapter(adapter_cls)
            assert report.passed, (
                f"Validation failed for family={family}:\n{report.summary()}"
            )
        finally:
            sys.modules.pop(mod_name, None)

    def test_generated_pyproject_has_valid_entry_points(self, tmp_path):
        """pyproject.toml should declare evo.adapters entry point."""
        scaffold_adapter("myci", "ci", output_dir=str(tmp_path))
        pyproject = (tmp_path / "evo-adapter-myci" / "pyproject.toml").read_text()
        assert "[project.entry-points.\"evo.adapters\"]" in pyproject
        assert "evo_myci:register" in pyproject

    def test_generated_register_function_returns_valid_descriptors(self, tmp_path):
        """The register() function should return a list of adapter descriptors."""
        scaffold_adapter("testci", "ci", output_dir=str(tmp_path))

        init_file = tmp_path / "evo-adapter-testci" / "evo_testci" / "__init__.py"
        mod_name = "evo_testci_register_test"
        spec = importlib.util.spec_from_file_location(mod_name, str(init_file))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)

        try:
            register_fn = getattr(mod, "register")
            descriptors = register_fn()

            assert isinstance(descriptors, list)
            assert len(descriptors) >= 1

            d = descriptors[0]
            assert "adapter_name" in d
            assert "family" in d
            assert "adapter_class" in d
            assert d["family"] == "ci"
        finally:
            sys.modules.pop(mod_name, None)
