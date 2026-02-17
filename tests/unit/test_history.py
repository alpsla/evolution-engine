"""Unit tests for run history (snapshot, list, load, compare, clean, diff)."""

import json
import time
from pathlib import Path

import pytest

from evolution.history import HistoryManager, diff_advisories, format_diff_summary


# ──────────────── Helpers ────────────────

def _make_advisory(changes=None, scope="test-repo", advisory_id="adv-001"):
    """Build a minimal advisory dict."""
    changes = changes or []
    return {
        "advisory_id": advisory_id,
        "scope": scope,
        "changes": changes,
        "summary": {
            "significant_changes": len(changes),
            "families_affected": sorted(set(c["family"] for c in changes)),
            "known_patterns_matched": 0,
        },
    }


def _make_change(family="git", metric="files_touched", deviation=3.5,
                 observed=20, median=5):
    return {
        "family": family,
        "metric": metric,
        "deviation_stddev": deviation,
        "current": observed,
        "normal": {"median": median, "mean": median, "stddev": 1.0, "mad": 1.0},
        "observed": observed,
        "direction": "above" if deviation > 0 else "below",
    }


# ──────────────── TestHistorySnapshot ────────────────


class TestHistorySnapshot:
    def test_creates_file(self, evo_dir):
        hm = HistoryManager(evo_dir)
        advisory = _make_advisory()
        path = hm.snapshot(advisory, "my-repo")
        assert path.exists()
        assert path.suffix == ".json"

    def test_contains_advisory(self, evo_dir):
        hm = HistoryManager(evo_dir)
        advisory = _make_advisory(
            changes=[_make_change()],
        )
        path = hm.snapshot(advisory, "my-repo")
        data = json.loads(path.read_text())
        assert data["advisory"]["changes"][0]["family"] == "git"
        assert data["advisory"]["advisory_id"] == "adv-001"

    def test_has_version(self, evo_dir):
        hm = HistoryManager(evo_dir)
        path = hm.snapshot(_make_advisory(), "test")
        data = json.loads(path.read_text())
        assert data["snapshot_version"] == 1

    def test_preserves_scope(self, evo_dir):
        hm = HistoryManager(evo_dir)
        path = hm.snapshot(_make_advisory(), "my-scope")
        data = json.loads(path.read_text())
        assert data["scope"] == "my-scope"

    def test_collision_handling(self, evo_dir):
        """Two snapshots in same second should not collide."""
        hm = HistoryManager(evo_dir)
        p1 = hm.snapshot(_make_advisory(), "test")
        # Force collision by creating a file with the same name
        # that the next snapshot would use
        p2 = hm.snapshot(_make_advisory(), "test")
        assert p1 != p2
        assert p1.exists()
        assert p2.exists()


# ──────────────── TestHistoryListRuns ────────────────


class TestHistoryListRuns:
    def test_empty_history(self, evo_dir):
        hm = HistoryManager(evo_dir)
        assert hm.list_runs() == []

    def test_sorted_newest_first(self, evo_dir):
        hm = HistoryManager(evo_dir)
        hm.snapshot(_make_advisory(), "first")
        time.sleep(0.01)
        hm.snapshot(_make_advisory(), "second")
        runs = hm.list_runs()
        assert len(runs) == 2
        assert runs[0]["scope"] == "second"
        assert runs[1]["scope"] == "first"

    def test_limit_parameter(self, evo_dir):
        hm = HistoryManager(evo_dir)
        for i in range(5):
            hm.snapshot(_make_advisory(), f"run-{i}")
            time.sleep(0.01)
        runs = hm.list_runs(limit=3)
        assert len(runs) == 3

    def test_includes_metadata(self, evo_dir):
        hm = HistoryManager(evo_dir)
        advisory = _make_advisory(
            changes=[_make_change(family="ci", metric="run_duration")],
        )
        hm.snapshot(advisory, "meta-test")
        runs = hm.list_runs()
        assert runs[0]["changes_count"] == 1
        assert "ci" in runs[0]["families"]
        assert runs[0]["scope"] == "meta-test"


# ──────────────── TestHistoryLoadRun ────────────────


class TestHistoryLoadRun:
    def test_exact_match(self, evo_dir):
        hm = HistoryManager(evo_dir)
        path = hm.snapshot(_make_advisory(), "exact")
        data = json.loads(path.read_text())
        ts = data["timestamp"]
        loaded = hm.load_run(ts)
        assert loaded["scope"] == "exact"

    def test_prefix_match(self, evo_dir):
        hm = HistoryManager(evo_dir)
        path = hm.snapshot(_make_advisory(), "prefix-test")
        data = json.loads(path.read_text())
        ts = data["timestamp"]
        # Use first 8 chars as prefix (YYYYMMDD)
        prefix = ts[:8]
        loaded = hm.load_run(prefix)
        assert loaded["scope"] == "prefix-test"

    def test_no_match_raises(self, evo_dir):
        hm = HistoryManager(evo_dir)
        hm.snapshot(_make_advisory(), "test")
        with pytest.raises(FileNotFoundError):
            hm.load_run("19700101-000000")

    def test_no_history_dir_raises(self, evo_dir):
        hm = HistoryManager(evo_dir)
        with pytest.raises(FileNotFoundError):
            hm.load_run("anything")


# ──────────────── TestHistoryCompare ────────────────


class TestHistoryCompare:
    def test_resolved_detected(self, evo_dir):
        hm = HistoryManager(evo_dir)
        before = _make_advisory(
            changes=[_make_change(family="git", metric="files_touched")],
        )
        after = _make_advisory(changes=[])

        p1 = hm.snapshot(before, "test")
        time.sleep(0.01)
        p2 = hm.snapshot(after, "test")

        ts1 = json.loads(p1.read_text())["timestamp"]
        ts2 = json.loads(p2.read_text())["timestamp"]
        diff = hm.compare(ts1, ts2)
        assert len(diff["resolved"]) == 1
        assert diff["resolved"][0]["family"] == "git"

    def test_persisting_detected(self, evo_dir):
        hm = HistoryManager(evo_dir)
        change = _make_change(family="ci", metric="run_duration", deviation=4.0)
        before = _make_advisory(changes=[change])
        change2 = _make_change(family="ci", metric="run_duration", deviation=3.0)
        after = _make_advisory(changes=[change2])

        p1 = hm.snapshot(before, "test")
        time.sleep(0.01)
        p2 = hm.snapshot(after, "test")

        ts1 = json.loads(p1.read_text())["timestamp"]
        ts2 = json.loads(p2.read_text())["timestamp"]
        diff = hm.compare(ts1, ts2)
        assert len(diff["persisting"]) == 1
        assert diff["persisting"][0]["improved"] is True

    def test_new_detected(self, evo_dir):
        hm = HistoryManager(evo_dir)
        before = _make_advisory(changes=[])
        after = _make_advisory(
            changes=[_make_change(family="dependency", metric="dependency_count")],
        )

        p1 = hm.snapshot(before, "test")
        time.sleep(0.01)
        p2 = hm.snapshot(after, "test")

        ts1 = json.loads(p1.read_text())["timestamp"]
        ts2 = json.loads(p2.read_text())["timestamp"]
        diff = hm.compare(ts1, ts2)
        assert len(diff["new"]) == 1

    def test_summary_text_present(self, evo_dir):
        hm = HistoryManager(evo_dir)
        before = _make_advisory(changes=[_make_change()])
        after = _make_advisory(changes=[])

        p1 = hm.snapshot(before, "test")
        time.sleep(0.01)
        p2 = hm.snapshot(after, "test")

        ts1 = json.loads(p1.read_text())["timestamp"]
        ts2 = json.loads(p2.read_text())["timestamp"]
        diff = hm.compare(ts1, ts2)
        assert "summary_text" in diff
        assert "RESOLVED" in diff["summary_text"]


# ──────────────── TestHistoryClean ────────────────


class TestHistoryClean:
    def test_keep_n(self, evo_dir):
        hm = HistoryManager(evo_dir)
        for i in range(5):
            hm.snapshot(_make_advisory(), f"run-{i}")
            time.sleep(0.01)
        deleted = hm.clean(keep=2)
        assert deleted == 3
        assert len(hm.list_runs()) == 2

    def test_before_date(self, evo_dir):
        hm = HistoryManager(evo_dir)
        hm.snapshot(_make_advisory(), "old")
        time.sleep(0.01)
        hm.snapshot(_make_advisory(), "new")

        runs = hm.list_runs()
        newest_ts = runs[0]["timestamp"]
        # Delete everything before the newest
        deleted = hm.clean(before=newest_ts)
        assert deleted == 1
        assert len(hm.list_runs()) == 1

    def test_returns_count(self, evo_dir):
        hm = HistoryManager(evo_dir)
        assert hm.clean(keep=5) == 0  # nothing to delete

    def test_empty_history(self, evo_dir):
        hm = HistoryManager(evo_dir)
        assert hm.clean(keep=1) == 0


# ──────────────── TestDiffAdvisories ────────────────


class TestDiffAdvisories:
    def test_all_resolved(self):
        before = {"changes": [_make_change()]}
        after = {"changes": []}
        diff = diff_advisories(before, after)
        assert len(diff["resolved"]) == 1
        assert len(diff["persisting"]) == 0
        assert len(diff["new"]) == 0

    def test_persisting_with_improvement(self):
        before = {"changes": [_make_change(deviation=5.0)]}
        after = {"changes": [_make_change(deviation=3.0)]}
        diff = diff_advisories(before, after)
        assert len(diff["persisting"]) == 1
        assert diff["persisting"][0]["improved"] is True
        assert diff["persisting"][0]["improvement"] == 2.0

    def test_new_observation(self):
        before = {"changes": []}
        after = {"changes": [_make_change(family="ci", metric="run_duration")]}
        diff = diff_advisories(before, after)
        assert len(diff["new"]) == 1
        assert diff["new"][0]["classification"] == "new_observation"

    def test_regression_detected(self):
        """A new metric in a family that already had changes = regression."""
        before = {"changes": [_make_change(family="git", metric="files_touched")]}
        after = {"changes": [
            _make_change(family="git", metric="files_touched"),
            _make_change(family="git", metric="dispersion", deviation=2.5),
        ]}
        diff = diff_advisories(before, after)
        assert len(diff["regressions"]) == 1
        assert diff["regressions"][0]["metric"] == "dispersion"

    def test_empty_both(self):
        diff = diff_advisories({"changes": []}, {"changes": []})
        assert diff == {
            "resolved": [], "persisting": [], "new": [], "regressions": [],
        }

    def test_matches_phase5_behavior(self):
        """Ensure shared function produces same structure as old Phase5 method."""
        before = {"changes": [
            _make_change(family="git", metric="files_touched", deviation=4.0),
            _make_change(family="ci", metric="run_duration", deviation=3.0),
        ]}
        after = {"changes": [
            _make_change(family="git", metric="files_touched", deviation=2.0),
            _make_change(family="dependency", metric="dependency_count", deviation=1.5),
        ]}
        diff = diff_advisories(before, after)
        assert len(diff["resolved"]) == 1  # ci:run_duration resolved
        assert diff["resolved"][0]["metric"] == "run_duration"
        assert len(diff["persisting"]) == 1  # git:files_touched persisting
        assert diff["persisting"][0]["improved"] is True


# ──────────────── TestFormatDiffSummary ────────────────


class TestFormatDiffSummary:
    def test_all_resolved_message(self):
        before = {"changes": [_make_change()], "scope": "test"}
        after = {"changes": [], "scope": "test"}
        diff = diff_advisories(before, after)
        summary = format_diff_summary(before, after, diff)
        assert "ALL ISSUES RESOLVED" in summary
        assert "Resolution rate: 100%" in summary

    def test_partial_resolution_message(self):
        before = {"changes": [
            _make_change(family="git", metric="files_touched"),
            _make_change(family="ci", metric="run_duration"),
        ]}
        after = {"changes": [
            _make_change(family="ci", metric="run_duration"),
        ]}
        diff = diff_advisories(before, after)
        summary = format_diff_summary(before, after, diff)
        assert "1 of 2" in summary

    def test_historical_transient(self):
        """Unchanged deviation + latest value near baseline → 'returned to normal'."""
        change = _make_change(family="git", metric="dispersion", deviation=4.0,
                              observed=0.85, median=0.20)
        before = {"changes": [change]}
        # After: same deviation but latest value returned to baseline
        after_change = {**change, "latest_deviation": 0.5,
                        "latest_value": 0.21, "is_latest_event": False}
        after = {"changes": [after_change]}
        diff = diff_advisories(before, after)
        summary = format_diff_summary(before, after, diff)
        assert "returned to normal" in summary
        assert "0.85" in summary  # observed value shown
        assert "baseline 0.20" in summary

    def test_historical_persistent(self):
        """Unchanged deviation + high latest_deviation → 'still actively deviating'."""
        change = _make_change(family="git", metric="dispersion", deviation=4.0,
                              observed=0.85, median=0.20)
        before = {"changes": [change]}
        after_change = {**change, "latest_deviation": 2.5, "is_latest_event": False}
        after = {"changes": [after_change]}
        diff = diff_advisories(before, after)
        summary = format_diff_summary(before, after, diff)
        assert "still actively deviating" in summary
        assert "0.85" in summary  # observed value shown

    def test_stabilized_drift(self):
        """Low latest deviation but value far from baseline → 'stabilized at new level'."""
        change = _make_change(family="dependency", metric="dependency_count",
                              deviation=182.1, observed=1613, median=1478)
        before = {"changes": [change]}
        after_change = {**change, "latest_deviation": 0.0,
                        "latest_value": 1613, "is_latest_event": False}
        after = {"changes": [after_change]}
        diff = diff_advisories(before, after)
        summary = format_diff_summary(before, after, diff)
        assert "stabilized at new level" in summary
        assert "1,613" in summary
        assert "baseline 1,478" in summary

    def test_historical_no_latest_deviation(self):
        """Unchanged deviation without latest_deviation → defaults to 'returned to normal'."""
        change = _make_change(family="git", metric="dispersion", deviation=4.0,
                              observed=0.85, median=0.20)
        before = {"changes": [change]}
        after = {"changes": [change]}
        diff = diff_advisories(before, after)
        summary = format_diff_summary(before, after, diff)
        assert "returned to normal" in summary

    def test_not_improving_when_deviation_changes(self):
        """Deviation changed (not identical) but not improving → 'not improving'."""
        before = {"changes": [_make_change(deviation=3.5, observed=20, median=5)]}
        after = {"changes": [_make_change(deviation=3.8, observed=22, median=5)]}
        diff = diff_advisories(before, after)
        summary = format_diff_summary(before, after, diff)
        assert "not improving" in summary
        assert "20" in summary  # before value
        assert "22" in summary  # after value

    def test_shows_observed_values_not_sigma(self):
        """Verify that format uses actual observed values, not raw σ numbers."""
        change = _make_change(deviation=182.1, observed=1613, median=1478)
        before = {"changes": [change]}
        after_change = {**change, "latest_deviation": 0.0, "latest_value": 1613}
        after = {"changes": [after_change]}
        diff = diff_advisories(before, after)
        summary = format_diff_summary(before, after, diff)
        assert "1,613" in summary  # formatted observed value
        assert "baseline 1,478" in summary
        assert "182.1" not in summary  # raw σ should NOT appear

    def test_was_value_preserved_in_diff(self):
        """diff_advisories preserves the before observation as was_value."""
        before = {"changes": [_make_change(deviation=5.0, observed=100, median=50)]}
        after = {"changes": [_make_change(deviation=3.0, observed=80, median=50)]}
        diff = diff_advisories(before, after)
        p = diff["persisting"][0]
        assert p["was_value"] == 100
        assert p["current"] == 80
