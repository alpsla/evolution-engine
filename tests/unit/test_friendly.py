"""Unit tests for PM-friendly formatting helpers."""

import pytest

from evolution.friendly import risk_level, relative_change, metric_insight, friendly_pattern


class TestRiskLevel:
    def test_critical(self):
        result = risk_level(7.0)
        assert result["label"] == "Critical"
        assert result["color"] == "#991b1b"

    def test_high(self):
        result = risk_level(5.0)
        assert result["label"] == "High"

    def test_medium(self):
        result = risk_level(3.0)
        assert result["label"] == "Medium"
        assert result["color"] == "#f59e0b"

    def test_low(self):
        result = risk_level(1.5)
        assert result["label"] == "Low"

    def test_normal(self):
        result = risk_level(0.5)
        assert result["label"] == "Normal"

    def test_negative_deviation(self):
        result = risk_level(-4.5)
        assert result["label"] == "High"

    def test_zero(self):
        result = risk_level(0)
        assert result["label"] == "Normal"

    def test_boundary_values(self):
        assert risk_level(6.0)["label"] == "Critical"
        assert risk_level(4.0)["label"] == "High"
        assert risk_level(2.0)["label"] == "Medium"
        assert risk_level(1.0)["label"] == "Low"


class TestRelativeChange:
    def test_much_higher(self):
        result = relative_change(12, 4)
        assert "3x more" in result
        assert "typically around 4" in result

    def test_much_lower(self):
        result = relative_change(2, 10)
        assert "5x less" in result
        assert "typically around 10" in result

    def test_slightly_more(self):
        result = relative_change(5, 4)
        assert "slightly more" in result

    def test_slightly_less(self):
        result = relative_change(4, 5)
        assert "slightly less" in result

    def test_about_the_same(self):
        result = relative_change(10, 10)
        assert "same as usual" in result

    def test_zero_baseline(self):
        result = relative_change(5, 0)
        assert "no established baseline" in result

    def test_both_zero(self):
        result = relative_change(0, 0)
        assert "at the usual level" in result

    def test_none_baseline(self):
        result = relative_change(5, None)
        assert "no established baseline" in result

    def test_float_formatting(self):
        result = relative_change(0.85, 0.22)
        assert "typically around 0.22" in result


class TestMetricInsight:
    def test_files_touched_up(self):
        result = metric_insight("files_touched", "up")
        assert "review" in result.lower()

    def test_dispersion_up(self):
        result = metric_insight("dispersion", "up")
        assert "spread" in result.lower() or "unrelated" in result.lower()

    def test_run_failed_up(self):
        result = metric_insight("run_failed", "up")
        assert "failure" in result.lower() or "attention" in result.lower()

    def test_dependency_count_up(self):
        result = metric_insight("dependency_count", "up")
        assert "supply-chain" in result.lower() or "dependencies" in result.lower()

    def test_release_cadence_down(self):
        result = metric_insight("release_cadence_hours", "down")
        assert "review" in result.lower() or "faster" in result.lower()

    def test_unknown_metric(self):
        assert metric_insight("nonexistent_metric", "up") == ""

    def test_all_metrics_have_both_directions(self):
        known_metrics = [
            "files_touched", "dispersion", "change_locality", "cochange_novelty_ratio",
            "run_duration", "run_failed",
            "dependency_count", "max_depth",
            "release_cadence_hours", "is_prerelease", "asset_count",
        ]
        for m in known_metrics:
            assert metric_insight(m, "up") != "", f"Missing insight for {m} up"
            assert metric_insight(m, "down") != "", f"Missing insight for {m} down"


class TestFriendlyPattern:
    def test_with_description_and_count(self):
        result = friendly_pattern({
            "description": "dependency-changing commits tend to touch more spread-out files.",
            "support_count": 5,
        })
        assert "Observed across 5 projects" in result
        assert "dependency-changing commits" in result

    def test_with_description_no_count(self):
        result = friendly_pattern({
            "description": "some pattern description",
            "support_count": 0,
        })
        assert result == "some pattern description"

    def test_fallback_from_families_and_metrics(self):
        result = friendly_pattern({
            "families": ["git", "dependency"],
            "metrics": ["dispersion"],
            "support_count": 3,
            "correlation": 0.5,
        })
        assert "Observed across 3 projects" in result
        assert "code changes" in result
        assert "dependency" in result

    def test_empty_pattern(self):
        result = friendly_pattern({})
        assert result == ""

    def test_single_project(self):
        result = friendly_pattern({
            "description": "test pattern",
            "support_count": 1,
        })
        assert "Observed in 1 project:" in result
        assert "projects" not in result

    def test_repo_count_key(self):
        result = friendly_pattern({
            "description": "test",
            "repo_count": 7,
        })
        assert "Observed across 7 projects" in result

    def test_repo_count_preferred_over_occurrence_count(self):
        result = friendly_pattern({
            "description": "test",
            "repo_count": 7,
            "occurrence_count": 27631,
        })
        assert "Observed across 7 projects" in result

    def test_sanitizes_statistical_details(self):
        """Ensure internal methodology isn't leaked in descriptions."""
        result = friendly_pattern({
            "families": ["deployment"],
            "metrics": ["dispersion"],
            "correlation": 0.75,
            "support_count": 9,
            "description": "When deployment events occur, git.dispersion is systematically increased (effect size d=0.75, treated=9, control=3342).",
        })
        assert "effect size" not in result
        assert "treated=" not in result
        assert "control=" not in result
        assert "Observed across 9 projects" in result

    def test_sanitizes_temporal_details(self):
        """Ensure temporal alignment internals aren't leaked."""
        result = friendly_pattern({
            "description": "Signals ci.run_duration and dependency.dependency_count co-occur with correlation -0.41 across 19 commit-aligned observations (of 98 shared commits).",
            "support_count": 3,
        })
        assert "correlation" not in result
        assert "commit-aligned" not in result
        assert "24h windows" not in result
