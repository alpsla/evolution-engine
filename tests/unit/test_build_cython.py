"""Tests for build_cython.py — Cython build infrastructure."""

import importlib.util
import pytest
from pathlib import Path


# Load build_cython as a module
BUILD_SCRIPT = Path(__file__).parent.parent.parent / "build_cython.py"


@pytest.fixture
def build_mod():
    """Import build_cython.py as a module."""
    if not BUILD_SCRIPT.exists():
        pytest.skip("build_cython.py not found")
    spec = importlib.util.spec_from_file_location("build_cython", BUILD_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestBuildCythonModule:
    def test_module_loads(self, build_mod):
        assert hasattr(build_mod, "CYTHON_MODULES")
        assert hasattr(build_mod, "build")
        assert hasattr(build_mod, "clean")
        assert hasattr(build_mod, "check_cython")

    def test_cython_modules_list(self, build_mod):
        assert len(build_mod.CYTHON_MODULES) == 5
        for mod in build_mod.CYTHON_MODULES:
            assert mod.startswith("evolution/phase") or mod.startswith("evolution/knowledge")
            assert mod.endswith(".py")

    def test_all_source_files_exist(self, build_mod):
        for mod_path in build_mod.CYTHON_MODULES:
            full_path = Path(__file__).parent.parent.parent / mod_path
            assert full_path.exists(), f"Missing source: {mod_path}"

    def test_proprietary_modules_correct(self, build_mod):
        """Verify only proprietary engines are compiled, not open-source."""
        names = {Path(m).stem for m in build_mod.CYTHON_MODULES}
        # These should be compiled
        assert "phase2_engine" in names
        assert "phase3_engine" in names
        assert "phase4_engine" in names
        assert "phase5_engine" in names
        assert "knowledge_store" in names
        # These should NOT be compiled (open source)
        assert "cli" not in names
        assert "orchestrator" not in names
        assert "registry" not in names
        assert "phase1_engine" not in names

    def test_check_cython_returns_bool(self, build_mod):
        result = build_mod.check_cython()
        assert isinstance(result, bool)

    def test_clean_no_artifacts(self, build_mod):
        """Clean doesn't crash when there's nothing to clean."""
        build_mod.clean()  # should not raise
