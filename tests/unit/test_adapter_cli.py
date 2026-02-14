"""
Unit tests for adapter CLI commands.

Covers: list, validate, new, prompt, request, requests,
        security-check, block, unblock, check-updates, report.

Uses Click's CliRunner for isolated command testing.
"""

import json
import os
import subprocess
import sys

import pytest
from click.testing import CliRunner

from evolution.cli import main


@pytest.fixture
def runner():
    return CliRunner()


# ─── evo adapter list ───


class TestAdapterList:
    def test_lists_adapters_in_git_repo(self, runner, tmp_path):
        """adapter list in a repo with .git/ shows connected adapters section."""
        # Create minimal git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        result = runner.invoke(main, ["adapter", "list", str(tmp_path)])
        assert result.exit_code == 0
        assert "Connected adapters:" in result.output

    def test_shows_none_when_no_adapters(self, runner, tmp_path):
        """adapter list in dir without .git shows (none) for connected adapters."""
        # Without .git, git adapter won't detect — so create an empty dir only
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = runner.invoke(main, ["adapter", "list", str(empty_dir)])
        assert result.exit_code == 0
        assert "(none)" in result.output or "Connected adapters:" in result.output

    def test_json_flag_outputs_valid_json(self, runner, tmp_path):
        """adapter list --json outputs machine-readable JSON."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        result = runner.invoke(main, ["adapter", "list", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "connected" in data
        assert "plugins" in data
        assert "detected" in data
        assert isinstance(data["connected"], list)


# ─── evo adapter validate ───


class TestAdapterValidate:
    def test_validates_builtin_adapter(self, runner, tmp_path):
        """adapter validate with PipDependencyAdapter passes validation."""
        # Create a requirements.txt so the adapter has something to scan
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests==2.31.0\n")

        result = runner.invoke(
            main,
            ["adapter", "validate",
             "evolution.adapters.dependency.pip_adapter.PipDependencyAdapter",
             "--args", json.dumps({"lock_file": str(req_file)})],
        )
        assert result.exit_code == 0
        assert "certified" in result.output.lower() or "passed" in result.output.lower()

    def test_fails_on_invalid_dotted_path(self, runner):
        """adapter validate with nonexistent module fails."""
        result = runner.invoke(main, ["adapter", "validate", "nonexistent.module.Adapter"])
        assert result.exit_code != 0
        assert "error" in result.output.lower()

    def test_fails_on_missing_attributes(self, runner, tmp_path):
        """adapter validate with an adapter missing required attrs fails."""
        # Create a minimal module with a class that lacks adapter attributes
        mod_dir = tmp_path / "bad_adapter"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text(
            "class BadAdapter:\n    pass\n"
        )
        sys.path.insert(0, str(tmp_path))
        try:
            result = runner.invoke(main, ["adapter", "validate", "bad_adapter.BadAdapter"])
            # Should fail validation (missing source_family etc.)
            assert result.exit_code != 0 or "error" in result.output.lower() or "fail" in result.output.lower()
        finally:
            sys.path.remove(str(tmp_path))


# ─── evo adapter new ───


class TestAdapterNew:
    def test_creates_package_in_output_dir(self, runner, tmp_path):
        """adapter new creates a package directory."""
        result = runner.invoke(main, ["adapter", "new", "jenkins", "--family", "ci", "--output", str(tmp_path)])
        assert result.exit_code == 0
        assert "Created adapter package" in result.output

        # Check package exists
        pkg_dir = tmp_path / "evo-adapter-jenkins"
        assert pkg_dir.is_dir()

    def test_generated_package_has_correct_structure(self, runner, tmp_path):
        """Scaffolded package has pyproject.toml, __init__.py, tests/, README.md."""
        runner.invoke(main, ["adapter", "new", "myci", "--family", "ci", "--output", str(tmp_path)])
        pkg_dir = tmp_path / "evo-adapter-myci"
        assert (pkg_dir / "pyproject.toml").is_file()
        assert (pkg_dir / "README.md").is_file()
        # Module directory
        mod_dir = pkg_dir / "evo_myci"
        assert mod_dir.is_dir()
        assert (mod_dir / "__init__.py").is_file()
        # Tests directory
        assert (pkg_dir / "tests").is_dir()

    def test_generated_class_name_is_correct(self, runner, tmp_path):
        """Adapter class name follows CamelCase convention."""
        runner.invoke(main, ["adapter", "new", "bitbucket-pipelines", "--family", "ci", "--output", str(tmp_path)])
        pkg_dir = tmp_path / "evo-adapter-bitbucket-pipelines"
        mod_dir = pkg_dir / "evo_bitbucket_pipelines"
        init_content = (mod_dir / "__init__.py").read_text()
        assert "BitbucketPipelinesAdapter" in init_content


# ─── evo adapter prompt ───


class TestAdapterPrompt:
    def test_generates_nonempty_prompt_for_each_family(self, runner):
        """adapter prompt generates non-empty output for every family."""
        families = ["ci", "testing", "dependency", "schema", "deployment", "config", "security"]
        for family in families:
            result = runner.invoke(main, ["adapter", "prompt", "test-adapter", "--family", family])
            assert result.exit_code == 0, f"Failed for family={family}: {result.output}"
            assert len(result.output) > 100, f"Prompt too short for family={family}"


# ─── evo adapter request ───


class TestAdapterRequest:
    def test_saves_request_to_file(self, runner, tmp_path, monkeypatch):
        """adapter request saves to ~/.evo/adapter_requests/requests.json."""
        monkeypatch.setenv("HOME", str(tmp_path))
        # Also patch Path.home() for consistency
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = runner.invoke(main, ["adapter", "request", "Bitbucket Pipelines CI adapter", "--family", "ci"])
        assert result.exit_code == 0
        assert "recorded" in result.output.lower()

        requests_file = tmp_path / ".evo" / "adapter_requests" / "requests.json"
        assert requests_file.exists()
        data = json.loads(requests_file.read_text())
        assert len(data) == 1
        assert data[0]["description"] == "Bitbucket Pipelines CI adapter"
        assert data[0]["family"] == "ci"

    def test_appends_to_existing_requests(self, runner, tmp_path, monkeypatch):
        """Multiple adapter requests append to the same file."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        runner.invoke(main, ["adapter", "request", "Jenkins adapter", "--family", "ci"])
        runner.invoke(main, ["adapter", "request", "Azure DevOps adapter", "--family", "deployment"])

        requests_file = tmp_path / ".evo" / "adapter_requests" / "requests.json"
        data = json.loads(requests_file.read_text())
        assert len(data) == 2
        assert data[0]["description"] == "Jenkins adapter"
        assert data[1]["description"] == "Azure DevOps adapter"


# ─── evo adapter requests (list pending) ───


class TestAdapterRequests:
    def test_shows_saved_requests(self, runner, tmp_path, monkeypatch):
        """adapter requests lists previously saved requests."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        # Create some requests first
        runner.invoke(main, ["adapter", "request", "Jenkins CI adapter", "--family", "ci"])
        runner.invoke(main, ["adapter", "request", "Azure DevOps", "--family", "deployment"])

        result = runner.invoke(main, ["adapter", "requests"])
        assert result.exit_code == 0
        assert "Jenkins CI adapter" in result.output
        assert "Azure DevOps" in result.output
        assert "2" in result.output  # count

    def test_shows_message_when_no_requests(self, runner, tmp_path, monkeypatch):
        """adapter requests with no saved requests shows helpful message."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = runner.invoke(main, ["adapter", "requests"])
        assert result.exit_code == 0
        assert "no" in result.output.lower()


# ─── evo adapter security-check ───


class TestAdapterSecurityCheck:
    def test_clean_directory_passes(self, runner, tmp_path):
        """security-check on a clean adapter directory passes."""
        mod_dir = tmp_path / "clean_mod"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text("x = 1\n")

        result = runner.invoke(main, ["adapter", "security-check", str(mod_dir)])
        assert result.exit_code == 0
        assert "PASSED" in result.output
        assert "No critical" in result.output

    def test_dangerous_directory_fails(self, runner, tmp_path):
        """security-check on a directory with eval() fails."""
        mod_dir = tmp_path / "bad_mod"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text("eval('1+1')\n")

        result = runner.invoke(main, ["adapter", "security-check", str(mod_dir)])
        assert result.exit_code != 0
        assert "critical" in result.output.lower()

    def test_nonexistent_target_fails(self, runner):
        """security-check on nonexistent target fails gracefully."""
        result = runner.invoke(main, ["adapter", "security-check", "nonexistent_xyz_99"])
        assert result.exit_code != 0
        assert "error" in result.output.lower()


# ─── evo adapter block / unblock ───


class TestAdapterBlockUnblock:
    def test_block_creates_entry(self, runner, tmp_path, monkeypatch):
        """adapter block adds to local blocklist."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = runner.invoke(main, ["adapter", "block", "test-adapter", "-r", "testing"])
        assert result.exit_code == 0
        assert "Blocked: test-adapter" in result.output

        # Verify file exists
        blocklist = tmp_path / ".evo" / "blocklist.json"
        assert blocklist.exists()
        data = json.loads(blocklist.read_text())
        assert data[0]["name"] == "test-adapter"
        assert data[0]["reason"] == "testing"

    def test_block_duplicate_shows_already(self, runner, tmp_path, monkeypatch):
        """adapter block on already-blocked adapter shows message."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        runner.invoke(main, ["adapter", "block", "dup-adapter"])
        result = runner.invoke(main, ["adapter", "block", "dup-adapter"])
        assert result.exit_code == 0
        assert "Already blocked" in result.output

    def test_unblock_removes_entry(self, runner, tmp_path, monkeypatch):
        """adapter unblock removes from local blocklist."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        runner.invoke(main, ["adapter", "block", "test-adapter"])
        result = runner.invoke(main, ["adapter", "unblock", "test-adapter"])
        assert result.exit_code == 0
        assert "Unblocked: test-adapter" in result.output

    def test_unblock_nonexistent_fails(self, runner, tmp_path, monkeypatch):
        """adapter unblock on non-blocked adapter fails."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = runner.invoke(main, ["adapter", "unblock", "nonexistent"])
        assert result.exit_code != 0
        assert "Not found" in result.output

    def test_blocked_adapter_hidden_from_list(self, runner, tmp_path, monkeypatch):
        """Blocked adapter disappears from 'adapter list' output."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".git").mkdir()

        # Block git adapter
        runner.invoke(main, ["adapter", "block", "git", "-r", "test"])

        result = runner.invoke(main, ["adapter", "list", str(tmp_path)])
        assert result.exit_code == 0
        # Git should not be in connected section, but in blocked section
        assert "Blocked adapters:" in result.output
        assert "version_control/git" in result.output


# ─── evo adapter check-updates ───


class TestAdapterCheckUpdates:
    def test_check_updates_runs(self, runner, monkeypatch):
        """adapter check-updates command runs without error."""
        from unittest.mock import MagicMock, patch
        import json as _json

        # Mock PyPI response
        resp = MagicMock()
        resp.read.return_value = _json.dumps(
            {"info": {"version": "99.0.0"}}
        ).encode("utf-8")
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("evolution.adapter_versions.urllib.request.urlopen", return_value=resp):
            result = runner.invoke(main, ["adapter", "check-updates"])

        assert result.exit_code == 0
        assert "Checking for updates" in result.output


# ─── evo adapter report ───


class TestAdapterReport:
    def test_report_saves_locally(self, runner, tmp_path, monkeypatch):
        """adapter report saves report JSON to ~/.evo/adapter_reports/."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = runner.invoke(
            main,
            ["adapter", "report", "test-adapter", "-c", "crashes", "-d", "It broke"],
        )
        assert result.exit_code == 0
        assert "Report saved" in result.output

        # Check file was created
        reports_dir = tmp_path / ".evo" / "adapter_reports"
        report_files = list(reports_dir.glob("test-adapter_*.json"))
        assert len(report_files) == 1

        data = json.loads(report_files[0].read_text())
        assert data["adapter_name"] == "test-adapter"
        assert data["category"] == "crashes"
        assert data["description"] == "It broke"

    def test_report_without_github_token_shows_instructions(self, runner, tmp_path, monkeypatch):
        """adapter report without GITHUB_BOT_TOKEN shows manual filing instructions."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.delenv("GITHUB_BOT_TOKEN", raising=False)

        result = runner.invoke(
            main,
            ["adapter", "report", "test-adapter", "-c", "other", "-d", "test"],
        )
        assert result.exit_code == 0
        assert "github.com" in result.output.lower()


# ─── evo adapter list — trust badges ───


class TestAdapterListTrustBadges:
    def test_shows_builtin_badge(self, runner, tmp_path):
        """adapter list shows [built-in] badge for Tier 1 adapters."""
        (tmp_path / ".git").mkdir()
        result = runner.invoke(main, ["adapter", "list", str(tmp_path)])
        assert result.exit_code == 0
        assert "built-in" in result.output

    def test_json_includes_trust_level(self, runner, tmp_path):
        """adapter list --json includes trust_level field."""
        (tmp_path / ".git").mkdir()
        result = runner.invoke(main, ["adapter", "list", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(c["trust_level"] == "built-in" for c in data["connected"])

    def test_json_includes_blocked(self, runner, tmp_path, monkeypatch):
        """adapter list --json includes blocked section."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".git").mkdir()

        result = runner.invoke(main, ["adapter", "list", str(tmp_path), "--json"])
        data = json.loads(result.output)
        assert "blocked" in data


# ─── evo adapter validate --security ───


class TestAdapterValidateSecurity:
    def test_security_flag_runs_scan(self, runner, tmp_path):
        """adapter validate --security also runs security scan."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests==2.31.0\n")

        result = runner.invoke(
            main,
            ["adapter", "validate",
             "evolution.adapters.dependency.pip_adapter.PipDependencyAdapter",
             "--args", json.dumps({"lock_file": str(req_file)}),
             "--security"],
        )
        assert result.exit_code == 0
        assert "security scan" in result.output.lower() or "Security scan" in result.output


# ─── evo adapter list — inline update indicators ───


class TestAdapterListUpdateIndicators:
    def test_shows_update_available_for_plugin(self, runner, tmp_path, monkeypatch):
        """adapter list shows 'update available' when plugin has newer PyPI version."""
        (tmp_path / ".git").mkdir()

        # Mock a plugin entry point
        fake_ep = type("EP", (), {
            "name": "evo-adapter-fake",
            "load": lambda self: lambda: [
                {"adapter_name": "fake", "family": "ci",
                 "adapter_class": type("A", (), {
                     "FAMILY": "ci", "ADAPTER_NAME": "fake",
                     "iter_events": lambda s: iter([]),
                 }),
                 "detect_config": None}
            ]
        })()

        # Patch entry_points to return our fake plugin
        monkeypatch.setattr(
            "evolution.registry.entry_points",
            lambda **kw: [fake_ep] if kw.get("group") == "evo.adapters" else []
        )

        # Patch importlib.metadata.version to return old version
        monkeypatch.setattr("importlib.metadata.version", lambda name: "0.1.0")
        # Patch check_pypi_version to return newer version
        monkeypatch.setattr(
            "evolution.adapter_versions.check_pypi_version",
            lambda name, **kw: "0.2.0"
        )

        result = runner.invoke(main, ["adapter", "list", str(tmp_path)])
        assert result.exit_code == 0
        assert "update available: 0.2.0" in result.output

    def test_no_update_note_when_up_to_date(self, runner, tmp_path, monkeypatch):
        """adapter list does not show update note when version is current."""
        (tmp_path / ".git").mkdir()

        # Patch check_pypi_version to return same version
        monkeypatch.setattr(
            "evolution.adapter_versions.check_pypi_version",
            lambda name, **kw: "0.1.0"
        )
        monkeypatch.setattr("importlib.metadata.version", lambda name: "0.1.0")

        result = runner.invoke(main, ["adapter", "list", str(tmp_path)])
        assert result.exit_code == 0
        assert "update available" not in result.output
