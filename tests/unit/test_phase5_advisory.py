"""Unit tests for Phase 5 advisory engine."""

import json
from pathlib import Path

import pytest

from evolution.phase5_engine import Phase5Engine, METRIC_LABELS, FAMILY_LABELS


class TestSignificanceFilter:
    def _make_signal(self, deviation, degenerate=False, unit="modified_zscore"):
        return {
            "engine_id": "git",
            "source_type": "git",
            "metric": "files_touched",
            "window": {"type": "rolling", "size": 50},
            "baseline": {"mean": 5, "stddev": 2, "median": 5, "mad": 1.5},
            "observed": 20,
            "deviation": {
                "measure": deviation,
                "unit": unit,
                "degenerate": degenerate,
            },
            "confidence": {"sample_count": 30, "status": "sufficient"},
            "event_ref": "git-0001",
        }

    def test_above_threshold_included(self, evo_dir):
        engine = Phase5Engine(evo_dir, significance_threshold=1.5)
        signals = [self._make_signal(2.5)]
        result = engine._filter_significant(signals)
        assert len(result) == 1

    def test_below_threshold_excluded(self, evo_dir):
        engine = Phase5Engine(evo_dir, significance_threshold=1.5)
        signals = [self._make_signal(0.5)]
        result = engine._filter_significant(signals)
        assert len(result) == 0

    def test_negative_deviation_included(self, evo_dir):
        engine = Phase5Engine(evo_dir, significance_threshold=1.5)
        signals = [self._make_signal(-3.0)]
        result = engine._filter_significant(signals)
        assert len(result) == 1

    def test_degenerate_excluded(self, evo_dir):
        engine = Phase5Engine(evo_dir, significance_threshold=1.5)
        signals = [self._make_signal(5.0, degenerate=True, unit="degenerate")]
        result = engine._filter_significant(signals)
        assert len(result) == 0

    def test_none_measure_excluded(self, evo_dir):
        engine = Phase5Engine(evo_dir, significance_threshold=1.5)
        signals = [self._make_signal(None, degenerate=True, unit="degenerate")]
        result = engine._filter_significant(signals)
        assert len(result) == 0


class TestEventGrouping:
    def _make_change(self, family, metric, deviation, event_ref="evt-001"):
        return {
            "family": family,
            "metric": metric,
            "deviation_stddev": deviation,
            "event_ref": event_ref,
            "normal": {"mean": 5, "stddev": 2, "median": 5, "mad": 1.5},
            "current": 20,
        }

    def test_groups_by_event_ref(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        changes = [
            self._make_change("git", "files_touched", 3.5, "evt-001"),
            self._make_change("ci", "run_duration", 2.1, "evt-001"),
            self._make_change("git", "dispersion", 1.8, "evt-002"),
        ]
        groups = engine._group_by_trigger_event(changes)

        assert len(groups) == 2  # Two distinct event_refs
        # First group should be evt-001 (higher primary deviation)
        assert groups[0]["signal_count"] == 2
        assert groups[0]["event_ref"] == "evt-001"

    def test_ungrouped_as_singletons(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        changes = [
            self._make_change("git", "files_touched", 3.5, ""),
        ]
        groups = engine._group_by_trigger_event(changes)
        assert len(groups) == 1
        assert groups[0]["event_ref"] is None
        assert groups[0]["signal_count"] == 1

    def test_sorted_by_primary_deviation(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        changes = [
            self._make_change("git", "files_touched", 1.5, "evt-low"),
            self._make_change("ci", "run_duration", 5.0, "evt-high"),
        ]
        groups = engine._group_by_trigger_event(changes)
        assert groups[0]["primary"]["deviation_stddev"] == 5.0


class TestCompoundKeyExplanationLookup:
    def test_compound_key_match(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        explanations = {
            "git-0001:git:files_touched": {
                "summary": "Matched by compound key",
                "engine_id": "git",
                "details": {"metric": "files_touched"},
            },
            "git:files_touched": {
                "summary": "Fallback match",
                "engine_id": "git",
                "details": {"metric": "files_touched"},
            },
        }

        signal = {
            "engine_id": "git",
            "source_type": "git",
            "metric": "files_touched",
            "baseline": {"mean": 5, "stddev": 2, "median": 5, "mad": 1.5},
            "observed": 20,
            "deviation": {"measure": 3.0, "unit": "modified_zscore", "degenerate": False},
            "event_ref": "git-0001",
        }

        change = engine._format_change(signal, explanations)
        assert change["description"] == "Matched by compound key"

    def test_fallback_key_match(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        explanations = {
            "git:files_touched": {
                "summary": "Fallback match",
                "engine_id": "git",
                "details": {"metric": "files_touched"},
            },
        }

        signal = {
            "engine_id": "git",
            "source_type": "git",
            "metric": "files_touched",
            "baseline": {"mean": 5, "stddev": 2, "median": 5, "mad": 1.5},
            "observed": 20,
            "deviation": {"measure": 3.0, "unit": "modified_zscore", "degenerate": False},
            "event_ref": "git-9999",  # not in explanations
        }

        change = engine._format_change(signal, explanations)
        assert change["description"] == "Fallback match"


class TestChangeFormat:
    def test_format_includes_all_fields(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        signal = {
            "engine_id": "git",
            "source_type": "git",
            "metric": "files_touched",
            "baseline": {"mean": 5, "stddev": 2, "median": 5, "mad": 1.5},
            "observed": 20,
            "deviation": {"measure": 3.0, "unit": "modified_zscore", "degenerate": False},
            "confidence": {"sample_count": 30, "status": "sufficient"},
            "event_ref": "git-0001",
        }

        change = engine._format_change(signal, {})
        assert change["family"] == "git"
        assert change["metric"] == "files_touched"
        assert change["current"] == 20
        assert change["deviation_stddev"] == 3.0
        assert change["deviation_unit"] == "modified_zscore"
        assert "mean" in change["normal"]
        assert "median" in change["normal"]


class TestAdvisoryDiff:
    def test_resolved_change(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        before = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 3.0},
            ],
        }
        after = {
            "changes": [],
        }
        diff = engine._diff_advisories(before, after)
        assert len(diff["resolved"]) == 1
        assert len(diff["persisting"]) == 0

    def test_persisting_change(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        before = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 3.0},
            ],
        }
        after = {
            "changes": [
                {"family": "git", "metric": "files_touched", "deviation_stddev": 2.0},
            ],
        }
        diff = engine._diff_advisories(before, after)
        assert len(diff["resolved"]) == 0
        assert len(diff["persisting"]) == 1
        assert diff["persisting"][0]["improved"] is True

    def test_new_observation(self, evo_dir):
        engine = Phase5Engine(evo_dir)
        before = {
            "changes": [],
        }
        after = {
            "changes": [
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 2.5},
            ],
        }
        diff = engine._diff_advisories(before, after)
        assert len(diff["new"]) == 1


class TestEnrichWithLatestDeviation:
    """Test _enrich_with_latest_deviation."""

    def _make_signal(self, engine_id, metric, deviation, event_ref):
        return {
            "engine_id": engine_id,
            "metric": metric,
            "observed": 20,
            "baseline": {"mean": 5, "stddev": 2, "median": 5, "mad": 1.5},
            "deviation": {"measure": deviation, "unit": "modified_zscore", "degenerate": False},
            "event_ref": event_ref,
        }

    def _make_event(self, event_id, timestamp):
        return {
            "event_id": event_id,
            "source_type": "git",
            "observed_at": timestamp,
            "payload": {"commit_hash": f"abc{event_id}", "timestamp": timestamp},
        }

    def test_latest_event_is_trigger(self, evo_dir):
        """When the trigger IS the latest event, is_latest_event=True."""
        engine = Phase5Engine(evo_dir)
        changes = [{
            "family": "git", "metric": "files_touched",
            "deviation_stddev": 3.0, "event_ref": "evt-002",
        }]
        signals = [
            self._make_signal("git", "files_touched", 2.0, "evt-001"),
            self._make_signal("git", "files_touched", 3.0, "evt-002"),
        ]
        events = {
            "evt-001": self._make_event("evt-001", "2025-01-01T00:00:00Z"),
            "evt-002": self._make_event("evt-002", "2025-01-02T00:00:00Z"),
        }
        engine._enrich_with_latest_deviation(changes, signals, events)
        assert changes[0]["is_latest_event"] is True
        assert changes[0]["latest_deviation"] == 3.0
        assert changes[0]["latest_value"] == 20  # from _make_signal observed

    def test_transient_historical(self, evo_dir):
        """Latest signal deviation < 1.5 → transient (returned to normal)."""
        engine = Phase5Engine(evo_dir)
        changes = [{
            "family": "git", "metric": "files_touched",
            "deviation_stddev": 4.0, "event_ref": "evt-001",
        }]
        signals = [
            self._make_signal("git", "files_touched", 4.0, "evt-001"),
            self._make_signal("git", "files_touched", 0.5, "evt-002"),
        ]
        events = {
            "evt-001": self._make_event("evt-001", "2025-01-01T00:00:00Z"),
            "evt-002": self._make_event("evt-002", "2025-01-02T00:00:00Z"),
        }
        engine._enrich_with_latest_deviation(changes, signals, events)
        assert changes[0]["is_latest_event"] is False
        assert changes[0]["latest_deviation"] == 0.5
        assert "latest_value" in changes[0]

    def test_persistent_historical(self, evo_dir):
        """Latest signal deviation >= 1.5 → persistent (still elevated)."""
        engine = Phase5Engine(evo_dir)
        changes = [{
            "family": "git", "metric": "files_touched",
            "deviation_stddev": 4.0, "event_ref": "evt-001",
        }]
        signals = [
            self._make_signal("git", "files_touched", 4.0, "evt-001"),
            self._make_signal("git", "files_touched", 2.5, "evt-002"),
        ]
        events = {
            "evt-001": self._make_event("evt-001", "2025-01-01T00:00:00Z"),
            "evt-002": self._make_event("evt-002", "2025-01-02T00:00:00Z"),
        }
        engine._enrich_with_latest_deviation(changes, signals, events)
        assert changes[0]["is_latest_event"] is False
        assert changes[0]["latest_deviation"] == 2.5

    def test_no_matching_signals(self, evo_dir):
        """No matching signals → fields not set."""
        engine = Phase5Engine(evo_dir)
        changes = [{
            "family": "git", "metric": "files_touched",
            "deviation_stddev": 3.0, "event_ref": "evt-001",
        }]
        signals = [
            self._make_signal("ci", "run_duration", 2.0, "evt-002"),
        ]
        events = {
            "evt-002": self._make_event("evt-002", "2025-01-02T00:00:00Z"),
        }
        engine._enrich_with_latest_deviation(changes, signals, events)
        assert "latest_deviation" not in changes[0]
        assert "is_latest_event" not in changes[0]
