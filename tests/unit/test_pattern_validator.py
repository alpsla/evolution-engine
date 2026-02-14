"""
Unit tests for pattern validator (evolution/pattern_validator.py).
"""

import pytest

from evolution.pattern_validator import validate_pattern_package, ValidationReport


# ─── Sample data ───

VALID_PATTERN = {
    "fingerprint": "3aab010d317b22df",
    "pattern_type": "co_occurrence",
    "discovery_method": "statistical",
    "sources": ["ci", "git"],
    "metrics": ["ci_presence", "dispersion"],
    "description_statistical": "When ci events occur, git.dispersion increases.",
    "correlation_strength": 0.38,
    "occurrence_count": 100,
    "confidence_tier": "confirmed",
    "scope": "community",
}

VALID_PATTERN_2 = {
    "fingerprint": "f0980c46c1243135",
    "pattern_type": "co_occurrence",
    "discovery_method": "statistical",
    "sources": ["deployment", "git"],
    "metrics": ["deployment_presence", "dispersion"],
    "correlation_strength": 1.0,
    "scope": "community",
}


class TestValidatePatternPackage:
    def test_valid_package(self):
        report = validate_pattern_package([VALID_PATTERN], package_name="test-pkg")
        assert report.passed
        assert len(report.errors) == 0

    def test_multiple_valid_patterns(self):
        report = validate_pattern_package(
            [VALID_PATTERN, VALID_PATTERN_2], package_name="test-pkg"
        )
        assert report.passed

    def test_empty_package_fails(self):
        report = validate_pattern_package([], package_name="test-pkg")
        assert not report.passed
        assert any("no patterns" in c.message.lower() for c in report.errors)

    def test_invalid_pattern_fails_security(self):
        bad = {
            "fingerprint": "INVALID",  # uppercase not allowed
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["ci"],
            "metrics": ["dispersion"],
            "scope": "community",
        }
        report = validate_pattern_package([bad], package_name="test-pkg")
        assert not report.passed

    def test_missing_required_fields(self):
        incomplete = {
            "fingerprint": "3aab010d317b22df",
            "scope": "community",
            # missing: sources, metrics, pattern_type, discovery_method
        }
        report = validate_pattern_package([incomplete], package_name="test-pkg")
        assert not report.passed

    def test_local_scope_rejected(self):
        local = dict(VALID_PATTERN, scope="local")
        report = validate_pattern_package([local], package_name="test-pkg")
        assert not report.passed

    def test_duplicate_fingerprints(self):
        dup = dict(VALID_PATTERN_2, fingerprint=VALID_PATTERN["fingerprint"])
        report = validate_pattern_package([VALID_PATTERN, dup], package_name="test-pkg")
        assert not report.passed
        assert any("duplicate" in c.message.lower() for c in report.checks if not c.passed)

    def test_missing_correlation_strength_is_warning(self):
        no_corr = dict(VALID_PATTERN)
        del no_corr["correlation_strength"]
        report = validate_pattern_package([no_corr], package_name="test-pkg")
        # Should still pass (warning, not error)
        assert report.passed
        assert len(report.warnings) == 1

    def test_summary_output(self):
        report = validate_pattern_package([VALID_PATTERN], package_name="my-pkg")
        summary = report.summary()
        assert "my-pkg" in summary
        assert "PASSED" in summary

    def test_universal_scope_accepted(self):
        universal = dict(VALID_PATTERN, scope="universal")
        report = validate_pattern_package([universal], package_name="test-pkg")
        assert report.passed
