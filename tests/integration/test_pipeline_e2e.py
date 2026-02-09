"""Integration test: full pipeline Phase 1 → 2 → 3 → 4 → 5 with fixture data."""

import json
from pathlib import Path

import pytest

from evolution.phase2_engine import Phase2Engine
from evolution.phase3_engine import Phase3Engine
from evolution.phase4_engine import Phase4Engine
from evolution.phase5_engine import Phase5Engine


class TestFullPipeline:
    """End-to-end pipeline test using conftest fixtures."""

    def test_phase2_produces_signals(self, populated_evo_dir):
        phase2 = Phase2Engine(populated_evo_dir, window_size=10, min_baseline=3)
        results = phase2.run_all()

        total = sum(len(s) for s in results.values())
        assert total > 0, "Phase 2 should produce signals"

        # At least git and dependency should have signals
        families_with_signals = [f for f, s in results.items() if s]
        assert "git" in families_with_signals
        assert "dependency" in families_with_signals

    def test_phase3_produces_explanations(self, populated_through_phase2):
        phase3 = Phase3Engine(populated_through_phase2)
        explanations = phase3.run()

        assert len(explanations) > 0
        # Every explanation should have required fields
        for exp in explanations:
            assert "engine_id" in exp
            assert "summary" in exp
            assert "details" in exp
            assert "metric" in exp["details"]

    def test_phase4_runs_without_error(self, populated_through_phase2):
        # Phase 3 must run first
        phase3 = Phase3Engine(populated_through_phase2)
        phase3.run()

        phase4 = Phase4Engine(populated_through_phase2, params={
            "min_support": 3,
            "min_correlation": 0.3,
            "promotion_threshold": 50,
        })
        result = phase4.run()
        phase4.close()

        assert result["status"] == "complete"
        assert result["total_signals"] > 0

    def test_phase5_produces_advisory(self, populated_through_phase2):
        # Phases 3+4 must run first
        phase3 = Phase3Engine(populated_through_phase2)
        phase3.run()

        phase4 = Phase4Engine(populated_through_phase2)
        phase4.run()
        phase4.close()

        phase5 = Phase5Engine(populated_through_phase2, significance_threshold=1.0)
        result = phase5.run(scope="test-repo")

        assert result["status"] == "complete"
        advisory = result["advisory"]
        assert advisory["scope"] == "test-repo"
        assert advisory["summary"]["significant_changes"] > 0
        assert len(advisory["changes"]) > 0

    def test_full_pipeline_produces_all_outputs(self, populated_through_phase2):
        evo = populated_through_phase2

        # Phase 3
        phase3 = Phase3Engine(evo)
        explanations = phase3.run()
        assert (evo / "phase3" / "explanations.json").exists()

        # Phase 4
        phase4 = Phase4Engine(evo)
        p4 = phase4.run()
        phase4.close()
        assert (evo / "phase4" / "phase4_summary.json").exists()
        assert (evo / "phase4" / "knowledge.db").exists()

        # Phase 5
        phase5 = Phase5Engine(evo, significance_threshold=1.0)
        p5 = phase5.run(scope="test-repo")
        assert (evo / "phase5" / "advisory.json").exists()
        assert (evo / "phase5" / "summary.txt").exists()
        assert (evo / "phase5" / "chat.txt").exists()
        assert (evo / "phase5" / "investigation_prompt.txt").exists()

        # Human summary should be non-empty
        summary = (evo / "phase5" / "summary.txt").read_text()
        assert "significant change" in summary.lower() or "Evolution Advisory" in summary

    def test_pipeline_signal_counts_are_consistent(self, populated_through_phase2):
        evo = populated_through_phase2

        # Count signals in Phase 2 output
        total_p2_signals = 0
        for f in (evo / "phase2").glob("*.json"):
            signals = json.loads(f.read_text())
            total_p2_signals += len(signals)

        # Phase 3 should explain all signals
        phase3 = Phase3Engine(evo)
        explanations = phase3.run()
        assert len(explanations) == total_p2_signals

    def test_degenerate_signals_excluded_from_advisory(self, populated_through_phase2):
        evo = populated_through_phase2

        phase3 = Phase3Engine(evo)
        phase3.run()

        phase4 = Phase4Engine(evo)
        phase4.run()
        phase4.close()

        phase5 = Phase5Engine(evo, significance_threshold=1.0)
        result = phase5.run(scope="test-repo")

        if result["status"] == "complete":
            for change in result["advisory"]["changes"]:
                assert change["deviation_unit"] != "degenerate", \
                    "Degenerate signals should not appear in advisory"
