"""
E2E integration tests for the adapter lifecycle.

Tests the full cycle: scaffold → develop → validate → security-check →
trust tier → block/unblock using a pytest-cov adapter as the reference.
"""

import json
import sys
import textwrap

import pytest

from evolution.adapter_security import scan_adapter_source
from evolution.adapter_validator import validate_adapter
from evolution.registry import AdapterRegistry


@pytest.fixture
def coverage_xml_content():
    """Sample coverage.xml content for testing."""
    return textwrap.dedent("""\
        <?xml version="1.0" ?>
        <coverage version="7.0" timestamp="1700000000" lines-valid="1000"
                  lines-covered="850" branches-valid="200" branches-covered="144"
                  line-rate="0.85" branch-rate="0.72" complexity="0">
            <packages>
                <package name="mypackage" line-rate="0.85" branch-rate="0.72"
                         complexity="0">
                    <classes>
                        <class name="module.py" filename="mypackage/module.py"
                               line-rate="0.85" branch-rate="0.72" complexity="0">
                            <lines>
                                <line number="1" hits="1"/>
                                <line number="2" hits="1"/>
                                <line number="3" hits="0"/>
                            </lines>
                        </class>
                    </classes>
                </package>
            </packages>
        </coverage>
    """)


# ─── E2E Lifecycle Tests ───


class TestAdapterLifecycleE2E:
    """Full lifecycle: scaffold → develop → validate → security-check → trust."""

    def test_scaffold_creates_package(self, tmp_path):
        """evo adapter new creates a working package structure."""
        from evolution.adapter_scaffold import scaffold_adapter

        result = scaffold_adapter("pytest-cov", "testing", output_dir=str(tmp_path))
        pkg_dir = tmp_path / "evo-adapter-pytest-cov"

        assert pkg_dir.is_dir()
        assert (pkg_dir / "pyproject.toml").is_file()
        assert (pkg_dir / "evo_pytest_cov" / "__init__.py").is_file()
        assert result["package_dir"] == str(pkg_dir)

    def test_developed_adapter_validates(self, tmp_path, coverage_xml_content):
        """A developed adapter passes all 13 structural validation checks."""
        # Write adapter code
        mod_dir = tmp_path / "evo_pytest_cov"
        mod_dir.mkdir()
        adapter_code = textwrap.dedent("""\
            import xml.etree.ElementTree as ET
            from pathlib import Path

            class PytestCovAdapter:
                source_family = "testing"
                source_type = "pytest_cov"
                ordering_mode = "temporal"
                attestation_tier = "weak"

                def __init__(self, path="."):
                    self.repo_path = Path(path).resolve()
                    self.source_id = f"pytest_cov:{self.repo_path}"

                def iter_events(self):
                    coverage_file = self.repo_path / "coverage.xml"
                    if not coverage_file.exists():
                        return
                    tree = ET.parse(str(coverage_file))
                    root = tree.getroot()
                    line_rate = float(root.get("line-rate", "0"))
                    branch_rate = float(root.get("branch-rate", "0"))
                    yield {
                        "source_family": self.source_family,
                        "source_type": self.source_type,
                        "source_id": self.source_id,
                        "ordering_mode": self.ordering_mode,
                        "attestation": {"trust_tier": self.attestation_tier},
                        "payload": {
                            "line_rate": line_rate,
                            "branch_rate": branch_rate,
                            "trigger": {"commit_sha": "abc123"},
                        },
                    }
        """)
        (mod_dir / "__init__.py").write_text(adapter_code)

        # Write coverage.xml for the adapter to parse
        repo = tmp_path / "test_repo"
        repo.mkdir()
        (repo / "coverage.xml").write_text(coverage_xml_content)

        # Add to sys.path so we can import it
        sys.path.insert(0, str(tmp_path))
        try:
            import importlib
            mod = importlib.import_module("evo_pytest_cov")
            importlib.reload(mod)  # Ensure fresh import
            adapter_cls = mod.PytestCovAdapter

            report = validate_adapter(
                adapter_cls,
                constructor_args={"path": str(repo)},
                max_events=5,
            )
            assert report.passed, f"Validation failed:\n{report.summary()}"
        finally:
            sys.path.remove(str(tmp_path))
            # Clean up sys.modules
            sys.modules.pop("evo_pytest_cov", None)

    def test_security_scan_passes_on_clean_adapter(self, tmp_path):
        """A clean adapter passes security scanning with no critical findings."""
        mod_dir = tmp_path / "clean_adapter"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text(textwrap.dedent("""\
            import json
            from pathlib import Path

            class CleanAdapter:
                source_family = "testing"
                source_type = "clean"
                ordering_mode = "temporal"
                attestation_tier = "weak"

                def __init__(self, path="."):
                    self.source_id = f"clean:{path}"

                def iter_events(self):
                    yield {
                        "source_family": self.source_family,
                        "source_type": self.source_type,
                        "source_id": self.source_id,
                        "ordering_mode": self.ordering_mode,
                        "attestation": {"trust_tier": self.attestation_tier},
                        "payload": {"value": 1, "trigger": {"commit_sha": "abc"}},
                    }
        """))

        report = scan_adapter_source(str(mod_dir))
        assert report.passed, f"Security scan failed:\n{report.summary()}"
        assert report.critical_count == 0

    def test_security_scan_detects_dangerous_adapter(self, tmp_path):
        """Security scan catches dangerous patterns in adapter code."""
        mod_dir = tmp_path / "bad_adapter"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text(textwrap.dedent("""\
            import os

            class BadAdapter:
                source_family = "testing"

                def __init__(self):
                    os.system("whoami")

                def iter_events(self):
                    data = eval("1+1")
                    yield {"payload": data}
        """))

        report = scan_adapter_source(str(mod_dir))
        assert not report.passed
        assert report.critical_count >= 2  # eval + os.system

    def test_trust_tier_builtin_for_tier1(self, tmp_path):
        """Tier 1 (file-based) adapters get 'built-in' trust level."""
        (tmp_path / ".git").mkdir()
        registry = AdapterRegistry(tmp_path)
        configs = registry.detect()

        git_config = next((c for c in configs if c.adapter_name == "git"), None)
        assert git_config is not None
        assert git_config.trust_level == "built-in"

    def test_block_unblock_roundtrip(self, tmp_path, monkeypatch):
        """Block and unblock an adapter, verify detection changes."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".git").mkdir()

        # Detect — git should be present
        registry1 = AdapterRegistry(tmp_path)
        configs1 = registry1.detect()
        assert any(c.adapter_name == "git" for c in configs1)

        # Block
        AdapterRegistry.block_adapter("git", reason="testing blocklist")

        # Re-detect — git should be gone
        registry2 = AdapterRegistry(tmp_path)
        configs2 = registry2.detect()
        assert not any(c.adapter_name == "git" for c in configs2)
        blocked = registry2.get_blocked()
        assert any(b["adapter_name"] == "git" for b in blocked)

        # Unblock
        AdapterRegistry.unblock_adapter("git")

        # Re-detect — git should be back
        registry3 = AdapterRegistry(tmp_path)
        configs3 = registry3.detect()
        assert any(c.adapter_name == "git" for c in configs3)
