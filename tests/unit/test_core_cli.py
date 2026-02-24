"""
Unit tests for the 5 core CLI commands: analyze, report, status, investigate, fix.

Uses Click's CliRunner for isolated command testing.
Mocks at module boundaries to avoid real I/O, AI calls, and filesystem side effects.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from evolution.cli import main
from evolution.fixer import FixIteration, FixResult
from evolution.investigator import InvestigationReport
from evolution.license import ProFeatureError


@pytest.fixture
def runner():
    return CliRunner()


# ──────────────── Analyze Helpers ────────────────


def _make_complete_result(**overrides):
    """Build a canned Orchestrator.run() result."""
    result = {
        "status": "complete",
        "advisory": {
            "status": {"icon": "⚠️", "label": "Needs Attention", "level": "needs_attention"},
            "significant_changes": 3,
            "families_affected": ["git", "ci"],
            "patterns_matched": 2,
        },
        "shareable_patterns": 0,
    }
    result.update(overrides)
    return result


def _make_no_events_result():
    return {"status": "no_events", "message": "No events found — nothing to analyze."}


@pytest.fixture
def _patch_analyze_side_effects(monkeypatch, tmp_path):
    """Autouse-style fixture to neutralize all side effects of the analyze command."""
    monkeypatch.setenv("EVO_CONFIG_DIR", str(tmp_path / "config"))

    patches = [
        patch("evolution.telemetry.prompt_consent"),
        patch("evolution.telemetry.track_event"),
        patch("evolution.adapter_versions.check_self_update_nudge", return_value=None),
        patch("evolution.notifications.check_and_notify", return_value=[]),
        patch("evolution.notifications.format_notifications", return_value=""),
        patch("evolution.config.EvoConfig"),
        patch("evolution.report_generator.generate_report", return_value="<html></html>"),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


# ──────────────── TestAnalyze ────────────────


class TestAnalyze:
    @pytest.fixture(autouse=True)
    def setup(self, _patch_analyze_side_effects):
        pass

    def test_analyze_happy_path(self, runner, tmp_path):
        """Successful run prints advisory summary."""
        mock_orch = MagicMock()
        mock_orch.run.return_value = _make_complete_result()

        with patch("evolution.orchestrator.Orchestrator", return_value=mock_orch):
            result = runner.invoke(main, ["analyze", str(tmp_path), "--no-report"])

        assert result.exit_code == 0
        assert "Needs Attention" in result.output
        assert "3 significant change(s)" in result.output
        assert "git" in result.output
        assert "ci" in result.output

    def test_analyze_no_events_exits_1(self, runner, tmp_path):
        """No events → exit 1 with message."""
        mock_orch = MagicMock()
        mock_orch.run.return_value = _make_no_events_result()

        with patch("evolution.orchestrator.Orchestrator", return_value=mock_orch):
            result = runner.invoke(main, ["analyze", str(tmp_path)])

        assert result.exit_code == 1
        assert "No events found" in result.output

    def test_analyze_json_output(self, runner, tmp_path):
        """--json outputs valid JSON with status."""
        mock_orch = MagicMock()
        mock_orch.run.return_value = _make_complete_result()

        with patch("evolution.orchestrator.Orchestrator", return_value=mock_orch):
            result = runner.invoke(main, ["analyze", str(tmp_path), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "complete"

    def test_analyze_quiet_suppresses_summary(self, runner, tmp_path):
        """--quiet suppresses advisory summary output."""
        mock_orch = MagicMock()
        mock_orch.run.return_value = _make_complete_result()

        with patch("evolution.orchestrator.Orchestrator", return_value=mock_orch):
            result = runner.invoke(main, ["analyze", str(tmp_path), "--quiet", "--no-report"])

        assert result.exit_code == 0
        assert "Needs Attention" not in result.output

    def test_analyze_no_report_flag(self, runner, tmp_path):
        """--no-report skips report generation."""
        mock_orch = MagicMock()
        mock_orch.run.return_value = _make_complete_result()

        with patch("evolution.orchestrator.Orchestrator", return_value=mock_orch) as orch_cls, \
             patch("evolution.report_generator.generate_report") as mock_gen:
            result = runner.invoke(main, ["analyze", str(tmp_path), "--no-report"])

        assert result.exit_code == 0
        mock_gen.assert_not_called()

    def test_analyze_show_prompt(self, runner, tmp_path):
        """--show-prompt prints INVESTIGATION PROMPT section."""
        mock_orch = MagicMock()
        mock_orch.run.return_value = _make_complete_result()

        # Seed the prompt file
        evo_path = tmp_path / ".evo" / "phase5"
        evo_path.mkdir(parents=True)
        (evo_path / "investigation_prompt.txt").write_text("Prompt content here")

        with patch("evolution.orchestrator.Orchestrator", return_value=mock_orch):
            result = runner.invoke(main, ["analyze", str(tmp_path), "--show-prompt", "--no-report"])

        assert result.exit_code == 0
        assert "INVESTIGATION PROMPT" in result.output
        assert "Prompt content here" in result.output

    def test_analyze_families_option(self, runner, tmp_path):
        """--families passes parsed list to Orchestrator."""
        mock_orch = MagicMock()
        mock_orch.run.return_value = _make_complete_result()

        with patch("evolution.orchestrator.Orchestrator", return_value=mock_orch) as orch_cls:
            result = runner.invoke(main, ["analyze", str(tmp_path), "--families", "git,ci", "--no-report"])

        assert result.exit_code == 0
        call_kwargs = orch_cls.call_args
        assert call_kwargs.kwargs.get("families") == ["git", "ci"] or \
               call_kwargs[1].get("families") == ["git", "ci"]

    def test_analyze_token_option(self, runner, tmp_path):
        """--token passes token dict to Orchestrator."""
        mock_orch = MagicMock()
        mock_orch.run.return_value = _make_complete_result()

        with patch("evolution.orchestrator.Orchestrator", return_value=mock_orch) as orch_cls:
            result = runner.invoke(main, ["analyze", str(tmp_path), "--token", "ghp_xxx", "--no-report"])

        assert result.exit_code == 0
        call_kwargs = orch_cls.call_args
        assert call_kwargs.kwargs.get("tokens") == {"github_token": "ghp_xxx"} or \
               call_kwargs[1].get("tokens") == {"github_token": "ghp_xxx"}


# ──────────────── Report Helpers ────────────────


@pytest.fixture
def seeded_advisory(tmp_path):
    """Write a minimal advisory.json so `evo report` finds it."""
    phase5 = tmp_path / ".evo" / "phase5"
    phase5.mkdir(parents=True)
    advisory = {
        "generated_at": "2026-02-20T10:00:00Z",
        "summary": {
            "significant_changes": 2,
            "families_affected": ["git"],
            "known_patterns_matched": 1,
        },
    }
    (phase5 / "advisory.json").write_text(json.dumps(advisory))
    return tmp_path


# ──────────────── TestReport ────────────────


class TestReport:
    def test_report_happy_path(self, runner, seeded_advisory):
        """Advisory exists → generates report, prints confirmation."""
        with patch("evolution.report_generator.generate_report", return_value="<html></html>"), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["report", str(seeded_advisory)])

        assert result.exit_code == 0
        assert "Report generated" in result.output

    def test_report_no_advisory_exits_1(self, runner, tmp_path):
        """No advisory.json → exit 1."""
        result = runner.invoke(main, ["report", str(tmp_path)])

        assert result.exit_code == 1
        assert "No advisory found" in result.output

    def test_report_custom_output_path(self, runner, seeded_advisory):
        """--output writes report to custom path."""
        custom = seeded_advisory / "custom_report.html"
        with patch("evolution.report_generator.generate_report", return_value="<html>custom</html>"), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["report", str(seeded_advisory), "--output", str(custom)])

        assert result.exit_code == 0
        assert custom.exists()
        assert custom.read_text() == "<html>custom</html>"

    def test_report_custom_title(self, runner, seeded_advisory):
        """--title passes title kwarg to generate_report."""
        with patch("evolution.report_generator.generate_report", return_value="<html></html>") as mock_gen, \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["report", str(seeded_advisory), "--title", "My Title"])

        assert result.exit_code == 0
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs.get("title") == "My Title" or \
               (len(call_kwargs.args) > 1 and call_kwargs.args[1] == "My Title")

    def test_report_serve_starts_server(self, runner, seeded_advisory):
        """--serve starts the report server."""
        mock_server = MagicMock()
        with patch("evolution.report_generator.generate_report", return_value="<html></html>"), \
             patch("evolution.telemetry.track_event"), \
             patch("evolution.report_server.ReportServer", return_value=mock_server):
            result = runner.invoke(main, ["report", str(seeded_advisory), "--serve"])

        assert result.exit_code == 0
        mock_server.serve.assert_called_once()

    def test_report_verify_loads_history(self, runner, seeded_advisory):
        """--verify calls HistoryManager.compare."""
        mock_hm = MagicMock()
        mock_hm.list_runs.return_value = [
            {"timestamp": "2026-02-20T12:00:00"},
            {"timestamp": "2026-02-20T10:00:00"},
        ]
        mock_hm.compare.return_value = {"summary_text": "Compared", "changes": []}

        with patch("evolution.report_generator.generate_report", return_value="<html></html>"), \
             patch("evolution.telemetry.track_event"), \
             patch("evolution.history.HistoryManager", return_value=mock_hm):
            result = runner.invoke(main, ["report", str(seeded_advisory), "--verify"])

        assert result.exit_code == 0
        mock_hm.compare.assert_called_once()


# ──────────────── TestStatus ────────────────


class TestStatus:
    def _make_summary(self, **overrides):
        summary = {
            "repo_path": "/tmp/repo",
            "adapters_detected": 3,
            "tier1_count": 2,
            "tier2_count": 1,
            "families": {
                "git": [{"adapter": "GitWalker", "tier": 1, "source": "local"}],
                "ci": [{"adapter": "GitHubActions", "tier": 2, "source": "api"}],
            },
            "missing_tokens": [],
        }
        summary.update(overrides)
        return summary

    def test_status_happy_path(self, runner, tmp_path):
        """Prints repository info, adapter counts, family names."""
        mock_registry = MagicMock()
        mock_registry.summary.return_value = self._make_summary()

        with patch("evolution.registry.AdapterRegistry", return_value=mock_registry):
            result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Repository:" in result.output
        assert "Adapters detected: 3" in result.output
        assert "git:" in result.output
        assert "ci:" in result.output

    def test_status_shows_missing_tokens(self, runner, tmp_path):
        """missing_tokens non-empty → 'Unlock more data' in output."""
        mock_registry = MagicMock()
        mock_registry.summary.return_value = self._make_summary(
            missing_tokens=["Set GITHUB_TOKEN for CI data"],
        )

        with patch("evolution.registry.AdapterRegistry", return_value=mock_registry):
            result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Unlock more data" in result.output

    def test_status_no_missing_tokens(self, runner, tmp_path):
        """missing_tokens empty → 'Unlock' NOT in output."""
        mock_registry = MagicMock()
        mock_registry.summary.return_value = self._make_summary(missing_tokens=[])

        with patch("evolution.registry.AdapterRegistry", return_value=mock_registry):
            result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Unlock" not in result.output

    def test_status_shows_last_advisory(self, runner, tmp_path):
        """advisory.json exists → 'Last advisory:' in output."""
        mock_registry = MagicMock()
        mock_registry.summary.return_value = self._make_summary()

        phase5 = tmp_path / ".evo" / "phase5"
        phase5.mkdir(parents=True)
        (phase5 / "advisory.json").write_text(json.dumps({
            "generated_at": "2026-02-20T10:00:00Z",
            "summary": {"significant_changes": 1, "families_affected": ["git"], "known_patterns_matched": 0},
        }))

        with patch("evolution.registry.AdapterRegistry", return_value=mock_registry):
            result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Last advisory:" in result.output

    def test_status_token_option(self, runner, tmp_path):
        """--token passes token dict to summary()."""
        mock_registry = MagicMock()
        mock_registry.summary.return_value = self._make_summary()

        with patch("evolution.registry.AdapterRegistry", return_value=mock_registry):
            result = runner.invoke(main, ["status", str(tmp_path), "--token", "ghp_xxx"])

        assert result.exit_code == 0
        mock_registry.summary.assert_called_once_with({"github_token": "ghp_xxx"})


# ──────────────── TestInvestigate ────────────────


class TestInvestigate:
    def _make_report(self, **overrides):
        defaults = {
            "text": "Root cause: dependency drift in ci pipeline",
            "advisory_id": "adv-001",
            "scope": "default",
            "agent_name": "anthropic",
            "success": True,
        }
        defaults.update(overrides)
        return InvestigationReport(**defaults)

    def test_investigate_happy_path(self, runner, tmp_path):
        """Prints 'Investigation complete', agent name, report text."""
        report = self._make_report()
        mock_inv = MagicMock()
        mock_inv.run.return_value = report

        with patch("evolution.license.require_pro"), \
             patch("evolution.investigator.Investigator", return_value=mock_inv), \
             patch("evolution.agents.base.get_agent"), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["investigate", str(tmp_path)])

        assert result.exit_code == 0
        assert "Investigation complete" in result.output
        assert "anthropic" in result.output
        assert "dependency drift" in result.output

    def test_investigate_no_pro_exits_1(self, runner, tmp_path):
        """require_pro raises ProFeatureError → exit 1."""
        with patch("evolution.license.require_pro", side_effect=ProFeatureError("AI Investigation")):
            result = runner.invoke(main, ["investigate", str(tmp_path)])

        assert result.exit_code == 1
        assert "Pro" in result.output

    def test_investigate_show_prompt(self, runner, tmp_path):
        """--show-prompt prints prompt text, no 'Investigation complete'."""
        report = self._make_report(text="PROMPT: Analyze the following advisory...")
        mock_inv = MagicMock()
        mock_inv.run.return_value = report

        with patch("evolution.license.require_pro"), \
             patch("evolution.investigator.Investigator", return_value=mock_inv):
            result = runner.invoke(main, ["investigate", str(tmp_path), "--show-prompt"])

        assert result.exit_code == 0
        assert "PROMPT: Analyze" in result.output
        assert "Investigation complete" not in result.output

    def test_investigate_no_advisory_exits_1(self, runner, tmp_path):
        """Investigator() raises FileNotFoundError → exit 1."""
        with patch("evolution.license.require_pro"), \
             patch("evolution.investigator.Investigator", side_effect=FileNotFoundError("No advisory")):
            result = runner.invoke(main, ["investigate", str(tmp_path)])

        assert result.exit_code == 1
        assert "No advisory" in result.output

    def test_investigate_failed_report(self, runner, tmp_path):
        """report.success=False → exit 1, 'Investigation failed'."""
        report = self._make_report(success=False, error="Agent timeout")
        mock_inv = MagicMock()
        mock_inv.run.return_value = report

        with patch("evolution.license.require_pro"), \
             patch("evolution.investigator.Investigator", return_value=mock_inv), \
             patch("evolution.agents.base.get_agent"):
            result = runner.invoke(main, ["investigate", str(tmp_path)])

        assert result.exit_code == 1
        assert "Investigation failed" in result.output

    def test_investigate_agent_option(self, runner, tmp_path):
        """--agent anthropic calls get_agent(prefer='anthropic')."""
        report = self._make_report()
        mock_inv = MagicMock()
        mock_inv.run.return_value = report

        with patch("evolution.license.require_pro"), \
             patch("evolution.investigator.Investigator", return_value=mock_inv), \
             patch("evolution.agents.base.get_agent") as mock_get_agent, \
             patch("evolution.telemetry.track_event"):
            mock_get_agent.return_value = MagicMock(name="anthropic")
            result = runner.invoke(main, ["investigate", str(tmp_path), "--agent", "anthropic"])

        assert result.exit_code == 0
        mock_get_agent.assert_called_once_with(prefer="anthropic", model=None)

    def test_investigate_ai_disclosure(self, runner, tmp_path):
        """Output contains AI disclosure notice."""
        report = self._make_report()
        mock_inv = MagicMock()
        mock_inv.run.return_value = report

        with patch("evolution.license.require_pro"), \
             patch("evolution.investigator.Investigator", return_value=mock_inv), \
             patch("evolution.agents.base.get_agent"), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["investigate", str(tmp_path)])

        assert result.exit_code == 0
        assert "[AI Disclosure]" in result.output


# ──────────────── TestFix ────────────────


class TestFix:
    def _make_fix_result(self, status="all_clear", iterations=None, **kwargs):
        if iterations is None:
            iterations = [FixIteration(
                iteration=1,
                agent_response="Applied fix to module.py",
                resolved=2,
                persisting=0,
                new_issues=0,
                regressions=0,
            )]
        defaults = {
            "status": status,
            "iterations": iterations,
            "branch": "evo/fix-20260220",
            "total_resolved": sum(it.resolved for it in iterations),
            "total_remaining": sum(it.persisting + it.new_issues for it in iterations),
        }
        defaults.update(kwargs)
        return FixResult(**defaults)

    def test_fix_dry_run(self, runner, tmp_path):
        """--dry-run prints 'DRY RUN', 'no files modified'."""
        fix_result = self._make_fix_result(dry_run=True)
        mock_fixer = MagicMock()
        mock_fixer.run.return_value = fix_result

        with patch("evolution.license.require_pro"), \
             patch("evolution.fixer.Fixer", return_value=mock_fixer), \
             patch("evolution.agents.base.get_agent"):
            result = runner.invoke(main, ["fix", str(tmp_path), "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "no files modified" in result.output

    def test_fix_no_pro_exits_1(self, runner, tmp_path):
        """require_pro raises ProFeatureError → exit 1."""
        with patch("evolution.license.require_pro", side_effect=ProFeatureError("AI Fix Loop")):
            result = runner.invoke(main, ["fix", str(tmp_path)])

        assert result.exit_code == 1
        assert "Pro" in result.output

    def test_fix_all_clear(self, runner, tmp_path):
        """status=all_clear → 'All advisory items resolved!'."""
        fix_result = self._make_fix_result(status="all_clear")
        mock_fixer = MagicMock()
        mock_fixer.run.return_value = fix_result

        evo_dir = tmp_path / ".evo"
        with patch("evolution.license.require_pro"), \
             patch("evolution.fixer.Fixer", return_value=mock_fixer), \
             patch("evolution.agents.base.get_agent"), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["fix", str(tmp_path), "--yes",
                                          "--evo-dir", str(evo_dir)])

        assert result.exit_code == 0
        assert "All advisory items resolved!" in result.output

    def test_fix_partial(self, runner, tmp_path):
        """status=partial → 'Some issues resolved'."""
        iterations = [FixIteration(
            iteration=1, agent_response="partial fix",
            resolved=1, persisting=1, new_issues=0, regressions=0,
        )]
        fix_result = self._make_fix_result(status="partial", iterations=iterations)
        mock_fixer = MagicMock()
        mock_fixer.run.return_value = fix_result

        evo_dir = tmp_path / ".evo"
        with patch("evolution.license.require_pro"), \
             patch("evolution.fixer.Fixer", return_value=mock_fixer), \
             patch("evolution.agents.base.get_agent"), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["fix", str(tmp_path), "--yes",
                                          "--evo-dir", str(evo_dir)])

        assert result.exit_code == 0
        assert "Some issues resolved" in result.output

    def test_fix_max_iterations(self, runner, tmp_path):
        """status=max_iterations → 'Max iterations'."""
        fix_result = self._make_fix_result(status="max_iterations")
        mock_fixer = MagicMock()
        mock_fixer.run.return_value = fix_result

        evo_dir = tmp_path / ".evo"
        with patch("evolution.license.require_pro"), \
             patch("evolution.fixer.Fixer", return_value=mock_fixer), \
             patch("evolution.agents.base.get_agent"), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["fix", str(tmp_path), "--yes",
                                          "--evo-dir", str(evo_dir)])

        assert result.exit_code == 0
        assert "Max iterations" in result.output

    def test_fix_yes_skips_confirmation(self, runner, tmp_path):
        """--yes skips interactive confirmation prompt."""
        fix_result = self._make_fix_result()
        mock_fixer = MagicMock()
        mock_fixer.run.return_value = fix_result

        evo_dir = tmp_path / ".evo"
        with patch("evolution.license.require_pro"), \
             patch("evolution.fixer.Fixer", return_value=mock_fixer), \
             patch("evolution.agents.base.get_agent"), \
             patch("evolution.telemetry.track_event"):
            # Without --yes and without input, click.confirm would abort
            result = runner.invoke(main, ["fix", str(tmp_path), "--yes",
                                          "--evo-dir", str(evo_dir)])

        assert result.exit_code == 0
        # If confirmation were shown without --yes, it would abort with no TTY input
        assert "Aborted" not in result.output

    def test_fix_dry_run_residual(self, runner, tmp_path):
        """--dry-run --residual prints 'DRY RUN (residual)'."""
        fix_result = self._make_fix_result(dry_run=True)
        mock_fixer = MagicMock()
        mock_fixer.run.return_value = fix_result

        with patch("evolution.license.require_pro"), \
             patch("evolution.fixer.Fixer", return_value=mock_fixer), \
             patch("evolution.agents.base.get_agent"):
            result = runner.invoke(main, ["fix", str(tmp_path), "--dry-run", "--residual"])

        assert result.exit_code == 0
        assert "DRY RUN (residual)" in result.output

    def test_fix_reports_branch_and_iterations(self, runner, tmp_path):
        """Output includes branch name, iteration details, resolved/remaining counts."""
        iterations = [
            FixIteration(iteration=1, agent_response="fix 1", resolved=2, persisting=1,
                         new_issues=0, regressions=0),
            FixIteration(iteration=2, agent_response="fix 2", resolved=1, persisting=0,
                         new_issues=0, regressions=0),
        ]
        fix_result = self._make_fix_result(
            status="all_clear", iterations=iterations,
            branch="evo/fix-20260220", total_resolved=3, total_remaining=0,
        )
        mock_fixer = MagicMock()
        mock_fixer.run.return_value = fix_result

        evo_dir = tmp_path / ".evo"
        with patch("evolution.license.require_pro"), \
             patch("evolution.fixer.Fixer", return_value=mock_fixer), \
             patch("evolution.agents.base.get_agent"), \
             patch("evolution.telemetry.track_event"):
            result = runner.invoke(main, ["fix", str(tmp_path), "--yes",
                                          "--evo-dir", str(evo_dir)])

        assert result.exit_code == 0
        assert "Branch: evo/fix-20260220" in result.output
        assert "Iterations: 2" in result.output
        assert "Resolved: 3" in result.output
        assert "Remaining: 0" in result.output
        assert "Iteration 1" in result.output
        assert "Iteration 2" in result.output
