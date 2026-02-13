"""Unit tests for accepted deviations (accept/unaccept workflow)."""

import json
from pathlib import Path

import pytest

from evolution.accepted import AcceptedDeviations


class TestAcceptedDeviations:
    def test_add_and_load(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        result = ad.add("git:dispersion", "git", "dispersion",
                        reason="Known refactoring spike", advisory_id="abc123")
        assert result is True

        entries = ad.load()
        assert len(entries) == 1
        assert entries[0]["key"] == "git:dispersion"
        assert entries[0]["family"] == "git"
        assert entries[0]["metric"] == "dispersion"
        assert entries[0]["reason"] == "Known refactoring spike"
        assert entries[0]["from_advisory"] == "abc123"
        assert entries[0]["accepted_at"]  # has a timestamp

    def test_duplicate_add_returns_false(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        assert ad.add("git:dispersion", "git", "dispersion") is True
        assert ad.add("git:dispersion", "git", "dispersion") is False
        assert len(ad.load()) == 1

    def test_remove(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")
        ad.add("ci:run_duration", "ci", "run_duration")

        assert ad.remove("git:dispersion") is True
        entries = ad.load()
        assert len(entries) == 1
        assert entries[0]["key"] == "ci:run_duration"

    def test_remove_not_found(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        assert ad.remove("nonexistent:key") is False

    def test_clear(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")
        ad.add("ci:run_duration", "ci", "run_duration")

        count = ad.clear()
        assert count == 2
        assert ad.load() == []

    def test_clear_empty(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        assert ad.clear() == 0

    def test_is_accepted(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")

        assert ad.is_accepted("git", "dispersion") is True
        assert ad.is_accepted("ci", "run_duration") is False

    def test_accepted_keys_set(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")
        ad.add("ci:run_duration", "ci", "run_duration")

        keys = ad.accepted_keys()
        assert keys == {"git:dispersion", "ci:run_duration"}

    def test_empty_file(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        assert ad.load() == []
        assert ad.accepted_keys() == set()
        assert ad.is_accepted("git", "dispersion") is False

    def test_corrupted_file(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.path.parent.mkdir(parents=True, exist_ok=True)
        ad.path.write_text("not json", encoding="utf-8")
        assert ad.load() == []

    def test_persistence_across_instances(self, evo_dir):
        ad1 = AcceptedDeviations(evo_dir)
        ad1.add("git:dispersion", "git", "dispersion")

        ad2 = AcceptedDeviations(evo_dir)
        assert ad2.is_accepted("git", "dispersion") is True


class TestPhase5AcceptedFiltering:
    """Test that Phase 5 filters out accepted deviations."""

    def test_phase5_filters_accepted(self, populated_through_phase2):
        from evolution.accepted import AcceptedDeviations
        from evolution.phase5_engine import Phase5Engine

        evo_dir = populated_through_phase2
        engine = Phase5Engine(evo_dir)

        # Run without accepted deviations
        result_before = engine.run(scope="test-repo")
        if result_before["status"] != "complete":
            pytest.skip("No significant changes in test data")

        changes_before = result_before["advisory"]["changes"]
        assert len(changes_before) > 0

        # Accept the first change
        first = changes_before[0]
        key = f"{first['family']}:{first['metric']}"
        ad = AcceptedDeviations(evo_dir)
        ad.add(key, first["family"], first["metric"])

        # Re-run — accepted change should be filtered out
        engine2 = Phase5Engine(evo_dir)
        result_after = engine2.run(scope="test-repo")

        if result_after["status"] == "complete":
            changes_after = result_after["advisory"]["changes"]
            after_keys = {f"{c['family']}:{c['metric']}" for c in changes_after}
            assert key not in after_keys
            assert len(changes_after) == len(changes_before) - 1
        else:
            # If all changes were accepted, we get no_significant_changes
            assert len(changes_before) == 1
