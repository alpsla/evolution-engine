"""Unit tests for adapter validator / certification system."""

import pytest

from evolution.adapter_validator import validate_adapter, load_adapter_class, ValidationReport


# ─────────────── Test Adapter Fixtures ───────────────


class GoodAdapter:
    """A valid adapter that passes all checks."""
    source_family = "ci"
    source_type = "my_ci"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, runs=None):
        self.source_id = "my_ci:test"
        self._runs = runs or [{"id": 1, "status": "success", "duration": 120}]

    def iter_events(self):
        for run in self._runs:
            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "ci_run",
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": {
                    "run_id": run["id"],
                    "status": run["status"],
                    "duration_seconds": run["duration"],
                },
            }


class MissingFamilyAdapter:
    """Adapter missing source_family."""
    source_type = "broken"
    ordering_mode = "temporal"
    attestation_tier = "weak"

    def __init__(self):
        self.source_id = "broken"

    def iter_events(self):
        yield {"payload": {}}


class InvalidFamilyAdapter:
    """Adapter with unrecognized source_family."""
    source_family = "quantum_computing"
    source_type = "qbit"
    ordering_mode = "temporal"
    attestation_tier = "weak"

    def __init__(self):
        self.source_id = "qbit:1"

    def iter_events(self):
        yield {
            "source_family": self.source_family,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "ordering_mode": self.ordering_mode,
            "attestation": {"trust_tier": "weak"},
            "payload": {},
        }


class NoIterEventsAdapter:
    """Adapter without iter_events method."""
    source_family = "ci"
    source_type = "nope"
    ordering_mode = "temporal"
    attestation_tier = "weak"


class BrokenIterEventsAdapter:
    """Adapter whose iter_events raises."""
    source_family = "ci"
    source_type = "broken_iter"
    ordering_mode = "temporal"
    attestation_tier = "weak"

    def __init__(self):
        self.source_id = "broken"

    def iter_events(self):
        raise RuntimeError("Something went wrong")


class EmptyAdapter:
    """Adapter that yields no events."""
    source_family = "ci"
    source_type = "empty"
    ordering_mode = "temporal"
    attestation_tier = "weak"

    def __init__(self):
        self.source_id = "empty"

    def iter_events(self):
        return iter([])


class BadEventStructureAdapter:
    """Adapter that yields events missing required fields."""
    source_family = "ci"
    source_type = "bad_events"
    ordering_mode = "temporal"
    attestation_tier = "weak"

    def __init__(self):
        self.source_id = "bad"

    def iter_events(self):
        yield {"payload": {"stuff": 1}}  # Missing source_family, source_type, etc.


class FamilyMismatchAdapter:
    """Adapter where event source_family doesn't match class attribute."""
    source_family = "ci"
    source_type = "mismatch"
    ordering_mode = "temporal"
    attestation_tier = "weak"

    def __init__(self):
        self.source_id = "mismatch"

    def iter_events(self):
        yield {
            "source_family": "deployment",  # Doesn't match class "ci"
            "source_type": self.source_type,
            "source_id": self.source_id,
            "ordering_mode": self.ordering_mode,
            "attestation": {"trust_tier": "weak"},
            "payload": {},
        }


class BadAttestationAdapter:
    """Adapter with missing trust_tier in attestation."""
    source_family = "ci"
    source_type = "bad_att"
    ordering_mode = "temporal"
    attestation_tier = "weak"

    def __init__(self):
        self.source_id = "bad_att"

    def iter_events(self):
        yield {
            "source_family": "ci",
            "source_type": "bad_att",
            "source_id": "bad_att",
            "ordering_mode": "temporal",
            "attestation": "not_a_dict",  # Should be dict
            "payload": {},
        }


class NonJsonAdapter:
    """Adapter that yields non-JSON-serializable events."""
    source_family = "ci"
    source_type = "nonjson"
    ordering_mode = "temporal"
    attestation_tier = "weak"

    def __init__(self):
        self.source_id = "nonjson"

    def iter_events(self):
        yield {
            "source_family": "ci",
            "source_type": "nonjson",
            "source_id": "nonjson",
            "ordering_mode": "temporal",
            "attestation": {"trust_tier": "weak"},
            "payload": {"data": set([1, 2, 3])},  # sets aren't JSON-serializable
        }


# ─────────────── Tests ───────────────


class TestValidAdapter:
    def test_good_adapter_passes(self):
        report = validate_adapter(GoodAdapter)
        assert report.passed
        assert len(report.errors) == 0

    def test_report_summary(self):
        report = validate_adapter(GoodAdapter)
        summary = report.summary()
        assert "PASSED" in summary
        assert "GoodAdapter" in summary

    def test_good_adapter_all_checks_pass(self):
        report = validate_adapter(GoodAdapter)
        for check in report.checks:
            assert check.passed, f"Check '{check.name}' failed: {check.message}"


class TestMissingAttributes:
    def test_missing_source_family(self):
        report = validate_adapter(MissingFamilyAdapter)
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "class_attr_source_family" in failed_names

    def test_invalid_family_name(self):
        report = validate_adapter(InvalidFamilyAdapter)
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "valid_family" in failed_names

    def test_no_iter_events(self):
        report = validate_adapter(NoIterEventsAdapter)
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "has_iter_events" in failed_names


class TestIterEventsProblems:
    def test_broken_iter_events(self):
        report = validate_adapter(BrokenIterEventsAdapter)
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "iter_events_runs" in failed_names

    def test_empty_adapter_warns(self):
        report = validate_adapter(EmptyAdapter)
        # Empty is a warning, not an error
        assert len(report.warnings) >= 1
        warning_names = [c.name for c in report.warnings]
        assert "iter_events_runs" in warning_names


class TestEventValidation:
    def test_bad_event_structure(self):
        report = validate_adapter(BadEventStructureAdapter)
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "event_structure" in failed_names

    def test_family_mismatch(self):
        report = validate_adapter(FamilyMismatchAdapter)
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "family_consistency" in failed_names

    def test_bad_attestation(self):
        report = validate_adapter(BadAttestationAdapter)
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "attestation_structure" in failed_names

    def test_non_json_serializable(self):
        report = validate_adapter(NonJsonAdapter)
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "json_serializable" in failed_names


class TestConstructorArgs:
    def test_passes_constructor_args(self):
        custom_runs = [
            {"id": 100, "status": "failed", "duration": 300},
            {"id": 101, "status": "success", "duration": 60},
        ]
        report = validate_adapter(GoodAdapter, constructor_args={"runs": custom_runs})
        assert report.passed

    def test_bad_constructor_args(self):
        report = validate_adapter(GoodAdapter, constructor_args={"nonexistent_arg": True})
        assert not report.passed
        failed_names = [c.name for c in report.errors]
        assert "can_instantiate" in failed_names


class TestLoadAdapterClass:
    def test_loads_real_adapter(self):
        cls = load_adapter_class(
            "evolution.adapters.dependency.pip_adapter.PipDependencyAdapter"
        )
        assert cls.source_family == "dependency"

    def test_bad_module_path(self):
        with pytest.raises(ImportError):
            load_adapter_class("nonexistent_module.Foo")

    def test_bad_class_name(self):
        with pytest.raises(AttributeError):
            load_adapter_class("evolution.adapters.dependency.pip_adapter.Nonexistent")

    def test_no_dot_in_path(self):
        with pytest.raises(ImportError, match="Invalid path"):
            load_adapter_class("JustAClassName")


class TestValidateRealAdapters:
    """Validate our own built-in adapters as a smoke test."""

    def test_pip_adapter(self):
        from evolution.adapters.dependency.pip_adapter import PipDependencyAdapter
        report = validate_adapter(
            PipDependencyAdapter,
            constructor_args={
                "snapshots": [{
                    "ecosystem": "pip",
                    "manifest_file": "requirements.txt",
                    "trigger": {"commit_sha": "abc123"},
                    "snapshot": {
                        "direct_count": 2,
                        "transitive_count": 0,
                        "total_count": 2,
                        "max_depth": 1,
                    },
                    "dependencies": [
                        {"name": "flask", "version": "2.0", "direct": True, "depth": 1},
                        {"name": "click", "version": "8.0", "direct": True, "depth": 1},
                    ],
                }],
            },
        )
        assert report.passed, report.summary()
