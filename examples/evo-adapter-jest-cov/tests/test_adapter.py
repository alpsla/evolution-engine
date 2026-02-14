"""Tests for JestCovAdapter."""

import json
from pathlib import Path

from evo_jest_cov import JestCovAdapter, register


SAMPLE_COVERAGE = {
    "total": {
        "lines": {"total": 1000, "covered": 850, "skipped": 0, "pct": 85},
        "statements": {"total": 1200, "covered": 1020, "skipped": 0, "pct": 85},
        "functions": {"total": 200, "covered": 180, "skipped": 0, "pct": 90},
        "branches": {"total": 300, "covered": 240, "skipped": 0, "pct": 80},
    },
    "/src/index.ts": {
        "lines": {"total": 50, "covered": 45, "skipped": 0, "pct": 90},
        "statements": {"total": 60, "covered": 54, "skipped": 0, "pct": 90},
        "functions": {"total": 10, "covered": 9, "skipped": 0, "pct": 90},
        "branches": {"total": 15, "covered": 12, "skipped": 0, "pct": 80},
    },
}


def test_register_returns_descriptors():
    """register() must return a list of dicts with required fields."""
    descriptors = register()
    assert isinstance(descriptors, list)
    assert len(descriptors) >= 1
    for d in descriptors:
        assert "adapter_name" in d
        assert "family" in d
        assert d["family"] == "testing"


def test_adapter_has_required_attributes():
    assert JestCovAdapter.source_family == "testing"
    assert JestCovAdapter.source_type == "jest_cov"
    assert JestCovAdapter.ordering_mode in ("causal", "temporal")
    assert JestCovAdapter.attestation_tier in ("strong", "medium", "weak")


def test_adapter_yields_events(tmp_path):
    """Adapter should yield valid events from coverage-summary.json."""
    cov_dir = tmp_path / "coverage"
    cov_dir.mkdir()
    (cov_dir / "coverage-summary.json").write_text(json.dumps(SAMPLE_COVERAGE))
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("abc123def456\n")

    adapter = JestCovAdapter(path=str(tmp_path))
    events = list(adapter.iter_events())
    assert len(events) == 1

    event = events[0]
    assert event["source_family"] == "testing"
    assert event["source_type"] == "jest_cov"
    assert isinstance(event["attestation"], dict)
    assert "report_hash" in event["attestation"]

    p = event["payload"]
    assert p["line_rate"] == 0.85
    assert p["branch_rate"] == 0.80
    assert p["function_rate"] == 0.90
    assert p["lines_covered"] == 850
    assert p["lines_missing"] == 150
    assert p["packages_covered"] == 1  # 1 file entry besides "total"
    assert p["trigger"]["commit_sha"] == "abc123def456"


def test_no_coverage_file(tmp_path):
    """Adapter returns 0 events when coverage file doesn't exist."""
    adapter = JestCovAdapter(path=str(tmp_path))
    events = list(adapter.iter_events())
    assert len(events) == 0


def test_certification(tmp_path):
    """Run the full evo adapter validation suite."""
    from evolution.adapter_validator import validate_adapter

    cov_dir = tmp_path / "coverage"
    cov_dir.mkdir()
    (cov_dir / "coverage-summary.json").write_text(json.dumps(SAMPLE_COVERAGE))

    report = validate_adapter(
        JestCovAdapter,
        constructor_args={"path": str(tmp_path)},
    )
    assert report.passed, report.summary()
