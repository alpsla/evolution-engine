"""Unit tests for the investigator module."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from evolution.agents.base import AgentResult, ShowPromptAgent
from evolution.investigator import InvestigationReport, Investigator


@pytest.fixture
def evo_dir_with_advisory(tmp_path):
    """Create an .evo dir with a Phase 5 advisory and investigation prompt."""
    phase5 = tmp_path / "phase5"
    phase5.mkdir(parents=True)

    advisory = {
        "advisory_id": "abc123",
        "scope": "test-repo",
        "generated_at": "2026-02-09T00:00:00Z",
        "period": {"from": "2026-01-01T00:00:00Z", "to": "2026-02-09T00:00:00Z"},
        "summary": {
            "significant_changes": 3,
            "families_affected": ["git", "ci"],
            "known_patterns_matched": 1,
            "candidate_patterns_matched": 1,
        },
        "changes": [
            {
                "family": "git",
                "metric": "files_touched",
                "normal": {"mean": 4.5, "stddev": 3.0, "median": 3.0, "mad": 1.5},
                "current": 47,
                "deviation_stddev": 14.2,
                "deviation_unit": "modified_zscore",
                "description": "This commit touched 47 files — about 10x more than usual",
                "event_ref": "evt1",
            },
            {
                "family": "ci",
                "metric": "run_duration",
                "normal": {"mean": 45, "stddev": 15, "median": 40, "mad": 10},
                "current": 340,
                "deviation_stddev": 19.7,
                "deviation_unit": "modified_zscore",
                "description": "CI took 340s — about 8x longer than usual",
                "event_ref": "evt2",
            },
            {
                "family": "git",
                "metric": "dispersion",
                "normal": {"mean": 0.3, "stddev": 0.2, "median": 0.25, "mad": 0.1},
                "current": 0.92,
                "deviation_stddev": 4.5,
                "deviation_unit": "modified_zscore",
                "description": "Changes were spread across many unrelated areas",
                "event_ref": "evt1",
            },
        ],
        "pattern_matches": [
            {
                "knowledge_id": "k1",
                "sources": ["git", "ci"],
                "description": "CI-triggering commits tend to be more dispersed",
            },
        ],
        "candidate_patterns": [
            {
                "pattern_id": "p1",
                "families": ["git", "dependency"],
                "description": "Dependency changes correlate with high dispersion",
            },
        ],
        "evidence": {
            "commits": [
                {
                    "sha": "abc123def456",
                    "message": "Refactor auth module across packages",
                    "files_changed": ["auth/login.py", "auth/oauth.py", "tests/test_auth.py"],
                },
            ],
            "timeline": [
                {"timestamp": "2026-02-09T12:00:00Z", "family": "git", "event": "Large commit"},
            ],
        },
    }

    (phase5 / "advisory.json").write_text(json.dumps(advisory))

    prompt = (
        "Here is a structural analysis of test-repo over the period "
        "2026-01-01 to 2026-02-09.\n\n"
        "CHANGES DETECTED:\n"
        "- Git / Files Changed: normally 4.5, now 47 (14.2 stddev deviation)\n"
        "- CI / Build Duration: normally 45, now 340 (19.7 stddev deviation)\n"
    )
    (phase5 / "investigation_prompt.txt").write_text(prompt)

    return tmp_path


@pytest.fixture
def evo_dir_no_prompt(tmp_path):
    """Advisory exists but no pre-built investigation prompt."""
    phase5 = tmp_path / "phase5"
    phase5.mkdir(parents=True)

    advisory = {
        "advisory_id": "def456",
        "scope": "minimal-repo",
        "period": {"from": "2026-01-01", "to": "2026-02-09"},
        "changes": [
            {
                "family": "git",
                "metric": "files_touched",
                "normal": {"mean": 3.0},
                "current": 20,
                "deviation_stddev": 5.7,
            },
        ],
        "pattern_matches": [],
        "candidate_patterns": [],
    }
    (phase5 / "advisory.json").write_text(json.dumps(advisory))
    return tmp_path


class TestInvestigatorPrompt:
    def test_loads_existing_prompt(self, evo_dir_with_advisory):
        inv = Investigator(evo_dir=evo_dir_with_advisory)
        prompt, advisory = inv.get_prompt()

        assert "test-repo" in prompt
        assert "CHANGES DETECTED" in prompt
        assert advisory["advisory_id"] == "abc123"

    def test_builds_fallback_prompt(self, evo_dir_no_prompt):
        inv = Investigator(evo_dir=evo_dir_no_prompt)
        prompt, advisory = inv.get_prompt()

        assert "minimal-repo" in prompt
        assert "files_touched" in prompt
        assert advisory["advisory_id"] == "def456"

    def test_appends_pattern_context(self, evo_dir_with_advisory):
        inv = Investigator(evo_dir=evo_dir_with_advisory)
        prompt, _ = inv.get_prompt()

        assert "KNOWN PATTERNS MATCHED" in prompt
        assert "CI-triggering commits" in prompt
        assert "CANDIDATE PATTERNS" in prompt

    def test_missing_advisory_raises(self, tmp_path):
        (tmp_path / "phase5").mkdir(parents=True)
        inv = Investigator(evo_dir=tmp_path)
        with pytest.raises(FileNotFoundError, match="No advisory found"):
            inv.get_prompt()


class TestInvestigatorRun:
    def test_show_prompt_mode(self, evo_dir_with_advisory):
        inv = Investigator(evo_dir=evo_dir_with_advisory)
        report = inv.run(show_prompt=True)

        assert report.success is True
        assert report.agent_name == "show-prompt"
        assert "SYSTEM PROMPT" in report.text
        assert "USER PROMPT" in report.text

    def test_run_with_mock_agent(self, evo_dir_with_advisory):
        mock_agent = MagicMock()
        mock_agent.name = "mock-agent"
        mock_agent.complete.return_value = AgentResult(
            text="## Finding 1: files_touched\nRisk: High\nRoot cause: Auth refactor",
            success=True,
            model="mock",
        )

        inv = Investigator(evo_dir=evo_dir_with_advisory)
        report = inv.run(agent=mock_agent)

        assert report.success is True
        assert "files_touched" in report.text
        assert report.agent_name == "mock-agent"
        assert report.advisory_id == "abc123"

        # Verify agent was called with correct prompt
        mock_agent.complete.assert_called_once()
        call_args = mock_agent.complete.call_args
        assert "test-repo" in call_args.args[0]  # prompt
        assert "system" in call_args.kwargs

    def test_run_saves_outputs(self, evo_dir_with_advisory):
        mock_agent = MagicMock()
        mock_agent.name = "mock"
        mock_agent.complete.return_value = AgentResult(
            text="Investigation findings here",
            success=True,
        )

        inv = Investigator(evo_dir=evo_dir_with_advisory)
        inv.run(agent=mock_agent)

        # Check outputs saved
        output_dir = evo_dir_with_advisory / "investigation"
        assert (output_dir / "investigation.json").exists()
        assert (output_dir / "investigation.txt").exists()

        data = json.loads((output_dir / "investigation.json").read_text())
        assert data["scope"] == "test-repo"
        assert data["success"] is True

        text = (output_dir / "investigation.txt").read_text()
        assert text == "Investigation findings here"

    def test_agent_failure_propagated(self, evo_dir_with_advisory):
        mock_agent = MagicMock()
        mock_agent.name = "failing-agent"
        mock_agent.complete.return_value = AgentResult(
            text="",
            success=False,
            error="Rate limited",
        )

        inv = Investigator(evo_dir=evo_dir_with_advisory)
        report = inv.run(agent=mock_agent)

        assert report.success is False
        assert report.error == "Rate limited"


class TestInvestigationReport:
    def test_to_dict(self):
        report = InvestigationReport(
            text="findings",
            advisory_id="abc",
            scope="test",
            agent_name="mock",
        )
        d = report.to_dict()
        assert d["investigation_id"] == "abc"
        assert d["scope"] == "test"
        assert d["success"] is True
        assert "generated_at" in d

    def test_error_report(self):
        report = InvestigationReport(
            text="",
            advisory_id="abc",
            scope="test",
            agent_name="mock",
            success=False,
            error="timeout",
        )
        d = report.to_dict()
        assert d["success"] is False
        assert d["error"] == "timeout"
