"""Tests for shareable pattern counting and post-analyze sharing prompt."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from evolution.knowledge_store import SQLiteKnowledgeStore


class TestCountShareablePatterns:
    """Test Orchestrator._count_shareable_patterns()."""

    def _make_orchestrator(self, tmp_path, monkeypatch):
        """Create a minimal orchestrator for testing."""
        from evolution.orchestrator import Orchestrator

        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        evo_dir = repo / ".evo"
        evo_dir.mkdir()
        (evo_dir / "phase4").mkdir()

        orch = Orchestrator(repo_path=str(repo), evo_dir=str(evo_dir))
        return orch

    def test_returns_zero_when_no_db(self, tmp_path, monkeypatch):
        """No knowledge.db → 0 shareable patterns."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        assert orch._count_shareable_patterns() == 0

    def test_returns_zero_for_empty_db(self, tmp_path, monkeypatch):
        """Empty knowledge.db → 0 shareable patterns."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        db_path = orch.evo_dir / "phase4" / "knowledge.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()
        assert orch._count_shareable_patterns() == 0

    def test_counts_strong_patterns(self, tmp_path, monkeypatch):
        """Patterns with |corr| >= 0.3 and occurrences >= 3 are shareable."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        db_path = orch.evo_dir / "phase4" / "knowledge.db"
        kb = SQLiteKnowledgeStore(db_path)

        # Strong pattern — shareable
        kb.create_pattern({
            "fingerprint": "strong111aaa",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": 0.65,
            "occurrence_count": 10,
            "confidence_tier": "statistical",
        })

        # Weak pattern — not shareable
        kb.create_pattern({
            "fingerprint": "weak222bbb",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["dispersion", "run_duration"],
            "correlation_strength": -0.065,
            "occurrence_count": 5,
            "confidence_tier": "statistical",
        })

        # Too few occurrences — not shareable
        kb.create_pattern({
            "fingerprint": "few333ccc",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "dependency"],
            "metrics": ["files_touched", "dependency_count"],
            "correlation_strength": 0.5,
            "occurrence_count": 2,
            "confidence_tier": "statistical",
        })
        kb.close()

        assert orch._count_shareable_patterns() == 1

    def test_excludes_community_patterns(self, tmp_path, monkeypatch):
        """Community patterns should not be counted as shareable."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        db_path = orch.evo_dir / "phase4" / "knowledge.db"
        kb = SQLiteKnowledgeStore(db_path)

        kb.create_pattern({
            "fingerprint": "community111aaa",
            "scope": "community",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": 0.8,
            "occurrence_count": 20,
            "confidence_tier": "confirmed",
        })
        kb.close()

        assert orch._count_shareable_patterns() == 0

    def test_strong_negative_correlation_is_shareable(self, tmp_path, monkeypatch):
        """Strong negative correlation (|corr| >= 0.3) should be shareable."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        db_path = orch.evo_dir / "phase4" / "knowledge.db"
        kb = SQLiteKnowledgeStore(db_path)

        kb.create_pattern({
            "fingerprint": "negcorr111aaa",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": -0.45,
            "occurrence_count": 5,
            "confidence_tier": "statistical",
        })
        kb.close()

        assert orch._count_shareable_patterns() == 1


class TestSharePromptConfig:
    """Test that sync.share_prompted default is in config."""

    def test_share_prompted_default(self, tmp_path):
        from evolution.config import EvoConfig
        cfg = EvoConfig(path=tmp_path / "config.toml")
        assert cfg.get("sync.share_prompted") is False


class TestSharePromptCLI:
    """Test the post-analyze sharing prompt in the CLI."""

    def test_prompt_shown_when_shareable_patterns(self, tmp_path, monkeypatch):
        """Sharing prompt appears when shareable_patterns > 0 and not yet prompted."""
        from click.testing import CliRunner
        from evolution.cli import analyze

        runner = CliRunner()

        mock_result = {
            "status": "complete",
            "scope": "test",
            "repo_path": str(tmp_path),
            "evo_dir": str(tmp_path / ".evo"),
            "events": 10,
            "families": ["version_control"],
            "family_counts": {"version_control": 10},
            "signals": 5,
            "signal_counts": {"version_control": 5},
            "explanations": 3,
            "phase4": {"patterns_discovered": 1, "patterns_recognized": 0, "knowledge_artifacts": 0},
            "advisory_status": "complete",
            "elapsed_seconds": 1.0,
            "shareable_patterns": 3,
            "advisory": {
                "significant_changes": 2,
                "families_affected": ["version_control"],
                "patterns_matched": 1,
                "status": {"icon": "", "label": "Complete", "level": "info"},
            },
        }

        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda key, default=None: {
            "sync.share_prompted": False,
            "sync.privacy_level": 0,
        }.get(key, default)

        with patch("evolution.orchestrator.Orchestrator") as MockOrch, \
             patch("evolution.telemetry.prompt_consent"), \
             patch("evolution.telemetry.track_event"), \
             patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.report_generator.generate_report", return_value="<html></html>"), \
             patch("evolution.cli.sys") as mock_sys:
            mock_sys.stdout.isatty.return_value = True
            mock_sys.exit = MagicMock()
            mock_orch_instance = MagicMock()
            mock_orch_instance.run.return_value = mock_result
            MockOrch.return_value = mock_orch_instance

            result = runner.invoke(analyze, [str(tmp_path)], input="n\n")

        assert "pattern(s) ready to share" in result.output
        assert "No problem" in result.output

    def test_prompt_not_shown_when_already_prompted(self, tmp_path, monkeypatch):
        """Sharing prompt does not appear when sync.share_prompted=True."""
        from click.testing import CliRunner
        from evolution.cli import analyze

        runner = CliRunner()

        mock_result = {
            "status": "complete",
            "scope": "test",
            "repo_path": str(tmp_path),
            "evo_dir": str(tmp_path / ".evo"),
            "events": 10,
            "families": ["version_control"],
            "family_counts": {"version_control": 10},
            "signals": 5,
            "signal_counts": {"version_control": 5},
            "explanations": 3,
            "phase4": {"patterns_discovered": 1, "patterns_recognized": 0, "knowledge_artifacts": 0},
            "advisory_status": "complete",
            "elapsed_seconds": 1.0,
            "shareable_patterns": 3,
            "advisory": {
                "significant_changes": 2,
                "families_affected": ["version_control"],
                "patterns_matched": 1,
                "status": {"icon": "", "label": "Complete", "level": "info"},
            },
        }

        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda key, default=None: {
            "sync.share_prompted": True,  # already prompted
            "sync.privacy_level": 0,
        }.get(key, default)

        with patch("evolution.orchestrator.Orchestrator") as MockOrch, \
             patch("evolution.telemetry.prompt_consent"), \
             patch("evolution.telemetry.track_event"), \
             patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.report_generator.generate_report", return_value="<html></html>"):
            mock_orch_instance = MagicMock()
            mock_orch_instance.run.return_value = mock_result
            MockOrch.return_value = mock_orch_instance

            result = runner.invoke(analyze, [str(tmp_path)])

        assert "pattern(s) ready to share" not in result.output

    def test_prompt_not_shown_when_already_sharing(self, tmp_path, monkeypatch):
        """Sharing prompt does not appear when privacy_level already >= 2."""
        from click.testing import CliRunner
        from evolution.cli import analyze

        runner = CliRunner()

        mock_result = {
            "status": "complete",
            "scope": "test",
            "repo_path": str(tmp_path),
            "evo_dir": str(tmp_path / ".evo"),
            "events": 10,
            "families": ["version_control"],
            "family_counts": {"version_control": 10},
            "signals": 5,
            "signal_counts": {"version_control": 5},
            "explanations": 3,
            "phase4": {"patterns_discovered": 1, "patterns_recognized": 0, "knowledge_artifacts": 0},
            "advisory_status": "complete",
            "elapsed_seconds": 1.0,
            "shareable_patterns": 3,
            "advisory": {
                "significant_changes": 2,
                "families_affected": ["version_control"],
                "patterns_matched": 1,
                "status": {"icon": "", "label": "Complete", "level": "info"},
            },
        }

        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda key, default=None: {
            "sync.share_prompted": False,
            "sync.privacy_level": 2,  # already sharing
        }.get(key, default)

        with patch("evolution.orchestrator.Orchestrator") as MockOrch, \
             patch("evolution.telemetry.prompt_consent"), \
             patch("evolution.telemetry.track_event"), \
             patch("evolution.config.EvoConfig", return_value=mock_cfg), \
             patch("evolution.report_generator.generate_report", return_value="<html></html>"):
            mock_orch_instance = MagicMock()
            mock_orch_instance.run.return_value = mock_result
            MockOrch.return_value = mock_orch_instance

            result = runner.invoke(analyze, [str(tmp_path)])

        assert "pattern(s) ready to share" not in result.output
