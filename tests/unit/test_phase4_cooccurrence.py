"""Unit tests for Phase 4 co-occurrence detection, fingerprinting, and alignment."""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev

import pytest

from evolution.phase4_engine import (
    classify_direction,
    compute_fingerprint,
    signals_to_components,
    Phase4Engine,
)


class TestClassifyDirection:
    def test_increased(self):
        assert classify_direction(2.0, threshold=1.0) == "increased"

    def test_decreased(self):
        assert classify_direction(-2.0, threshold=1.0) == "decreased"

    def test_unchanged_within_threshold(self):
        assert classify_direction(0.5, threshold=1.0) == "unchanged"
        assert classify_direction(-0.5, threshold=1.0) == "unchanged"

    def test_unchanged_at_boundary(self):
        assert classify_direction(1.0, threshold=1.0) == "unchanged"
        assert classify_direction(-1.0, threshold=1.0) == "unchanged"

    def test_degenerate_always_unchanged(self):
        assert classify_direction(999.0, threshold=1.0, unit="degenerate") == "unchanged"


class TestComputeFingerprint:
    def test_deterministic(self):
        components = [("git", "files_touched", "increased"), ("ci", "run_duration", "increased")]
        fp1 = compute_fingerprint(components)
        fp2 = compute_fingerprint(components)
        assert fp1 == fp2

    def test_order_independent(self):
        c1 = [("git", "files_touched", "increased"), ("ci", "run_duration", "increased")]
        c2 = [("ci", "run_duration", "increased"), ("git", "files_touched", "increased")]
        assert compute_fingerprint(c1) == compute_fingerprint(c2)

    def test_different_components_different_hash(self):
        c1 = [("git", "files_touched", "increased")]
        c2 = [("git", "files_touched", "decreased")]
        assert compute_fingerprint(c1) != compute_fingerprint(c2)

    def test_returns_16_char_hex(self):
        fp = compute_fingerprint([("git", "files_touched", "increased")])
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)


class TestSignalsToComponents:
    def test_filters_degenerate(self):
        signals = [
            {"engine_id": "git", "metric": "files_touched",
             "deviation": {"measure": 5.0, "unit": "modified_zscore", "degenerate": False}},
            {"engine_id": "ci", "metric": "run_failed",
             "deviation": {"measure": 0.0, "unit": "degenerate", "degenerate": True}},
        ]
        components = signals_to_components(signals, threshold=1.0)
        assert len(components) == 1
        assert components[0][0] == "git"

    def test_filters_unchanged(self):
        signals = [
            {"engine_id": "git", "metric": "files_touched",
             "deviation": {"measure": 0.3, "unit": "modified_zscore", "degenerate": False}},
        ]
        components = signals_to_components(signals, threshold=1.0)
        assert len(components) == 0

    def test_filters_none_measure(self):
        signals = [
            {"engine_id": "git", "metric": "files_touched",
             "deviation": {"measure": None, "unit": "degenerate", "degenerate": True}},
        ]
        components = signals_to_components(signals, threshold=1.0)
        assert len(components) == 0


class TestPearson:
    def test_perfect_positive_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [2, 4, 6, 8, 10]
        r = Phase4Engine._pearson(xs, ys)
        assert abs(r - 1.0) < 1e-10

    def test_perfect_negative_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [10, 8, 6, 4, 2]
        r = Phase4Engine._pearson(xs, ys)
        assert abs(r - (-1.0)) < 1e-10

    def test_no_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [5, 1, 4, 2, 3]
        r = Phase4Engine._pearson(xs, ys)
        assert abs(r) < 0.5  # low correlation

    def test_constant_series_returns_zero(self):
        xs = [1, 1, 1, 1, 1]
        ys = [1, 2, 3, 4, 5]
        assert Phase4Engine._pearson(xs, ys) == 0.0

    def test_single_element_returns_zero(self):
        assert Phase4Engine._pearson([1], [2]) == 0.0


class TestTimeBucket:
    def test_same_day_same_bucket(self):
        t1 = "2026-01-01T10:00:00Z"
        t2 = "2026-01-01T20:00:00Z"
        b1 = Phase4Engine._time_bucket(t1, 24)
        b2 = Phase4Engine._time_bucket(t2, 24)
        assert b1 == b2

    def test_different_days_different_buckets(self):
        t1 = "2026-01-01T10:00:00Z"
        t2 = "2026-01-03T10:00:00Z"
        b1 = Phase4Engine._time_bucket(t1, 24)
        b2 = Phase4Engine._time_bucket(t2, 24)
        assert b1 != b2

    def test_invalid_timestamp_returns_none(self):
        assert Phase4Engine._time_bucket("not-a-date", 24) is None
        assert Phase4Engine._time_bucket("", 24) is None
        assert Phase4Engine._time_bucket(None, 24) is None


class TestCoOccurrenceDiscovery:
    """Integration-level test: synthetic correlated signals → pattern discovery."""

    def _write_events_and_signals(self, evo_dir: Path, n: int = 30):
        """Create synthetic events with known correlation between git and CI."""
        events_dir = evo_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        phase2_dir = evo_dir / "phase2"
        phase2_dir.mkdir(parents=True, exist_ok=True)

        base_time = datetime(2026, 1, 1, 10, 0, 0)
        git_signals = []
        ci_signals = []

        for i in range(n):
            sha = f"{i:040x}"
            t = base_time + timedelta(hours=i * 2)

            # Git event
            git_ev = {
                "event_id": f"git-{i:04d}",
                "source_type": "git",
                "source_family": "version_control",
                "observed_at": t.isoformat() + "Z",
                "payload": {
                    "commit_hash": sha,
                    "committed_at": t.isoformat() + "Z",
                    "files": [f"f{j}.py" for j in range(i + 1)],  # growing
                },
            }
            (events_dir / f"git-{i:04d}.json").write_text(json.dumps(git_ev))

            # CI event — duration correlated with files_touched
            ci_ev = {
                "event_id": f"ci-{i:04d}",
                "source_type": "github_actions",
                "source_family": "ci",
                "observed_at": t.isoformat() + "Z",
                "payload": {
                    "trigger": {"commit_sha": sha},
                    "timing": {
                        "created_at": t.isoformat() + "Z",
                        "duration_seconds": 60 + i * 10,  # correlated with i
                    },
                    "conclusion": "success",
                },
            }
            (events_dir / f"ci-{i:04d}.json").write_text(json.dumps(ci_ev))

            # Build Phase 2 signals with known deviation that rises with i
            deviation_git = (i - n / 2) * 0.5  # ranges from -7.5 to +7
            deviation_ci = (i - n / 2) * 0.4   # correlated

            git_signals.append({
                "engine_id": "git",
                "source_type": "git",
                "metric": "files_touched",
                "window": {"type": "rolling", "size": 50},
                "baseline": {"mean": 5, "stddev": 2, "median": 5, "mad": 1.5},
                "observed": i + 1,
                "deviation": {
                    "measure": round(deviation_git, 4),
                    "unit": "modified_zscore",
                    "degenerate": False,
                },
                "confidence": {"sample_count": 30, "status": "sufficient"},
                "event_ref": f"git-{i:04d}",
            })

            ci_signals.append({
                "engine_id": "ci",
                "source_type": "github_actions",
                "metric": "run_duration",
                "window": {"type": "rolling", "size": 50},
                "baseline": {"mean": 200, "stddev": 50, "median": 200, "mad": 30},
                "observed": 60 + i * 10,
                "deviation": {
                    "measure": round(deviation_ci, 4),
                    "unit": "modified_zscore",
                    "degenerate": False,
                },
                "confidence": {"sample_count": 30, "status": "sufficient"},
                "event_ref": f"ci-{i:04d}",
            })

        (phase2_dir / "git_signals.json").write_text(json.dumps(git_signals))
        (phase2_dir / "ci_signals.json").write_text(json.dumps(ci_signals))

    def test_discovers_correlated_pattern(self, evo_dir):
        """Synthetic correlated git+CI data should produce at least one pattern."""
        self._write_events_and_signals(evo_dir, n=30)

        phase4 = Phase4Engine(evo_dir, params={
            "min_support": 3,
            "min_correlation": 0.3,
            "promotion_threshold": 50,
            "direction_threshold": 1.0,
            "temporal_window_hours": 24,
        })

        result = phase4.run()
        phase4.close()

        assert result["status"] == "complete"
        assert result["patterns_discovered"] >= 1

        found_cross_family = any(
            d.get("sources") and len(d["sources"]) > 1
            for d in result["details"]
        )
        assert found_cross_family, "Should discover cross-family pattern between git and ci"

    def test_discovers_presence_pattern(self, evo_dir):
        """Presence-based discovery: when one family's events occur,
        git metrics show systematically different values."""
        events_dir = evo_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        phase2_dir = evo_dir / "phase2"
        phase2_dir.mkdir(parents=True, exist_ok=True)

        base_time = datetime(2026, 1, 1, 10, 0, 0)
        git_signals = []
        dep_signals = []

        # Create 100 commits: 40 with dep events (high dispersion),
        # 60 without dep events (low dispersion)
        for i in range(100):
            sha = f"{i:040x}"
            t = base_time + timedelta(hours=i * 2)
            has_dep = i % 5 < 2  # 40% have dep events

            git_ev = {
                "event_id": f"git-{i:04d}",
                "source_type": "git",
                "source_family": "version_control",
                "observed_at": t.isoformat() + "Z",
                "payload": {
                    "commit_hash": sha,
                    "committed_at": t.isoformat() + "Z",
                },
            }
            (events_dir / f"git-{i:04d}.json").write_text(json.dumps(git_ev))

            # Git dispersion: higher when deps change
            if has_dep:
                deviation = 2.0 + (i % 3) * 0.5  # 2.0-3.0 (always deviating)
            else:
                deviation = 0.3 + (i % 5) * 0.1  # 0.3-0.7 (low, not deviating)

            git_signals.append({
                "engine_id": "git",
                "source_type": "git",
                "metric": "dispersion",
                "window": {"type": "rolling", "size": 50},
                "baseline": {"mean": 1.0, "stddev": 0.5, "median": 1.0, "mad": 0.4},
                "observed": 1.0 + deviation * 0.4,
                "deviation": {
                    "measure": round(deviation, 4),
                    "unit": "modified_zscore",
                    "degenerate": False,
                },
                "confidence": {"sample_count": 50, "status": "sufficient"},
                "event_ref": f"git-{i:04d}",
            })

            if has_dep:
                dep_ev = {
                    "event_id": f"dep-{i:04d}",
                    "source_type": "dependency",
                    "source_family": "dependency",
                    "observed_at": t.isoformat() + "Z",
                    "payload": {
                        "trigger": {"commit_sha": sha},
                    },
                }
                (events_dir / f"dep-{i:04d}.json").write_text(json.dumps(dep_ev))

                dep_signals.append({
                    "engine_id": "dependency",
                    "source_type": "dependency",
                    "metric": "dependency_count",
                    "window": {"type": "rolling", "size": 50},
                    "baseline": {"mean": 50, "stddev": 5, "median": 50, "mad": 3},
                    "observed": 50 + i % 10,
                    "deviation": {
                        "measure": round((i % 10 - 5) * 0.5, 4),
                        "unit": "modified_zscore",
                        "degenerate": False,
                    },
                    "confidence": {"sample_count": 30, "status": "sufficient"},
                    "event_ref": f"dep-{i:04d}",
                })

        (phase2_dir / "git_signals.json").write_text(json.dumps(git_signals))
        (phase2_dir / "dependency_signals.json").write_text(json.dumps(dep_signals))

        phase4 = Phase4Engine(evo_dir, params={
            "min_support": 3,
            "min_correlation": 0.3,
            "min_effect_size": 0.2,
            "promotion_threshold": 500,
            "direction_threshold": 1.0,
        })

        result = phase4.run()
        phase4.close()

        assert result["status"] == "complete"
        assert result["patterns_discovered"] >= 1

        # Should find a presence-based pattern for git.dispersion
        found_presence = False
        for d in result["details"]:
            desc = d.get("description_statistical", "")
            if "dependency" in desc and "dispersion" in desc:
                found_presence = True
        assert found_presence, (
            f"Should find presence-based dependency×git.dispersion pattern. "
            f"Details: {result['details']}"
        )

    def test_skips_intra_family(self, evo_dir):
        """Co-occurrence should NOT pair metrics from the same family."""
        self._write_events_and_signals(evo_dir, n=30)

        phase4 = Phase4Engine(evo_dir, params={
            "min_support": 3,
            "min_correlation": 0.3,
            "promotion_threshold": 50,
            "direction_threshold": 1.0,
        })

        result = phase4.run()
        phase4.close()

        for detail in result["details"]:
            if detail.get("sources"):
                # All discovered patterns should span different families
                assert len(set(detail["sources"])) > 1, \
                    f"Intra-family pattern discovered: {detail['sources']}"
