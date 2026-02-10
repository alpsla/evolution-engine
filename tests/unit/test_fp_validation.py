"""Unit tests for FP validation module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from evolution.fp_validation import (
    ChangeClassification,
    FPReport,
    validate_fp_rate,
    baseline_norms,
    _classify_change,
    _get_pattern_repos,
)


# ─── ChangeClassification ───


class TestChangeClassification:
    def test_fields(self):
        c = ChangeClassification(
            repo="test", family="git", metric="files_touched",
            deviation=3.5, current=10, median=3.0,
            label="TP", reason="genuine deviation",
        )
        assert c.repo == "test"
        assert c.label == "TP"
        assert c.pattern_matched is False

    def test_pattern_matched_default(self):
        c = ChangeClassification(
            repo="r", family="git", metric="m",
            deviation=1.0, current=1, median=1.0,
            label="TP", reason="test", pattern_matched=True,
        )
        assert c.pattern_matched is True


# ─── FPReport ───


class TestFPReport:
    def _make_report(self, labels):
        report = FPReport(repos_analyzed=1, total_changes=len(labels))
        for label in labels:
            report.classifications.append(
                ChangeClassification(
                    repo="test", family="git", metric="files_touched",
                    deviation=3.0, current=10, median=3.0,
                    label=label, reason="test",
                )
            )
        return report

    def test_counts(self):
        report = self._make_report(["TP", "TP", "EP", "FP"])
        assert report.tp_count == 2
        assert report.ep_count == 1
        assert report.fp_count == 1

    def test_fp_rate(self):
        report = self._make_report(["TP", "TP", "FP", "FP"])
        assert report.fp_rate == pytest.approx(0.5)

    def test_fp_rate_empty(self):
        report = FPReport()
        assert report.fp_rate == 0.0

    def test_actionable_rate(self):
        report = self._make_report(["TP", "EP", "FP"])
        assert report.actionable_rate == pytest.approx(1 / 3)

    def test_actionable_rate_empty(self):
        report = FPReport()
        assert report.actionable_rate == 0.0

    def test_summary_contains_key_info(self):
        report = self._make_report(["TP", "FP"])
        text = report.summary()
        assert "FP Validation Report" in text
        assert "True Positives:" in text
        assert "False Positives:" in text
        assert "Per-metric breakdown:" in text

    def test_summary_fp_details(self):
        report = self._make_report(["FP"])
        text = report.summary()
        assert "FP Details:" in text

    def test_summary_no_fp_details_when_clean(self):
        report = self._make_report(["TP"])
        text = report.summary()
        assert "FP Details:" not in text

    def test_pct_zero_changes(self):
        report = FPReport()
        assert report._pct(0) == "0%"

    def test_to_dict(self):
        report = self._make_report(["TP", "FP"])
        d = report.to_dict()
        assert d["repos_analyzed"] == 1
        assert d["total_changes"] == 2
        assert d["tp_count"] == 1
        assert d["fp_count"] == 1
        assert d["fp_rate"] == 0.5
        assert len(d["classifications"]) == 2
        assert d["classifications"][0]["label"] == "TP"


# ─── _classify_change ───


class TestClassifyChange:
    def _make_change(self, family="git", metric="files_touched",
                     deviation=3.0, current=10, median=3.0):
        return {
            "family": family,
            "metric": metric,
            "deviation_stddev": deviation,
            "current": current,
            "normal": {"median": median},
        }

    def test_deprecated_metric_fp(self):
        c = _classify_change("repo", self._make_change(metric="direct_count"), False)
        assert c.label == "FP"
        assert "deprecated" in c.reason

    def test_ci_runner_noise_fp(self):
        change = self._make_change(family="ci", metric="run_duration", deviation=200000)
        c = _classify_change("repo", change, False)
        assert c.label == "FP"
        assert "runner variability" in c.reason

    def test_cold_start_fp(self):
        change = self._make_change(median=None)
        c = _classify_change("repo", change, False)
        assert c.label == "FP"
        assert "cold-start" in c.reason

    def test_large_merge_ep(self):
        change = self._make_change(metric="files_touched", current=600, deviation=1500)
        c = _classify_change("repo", change, False)
        assert c.label == "EP"
        assert "merge" in c.reason.lower() or "release" in c.reason.lower()

    def test_locality_ceiling_ep(self):
        change = self._make_change(metric="change_locality", current=600, deviation=200)
        c = _classify_change("repo", change, False)
        assert c.label == "EP"
        assert "locality" in c.reason

    def test_novelty_floor_ep(self):
        change = self._make_change(
            metric="cochange_novelty_ratio", current=0, deviation=150,
        )
        c = _classify_change("repo", change, False)
        assert c.label == "EP"
        assert "novel" in c.reason

    def test_release_cadence_ep(self):
        change = self._make_change(
            family="deployment", metric="release_cadence_hours", deviation=20,
        )
        c = _classify_change("repo", change, False)
        assert c.label == "EP"
        assert "cadence" in c.reason

    def test_genuine_deviation_tp(self):
        change = self._make_change(deviation=3.0)
        c = _classify_change("repo", change, False)
        assert c.label == "TP"
        assert "medium" in c.reason

    def test_high_deviation_tp(self):
        change = self._make_change(deviation=5.0)
        c = _classify_change("repo", change, False)
        assert c.label == "TP"
        assert "high" in c.reason

    def test_critical_deviation_tp(self):
        change = self._make_change(deviation=8.0)
        c = _classify_change("repo", change, False)
        assert c.label == "TP"
        assert "critical" in c.reason

    def test_pattern_matched_tp(self):
        change = self._make_change(deviation=2.5)
        c = _classify_change("repo", change, True)
        assert c.label == "TP"
        assert "pattern-matched" in c.reason

    def test_small_deviation_tp(self):
        change = self._make_change(deviation=1.5)
        c = _classify_change("repo", change, False)
        assert c.label == "TP"
        assert c.reason == "genuine deviation"

    def test_negative_deviation_uses_abs(self):
        change = self._make_change(family="ci", metric="run_duration", deviation=-200000)
        c = _classify_change("repo", change, False)
        assert c.label == "FP"  # abs(deviation) > 100K


# ─── _get_pattern_repos ───


class TestGetPatternRepos:
    def test_nonexistent_file(self, tmp_path):
        assert _get_pattern_repos(tmp_path / "missing.json") == set()

    def test_extracts_repos(self, tmp_path):
        data = {
            "patterns": [
                {"repos_observed": ["repo-a", "repo-b"]},
                {"repos_observed": ["repo-b", "repo-c"]},
            ]
        }
        path = tmp_path / "patterns.json"
        path.write_text(json.dumps(data))
        repos = _get_pattern_repos(path)
        assert repos == {"repo-a", "repo-b", "repo-c"}


# ─── validate_fp_rate ───


class TestValidateFPRate:
    def _setup_cal_dir(self, tmp_path, repos):
        """Create a mock calibration directory with advisory files."""
        cal_dir = tmp_path / "runs"
        for name, advisory in repos.items():
            d = cal_dir / name / "phase5"
            d.mkdir(parents=True)
            (d / "advisory.json").write_text(json.dumps(advisory))
        return cal_dir

    def test_basic_validation(self, tmp_path):
        # Create a universal patterns file that excludes "training-repo"
        patterns_path = tmp_path / "patterns.json"
        patterns_path.write_text(json.dumps({
            "patterns": [{"repos_observed": ["training-repo"]}]
        }))

        advisory = {
            "changes": [
                {
                    "family": "git", "metric": "files_touched",
                    "deviation_stddev": 4.0, "current": 15,
                    "normal": {"median": 3.0},
                },
            ],
        }
        cal_dir = self._setup_cal_dir(tmp_path, {
            "training-repo": advisory,  # should be excluded
            "unseen-repo": advisory,    # should be included
        })

        report = validate_fp_rate(cal_dir, patterns_path)
        assert report.repos_analyzed == 1
        assert report.total_changes == 1
        assert report.tp_count == 1

    def test_empty_calibration(self, tmp_path):
        cal_dir = tmp_path / "runs"
        cal_dir.mkdir()
        patterns_path = tmp_path / "patterns.json"
        patterns_path.write_text(json.dumps({"patterns": []}))

        report = validate_fp_rate(cal_dir, patterns_path)
        assert report.repos_analyzed == 0
        assert report.total_changes == 0
        assert report.fp_rate == 0.0

    def test_max_repos(self, tmp_path):
        patterns_path = tmp_path / "patterns.json"
        patterns_path.write_text(json.dumps({"patterns": []}))

        advisory = {
            "changes": [
                {"family": "git", "metric": "m", "deviation_stddev": 3.0,
                 "current": 5, "normal": {"median": 2.0}},
            ]
        }
        cal_dir = self._setup_cal_dir(tmp_path, {
            f"repo-{i}": advisory for i in range(5)
        })

        report = validate_fp_rate(cal_dir, patterns_path, max_repos=2)
        assert report.repos_analyzed == 2

    def test_invalid_json_skipped(self, tmp_path):
        patterns_path = tmp_path / "patterns.json"
        patterns_path.write_text(json.dumps({"patterns": []}))

        cal_dir = tmp_path / "runs"
        d = cal_dir / "bad-repo" / "phase5"
        d.mkdir(parents=True)
        (d / "advisory.json").write_text("NOT JSON")

        report = validate_fp_rate(cal_dir, patterns_path)
        assert report.repos_analyzed == 0


# ─── baseline_norms ───


class TestBaselineNorms:
    def test_computes_norms(self, tmp_path):
        cal_dir = tmp_path / "runs"
        for name, median in [("a", 2.0), ("b", 4.0), ("c", 6.0)]:
            d = cal_dir / name / "phase5"
            d.mkdir(parents=True)
            advisory = {
                "changes": [
                    {"family": "git", "metric": "files_touched",
                     "deviation_stddev": 3.0, "current": 10,
                     "normal": {"median": median}},
                ]
            }
            (d / "advisory.json").write_text(json.dumps(advisory))

        norms = baseline_norms(cal_dir)
        assert "git" in norms
        assert "files_touched" in norms["git"]
        # median of [2, 4, 6] = 4
        assert norms["git"]["files_touched"]["median_of_medians"] == 4.0
        assert norms["git"]["files_touched"]["repos_with_data"] == 3

    def test_skips_none_medians(self, tmp_path):
        cal_dir = tmp_path / "runs"
        d = cal_dir / "repo" / "phase5"
        d.mkdir(parents=True)
        advisory = {
            "changes": [
                {"family": "git", "metric": "m", "deviation_stddev": 1.0,
                 "current": 1, "normal": {"median": None}},
            ]
        }
        (d / "advisory.json").write_text(json.dumps(advisory))

        norms = baseline_norms(cal_dir)
        # No valid medians, so empty
        assert norms == {}

    def test_empty_dir(self, tmp_path):
        cal_dir = tmp_path / "runs"
        cal_dir.mkdir()
        norms = baseline_norms(cal_dir)
        assert norms == {}
