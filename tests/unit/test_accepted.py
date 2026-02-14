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


class TestScopedAcceptance:
    """Tests for scoped acceptance (commits, dates, this-run)."""

    def test_add_with_commit_scope(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        result = ad.add("git:dispersion", "git", "dispersion",
                        scope={"type": "commits", "from": "abc123", "to": "def456"})
        assert result is True
        entries = ad.load()
        assert len(entries) == 1
        assert entries[0]["scope"]["type"] == "commits"
        assert entries[0]["scope"]["from"] == "abc123"

    def test_add_with_date_scope(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        result = ad.add("ci:run_duration", "ci", "run_duration",
                        scope={"type": "dates", "from": "2026-02-10", "to": "2026-02-14"})
        assert result is True
        entries = ad.load()
        assert entries[0]["scope"]["type"] == "dates"

    def test_add_with_this_run_scope(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        result = ad.add("git:dispersion", "git", "dispersion",
                        scope={"type": "this-run", "advisory_id": "adv-001"})
        assert result is True

    def test_add_invalid_scope_raises(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        with pytest.raises(ValueError, match="Invalid scope type"):
            ad.add("git:dispersion", "git", "dispersion",
                   scope={"type": "bogus"})

    def test_duplicate_permanent_blocked_but_scoped_allowed(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        assert ad.add("git:dispersion", "git", "dispersion") is True
        # Same key, permanent → blocked
        assert ad.add("git:dispersion", "git", "dispersion") is False
        # Same key, different scope → allowed
        assert ad.add("git:dispersion", "git", "dispersion",
                      scope={"type": "commits", "from": "a", "to": "b"}) is True
        assert len(ad.load()) == 2

    def test_is_accepted_only_permanent(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "a", "to": "b"})
        # is_accepted only checks permanent scope
        assert ad.is_accepted("git", "dispersion") is False
        # Add permanent
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "permanent"})
        assert ad.is_accepted("git", "dispersion") is True

    def test_accepted_keys_only_permanent(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "a", "to": "b"})
        assert ad.accepted_keys() == set()
        ad.add("ci:run_duration", "ci", "run_duration")  # default = permanent
        assert ad.accepted_keys() == {"ci:run_duration"}

    def test_is_accepted_in_context_permanent(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")
        assert ad.is_accepted_in_context("git", "dispersion") is True

    def test_is_accepted_in_context_this_run(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "this-run", "advisory_id": "adv-001"})
        # Matching advisory
        assert ad.is_accepted_in_context("git", "dispersion", advisory_id="adv-001") is True
        # Wrong advisory
        assert ad.is_accepted_in_context("git", "dispersion", advisory_id="adv-002") is False
        # No advisory
        assert ad.is_accepted_in_context("git", "dispersion") is False

    def test_is_accepted_in_context_commits(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        commits = ["aaa", "bbb", "ccc", "ddd", "eee"]
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "bbb", "to": "ddd"})
        # In range
        assert ad.is_accepted_in_context("git", "dispersion", commit_sha="ccc", commit_list=commits) is True
        assert ad.is_accepted_in_context("git", "dispersion", commit_sha="bbb", commit_list=commits) is True
        assert ad.is_accepted_in_context("git", "dispersion", commit_sha="ddd", commit_list=commits) is True
        # Out of range
        assert ad.is_accepted_in_context("git", "dispersion", commit_sha="aaa", commit_list=commits) is False
        assert ad.is_accepted_in_context("git", "dispersion", commit_sha="eee", commit_list=commits) is False

    def test_is_accepted_in_context_dates(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("ci:run_duration", "ci", "run_duration",
               scope={"type": "dates", "from": "2026-02-10", "to": "2026-02-14"})
        assert ad.is_accepted_in_context("ci", "run_duration", event_date="2026-02-12") is True
        assert ad.is_accepted_in_context("ci", "run_duration", event_date="2026-02-10") is True
        assert ad.is_accepted_in_context("ci", "run_duration", event_date="2026-02-14") is True
        assert ad.is_accepted_in_context("ci", "run_duration", event_date="2026-02-09") is False
        assert ad.is_accepted_in_context("ci", "run_duration", event_date="2026-02-15") is False

    def test_is_accepted_in_context_no_match(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        assert ad.is_accepted_in_context("git", "dispersion") is False

    def test_remove_scoped(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")  # permanent
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "a", "to": "b"})
        assert len(ad.load()) == 2
        # Remove only the commits scope
        assert ad.remove_scoped("git:dispersion", "commits") is True
        entries = ad.load()
        assert len(entries) == 1
        assert entries[0]["scope"]["type"] == "permanent"

    def test_remove_scoped_not_found(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        assert ad.remove_scoped("git:dispersion", "commits") is False

    def test_cleanup_expired(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "this-run", "advisory_id": "old-001"})
        ad.add("ci:run_duration", "ci", "run_duration")  # permanent
        ad.add("git:files_touched", "git", "files_touched",
               scope={"type": "this-run", "advisory_id": "current-001"})

        removed = ad.cleanup_expired(current_advisory_id="current-001")
        assert removed == 1  # old-001 removed
        entries = ad.load()
        assert len(entries) == 2
        keys = [e["key"] for e in entries]
        assert "ci:run_duration" in keys
        assert "git:files_touched" in keys

    def test_cleanup_expired_all_removed(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "this-run", "advisory_id": "old-001"})
        removed = ad.cleanup_expired(current_advisory_id="new-001")
        assert removed == 1
        assert ad.load() == []

    def test_all_entries_for_key(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "a", "to": "b"})
        ad.add("ci:run_duration", "ci", "run_duration")

        entries = ad.all_entries_for_key("git:dispersion")
        assert len(entries) == 2
        assert all(e["key"] == "git:dispersion" for e in entries)

    def test_all_entries_for_key_empty(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        assert ad.all_entries_for_key("nonexistent") == []

    def test_remove_deletes_all_scopes(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "a", "to": "b"})
        assert ad.remove("git:dispersion") is True
        assert ad.load() == []

    def test_single_commit_scope(self, evo_dir):
        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "abc123"})
        # Prefix match
        assert ad.is_accepted_in_context("git", "dispersion", commit_sha="abc123def") is True
        assert ad.is_accepted_in_context("git", "dispersion", commit_sha="other") is False

    def test_backward_compat_old_entries_treated_permanent(self, evo_dir):
        """Old entries without scope field are treated as permanent."""
        ad = AcceptedDeviations(evo_dir)
        # Write an old-format entry directly
        import json
        ad.path.parent.mkdir(parents=True, exist_ok=True)
        old_data = {"version": 2, "accepted": [
            {"key": "git:dispersion", "family": "git", "metric": "dispersion",
             "reason": "", "accepted_at": "2026-01-01", "from_advisory": ""}
        ]}
        ad.path.write_text(json.dumps(old_data), encoding="utf-8")
        assert ad.is_accepted("git", "dispersion") is True
        assert ad.is_accepted_in_context("git", "dispersion") is True


class TestAcceptCLIScope:
    """Test evo accept --scope CLI integration."""

    def _setup_advisory(self, evo_dir):
        """Create a minimal advisory for CLI testing."""
        import json
        phase5 = evo_dir / "phase5"
        phase5.mkdir(parents=True, exist_ok=True)
        advisory = {
            "advisory_id": "test-adv-001",
            "changes": [
                {"family": "git", "metric": "dispersion", "deviation_stddev": 3.5,
                 "observed": 0.8, "baseline_median": 0.2},
                {"family": "ci", "metric": "run_duration", "deviation_stddev": 2.1,
                 "observed": 300, "baseline_median": 120},
            ],
        }
        (phase5 / "advisory.json").write_text(json.dumps(advisory), encoding="utf-8")
        return advisory

    def test_accept_permanent_default(self, evo_dir):
        from click.testing import CliRunner
        from evolution.cli import main

        self._setup_advisory(evo_dir)
        runner = CliRunner()
        result = runner.invoke(main, [
            "accept", str(evo_dir.parent), "1",
            "--evo-dir", str(evo_dir),
        ])
        assert result.exit_code == 0
        assert "Accepted 1" in result.output

        ad = AcceptedDeviations(evo_dir)
        entries = ad.load()
        assert len(entries) == 1
        assert entries[0]["scope"]["type"] == "permanent"

    def test_accept_commit_scope(self, evo_dir):
        from click.testing import CliRunner
        from evolution.cli import main

        self._setup_advisory(evo_dir)
        runner = CliRunner()
        result = runner.invoke(main, [
            "accept", str(evo_dir.parent), "1",
            "--evo-dir", str(evo_dir),
            "--scope", "commits", "--from", "abc123", "--to", "def456",
        ])
        assert result.exit_code == 0

        ad = AcceptedDeviations(evo_dir)
        entries = ad.load()
        assert entries[0]["scope"]["type"] == "commits"
        assert entries[0]["scope"]["from"] == "abc123"
        assert entries[0]["scope"]["to"] == "def456"

    def test_accept_date_scope(self, evo_dir):
        from click.testing import CliRunner
        from evolution.cli import main

        self._setup_advisory(evo_dir)
        runner = CliRunner()
        result = runner.invoke(main, [
            "accept", str(evo_dir.parent), "1",
            "--evo-dir", str(evo_dir),
            "--scope", "dates", "--from", "2026-02-10", "--to", "2026-02-14",
        ])
        assert result.exit_code == 0

        ad = AcceptedDeviations(evo_dir)
        entries = ad.load()
        assert entries[0]["scope"]["type"] == "dates"

    def test_accept_this_run_scope(self, evo_dir):
        from click.testing import CliRunner
        from evolution.cli import main

        self._setup_advisory(evo_dir)
        runner = CliRunner()
        result = runner.invoke(main, [
            "accept", str(evo_dir.parent), "1",
            "--evo-dir", str(evo_dir),
            "--scope", "this-run",
        ])
        assert result.exit_code == 0

        ad = AcceptedDeviations(evo_dir)
        entries = ad.load()
        assert entries[0]["scope"]["type"] == "this-run"
        assert entries[0]["scope"]["advisory_id"] == "test-adv-001"

    def test_accept_commits_requires_from(self, evo_dir):
        from click.testing import CliRunner
        from evolution.cli import main

        self._setup_advisory(evo_dir)
        runner = CliRunner()
        result = runner.invoke(main, [
            "accept", str(evo_dir.parent), "1",
            "--evo-dir", str(evo_dir),
            "--scope", "commits",
        ])
        assert result.exit_code != 0
        assert "--from is required" in result.output

    def test_accepted_list_shows_scope(self, evo_dir):
        from click.testing import CliRunner
        from evolution.cli import main

        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "abc123", "to": "def456"})

        runner = CliRunner()
        result = runner.invoke(main, [
            "accepted", "list", str(evo_dir.parent),
            "--evo-dir", str(evo_dir),
        ])
        assert result.exit_code == 0
        assert "[commits: abc123..def456]" in result.output

    def test_accepted_remove_with_scope_type(self, evo_dir):
        from click.testing import CliRunner
        from evolution.cli import main

        ad = AcceptedDeviations(evo_dir)
        ad.add("git:dispersion", "git", "dispersion")  # permanent
        ad.add("git:dispersion", "git", "dispersion",
               scope={"type": "commits", "from": "a", "to": "b"})

        runner = CliRunner()
        result = runner.invoke(main, [
            "accepted", "remove", str(evo_dir.parent), "git:dispersion",
            "--evo-dir", str(evo_dir),
            "--scope-type", "commits",
        ])
        assert result.exit_code == 0
        assert "scope: commits" in result.output

        # Permanent entry should still exist
        entries = ad.load()
        assert len(entries) == 1
        assert entries[0]["scope"]["type"] == "permanent"


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
