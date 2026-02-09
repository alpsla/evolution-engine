"""Unit tests for KB security: pattern validation and injection prevention."""

import pytest

from evolution.kb_security import (
    validate_pattern,
    verify_fingerprint_integrity,
    compute_import_digest,
    PatternValidationError,
)


def _valid_pattern(**overrides):
    """Create a minimal valid community pattern."""
    base = {
        "fingerprint": "abc123def456",
        "scope": "community",
        "pattern_type": "co_occurrence",
        "discovery_method": "statistical",
        "sources": ["git", "ci"],
        "metrics": ["files_touched", "run_duration"],
        "description_statistical": "Git files_touched and CI run_duration co-occur",
        "correlation_strength": 0.72,
        "occurrence_count": 14,
        "confidence_tier": "statistical",
    }
    base.update(overrides)
    return base


class TestValidatePattern:
    def test_valid_community_pattern_passes(self):
        result = validate_pattern(_valid_pattern())
        assert result["fingerprint"] == "abc123def456"
        assert result["scope"] == "community"

    def test_rejects_local_scope_for_imports(self):
        with pytest.raises(PatternValidationError, match="scope"):
            validate_pattern(_valid_pattern(scope="local"))

    def test_accepts_universal_scope(self):
        result = validate_pattern(_valid_pattern(scope="universal"))
        assert result["scope"] == "universal"

    def test_rejects_non_dict(self):
        with pytest.raises(PatternValidationError):
            validate_pattern("not a dict")

    def test_rejects_missing_fingerprint(self):
        p = _valid_pattern()
        del p["fingerprint"]
        with pytest.raises(PatternValidationError, match="fingerprint"):
            validate_pattern(p)

    def test_rejects_non_hex_fingerprint(self):
        with pytest.raises(PatternValidationError, match="fingerprint"):
            validate_pattern(_valid_pattern(fingerprint="ZZZZ"))

    def test_rejects_oversized_fingerprint(self):
        with pytest.raises(PatternValidationError, match="fingerprint"):
            validate_pattern(_valid_pattern(fingerprint="a" * 100))


class TestXSSPrevention:
    def test_rejects_script_tag_in_description(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_statistical='<script>alert("xss")</script>'
            ))

    def test_rejects_javascript_protocol(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_semantic="javascript:alert(1)"
            ))

    def test_rejects_template_injection(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_statistical="{{config.__class__.__init__.__globals__}}"
            ))

    def test_rejects_js_template_literal(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_statistical="${process.env.SECRET}"
            ))


class TestPathTraversal:
    def test_rejects_path_traversal_in_description(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_statistical="../../etc/passwd"
            ))

    def test_rejects_file_protocol(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_semantic="file:///etc/shadow"
            ))


class TestShellInjection:
    def test_rejects_shell_commands_in_description(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_statistical="; rm -rf /"
            ))

    def test_rejects_backtick_execution(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_statistical="`whoami`"
            ))


class TestSQLInjection:
    def test_rejects_drop_table(self):
        with pytest.raises(PatternValidationError, match="dangerous content"):
            validate_pattern(_valid_pattern(
                description_statistical="; DROP TABLE patterns"
            ))


class TestFieldTypeValidation:
    def test_rejects_string_as_correlation(self):
        with pytest.raises(PatternValidationError, match="correlation_strength"):
            validate_pattern(_valid_pattern(correlation_strength="not_a_number"))

    def test_rejects_out_of_range_correlation(self):
        with pytest.raises(PatternValidationError, match="correlation_strength"):
            validate_pattern(_valid_pattern(correlation_strength=5.0))

    def test_rejects_negative_occurrence_count(self):
        with pytest.raises(PatternValidationError, match="occurrence_count"):
            validate_pattern(_valid_pattern(occurrence_count=-1))

    def test_rejects_float_occurrence_count(self):
        with pytest.raises(PatternValidationError, match="occurrence_count"):
            validate_pattern(_valid_pattern(occurrence_count=3.5))

    def test_rejects_invalid_pattern_type(self):
        with pytest.raises(PatternValidationError, match="pattern_type"):
            validate_pattern(_valid_pattern(pattern_type="evil_type"))

    def test_rejects_invalid_discovery_method(self):
        with pytest.raises(PatternValidationError, match="discovery_method"):
            validate_pattern(_valid_pattern(discovery_method="magic"))

    def test_rejects_invalid_confidence_tier(self):
        with pytest.raises(PatternValidationError, match="confidence_tier"):
            validate_pattern(_valid_pattern(confidence_tier="ultra_confident"))


class TestNameValidation:
    def test_rejects_special_chars_in_source_name(self):
        with pytest.raises(PatternValidationError, match="sources"):
            validate_pattern(_valid_pattern(sources=["git; rm -rf /"]))

    def test_rejects_special_chars_in_metric_name(self):
        with pytest.raises(PatternValidationError, match="metrics"):
            validate_pattern(_valid_pattern(metrics=["<script>alert(1)</script>"]))

    def test_accepts_dotted_names(self):
        result = validate_pattern(_valid_pattern(
            sources=["git.local"],
            metrics=["files_touched.count"],
        ))
        assert "git.local" in result["sources"]

    def test_rejects_empty_sources(self):
        with pytest.raises(PatternValidationError, match="sources"):
            validate_pattern(_valid_pattern(sources=[]))

    def test_rejects_empty_metrics(self):
        with pytest.raises(PatternValidationError, match="metrics"):
            validate_pattern(_valid_pattern(metrics=[]))


class TestPayloadSize:
    def test_rejects_oversized_description(self):
        with pytest.raises(PatternValidationError, match="max length"):
            validate_pattern(_valid_pattern(
                description_statistical="a" * 2000
            ))

    def test_rejects_too_many_sources(self):
        with pytest.raises(PatternValidationError, match="max count"):
            validate_pattern(_valid_pattern(
                sources=[f"source_{i}" for i in range(50)]
            ))

    def test_rejects_too_many_metrics(self):
        with pytest.raises(PatternValidationError, match="max count"):
            validate_pattern(_valid_pattern(
                metrics=[f"metric_{i}" for i in range(50)]
            ))


class TestSignalRefStripping:
    def test_strips_signal_refs_on_import(self):
        """External signal_refs could be used for reference injection."""
        result = validate_pattern(_valid_pattern(
            signal_refs=["../../../etc/passwd", "'; DROP TABLE patterns; --"]
        ))
        assert result["signal_refs"] == []


class TestFingerprintIntegrity:
    def test_valid_fingerprint(self):
        assert verify_fingerprint_integrity({"fingerprint": "abc123def456"})

    def test_rejects_empty_fingerprint(self):
        assert not verify_fingerprint_integrity({"fingerprint": ""})

    def test_rejects_non_hex_fingerprint(self):
        assert not verify_fingerprint_integrity({"fingerprint": "ZZZZ"})

    def test_rejects_short_fingerprint(self):
        assert not verify_fingerprint_integrity({"fingerprint": "abc"})


class TestImportDigest:
    def test_deterministic(self):
        p = _valid_pattern()
        d1 = compute_import_digest(p)
        d2 = compute_import_digest(p)
        assert d1 == d2

    def test_different_patterns_different_digest(self):
        p1 = _valid_pattern(fingerprint="aaa111")
        p2 = _valid_pattern(fingerprint="bbb222")
        assert compute_import_digest(p1) != compute_import_digest(p2)

    def test_order_independent_for_sources(self):
        p1 = _valid_pattern(sources=["git", "ci"])
        p2 = _valid_pattern(sources=["ci", "git"])
        assert compute_import_digest(p1) == compute_import_digest(p2)
