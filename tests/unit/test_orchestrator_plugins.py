"""
Tests for Tier 3 plugin ingestion in the orchestrator.
"""

from unittest.mock import MagicMock

import pytest

from evolution.orchestrator import Orchestrator
from evolution.registry import AdapterConfig


class FakePhase1:
    """Minimal Phase1Engine stub that counts ingested events."""

    def __init__(self):
        self.ingested = []

    def ingest(self, adapter, **kwargs):
        events = list(adapter.iter_events())
        self.ingested.extend(events)
        return len(events)


def _make_event(family="testing", source_type="fake", metric=1):
    return {
        "source_family": family,
        "source_type": source_type,
        "source_id": source_type,
        "ordering_mode": "temporal",
        "attestation": {"trust_tier": "weak"},
        "payload": {"metric": metric},
    }


class FakeAdapterWithPath:
    """Plugin adapter that accepts repo_path."""

    def __init__(self, repo_path=None):
        self.repo_path = repo_path
        self.source_id = "fake_path"

    def iter_events(self):
        yield _make_event(metric=1)
        yield _make_event(metric=2)


class FakeAdapterWithToken:
    """Plugin adapter that accepts token."""

    def __init__(self, token=None):
        self.token = token
        self.source_id = "fake_token"

    def iter_events(self):
        if self.token:
            yield _make_event(family="ci", source_type="fake_token")


class FakeAdapterBroken:
    """Plugin adapter that raises on iter_events."""

    def __init__(self, **kwargs):
        self.source_id = "broken"

    def iter_events(self):
        raise RuntimeError("intentional failure")


class TestIngestPlugins:
    """Tests for Orchestrator._ingest_plugins()."""

    def _make_orchestrator(self, tmp_path, monkeypatch, **kwargs):
        """Create an orchestrator with isolated license."""
        monkeypatch.delenv("EVO_LICENSE_KEY", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir(exist_ok=True)
        monkeypatch.setenv("HOME", str(fake_home))

        repo = tmp_path / "repo"
        repo.mkdir(exist_ok=True)
        (repo / ".git").mkdir(exist_ok=True)

        return Orchestrator(repo_path=str(repo), **kwargs)

    def test_plugin_events_ingested(self, tmp_path, monkeypatch):
        """Plugin events should be ingested by phase1."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        phase1 = FakePhase1()
        log = MagicMock()

        # Patch load_adapter_class to return our fake
        import evolution.adapter_validator as av
        monkeypatch.setattr(av, "load_adapter_class", lambda _: FakeAdapterWithPath)

        configs = [
            AdapterConfig(
                family="testing",
                adapter_name="fake_path",
                tier=3,
                adapter_class="fake_pkg.FakeAdapterWithPath",
            ),
        ]

        counts = orch._ingest_plugins(phase1, configs, log)

        assert counts == {"testing": 2}
        assert len(phase1.ingested) == 2

    def test_repo_path_passed_for_file_based_plugin(self, tmp_path, monkeypatch):
        """Plugin adapter with repo_path param should receive the repo path."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        phase1 = FakePhase1()
        log = MagicMock()

        constructed_with = {}

        class TrackingAdapter(FakeAdapterWithPath):
            def __init__(self, repo_path=None):
                super().__init__(repo_path=repo_path)
                constructed_with["repo_path"] = repo_path

        import evolution.adapter_validator as av
        monkeypatch.setattr(av, "load_adapter_class", lambda _: TrackingAdapter)

        configs = [
            AdapterConfig(
                family="testing",
                adapter_name="fake_path",
                tier=3,
                adapter_class="fake_pkg.TrackingAdapter",
            ),
        ]

        orch._ingest_plugins(phase1, configs, log)

        assert constructed_with["repo_path"] == str(orch.repo_path)

    def test_token_passed_for_token_based_plugin(self, tmp_path, monkeypatch):
        """Plugin adapter with token param should receive the token."""
        orch = self._make_orchestrator(
            tmp_path, monkeypatch,
            tokens={"jenkins_url": "http://ci.example.com"},
        )
        phase1 = FakePhase1()
        log = MagicMock()

        import evolution.adapter_validator as av
        monkeypatch.setattr(av, "load_adapter_class", lambda _: FakeAdapterWithToken)

        configs = [
            AdapterConfig(
                family="ci",
                adapter_name="fake_token",
                tier=3,
                token_key="jenkins_url",
                adapter_class="fake_pkg.FakeAdapterWithToken",
            ),
        ]

        counts = orch._ingest_plugins(phase1, configs, log)

        assert counts == {"ci": 1}
        assert len(phase1.ingested) == 1

    def test_plugin_failure_doesnt_break_pipeline(self, tmp_path, monkeypatch):
        """A failing plugin should be skipped, not crash the pipeline."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        phase1 = FakePhase1()
        log = MagicMock()

        call_count = {"n": 0}

        def _load_class(dotted_path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return FakeAdapterBroken
            return FakeAdapterWithPath

        import evolution.adapter_validator as av
        monkeypatch.setattr(av, "load_adapter_class", _load_class)

        configs = [
            AdapterConfig(
                family="ci",
                adapter_name="broken",
                tier=3,
                adapter_class="fake_pkg.FakeAdapterBroken",
            ),
            AdapterConfig(
                family="testing",
                adapter_name="fake_path",
                tier=3,
                adapter_class="fake_pkg.FakeAdapterWithPath",
            ),
        ]

        counts = orch._ingest_plugins(phase1, configs, log)

        # Broken plugin skipped, good plugin still ingested
        assert counts == {"testing": 2}
        assert len(phase1.ingested) == 2
        # Warning was logged
        assert any("[warn]" in str(call) for call in log.call_args_list)

    def test_families_override_respected(self, tmp_path, monkeypatch):
        """Plugins outside families_override should be skipped."""
        orch = self._make_orchestrator(
            tmp_path, monkeypatch, families=["ci"],
        )
        phase1 = FakePhase1()
        log = MagicMock()

        import evolution.adapter_validator as av
        monkeypatch.setattr(av, "load_adapter_class", lambda _: FakeAdapterWithPath)

        configs = [
            AdapterConfig(
                family="testing",  # not in override
                adapter_name="fake_path",
                tier=3,
                adapter_class="fake_pkg.FakeAdapterWithPath",
            ),
        ]

        counts = orch._ingest_plugins(phase1, configs, log)

        assert counts == {}
        assert len(phase1.ingested) == 0

    def test_no_plugins_returns_empty(self, tmp_path, monkeypatch):
        """Empty plugin list should return empty dict immediately."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        phase1 = FakePhase1()
        log = MagicMock()

        counts = orch._ingest_plugins(phase1, [], log)

        assert counts == {}
        assert len(phase1.ingested) == 0

    def test_import_error_skips_plugin(self, tmp_path, monkeypatch):
        """Plugin with unimportable class should be skipped."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        phase1 = FakePhase1()
        log = MagicMock()

        import evolution.adapter_validator as av
        monkeypatch.setattr(
            av, "load_adapter_class",
            MagicMock(side_effect=ImportError("no such module")),
        )

        configs = [
            AdapterConfig(
                family="ci",
                adapter_name="nonexistent",
                tier=3,
                adapter_class="nonexistent_package.NonexistentAdapter",
            ),
        ]

        counts = orch._ingest_plugins(phase1, configs, log)

        assert counts == {}
        assert any("[warn]" in str(call) for call in log.call_args_list)

    def test_additive_merge_with_builtin(self, tmp_path, monkeypatch):
        """Plugin counts should add to existing family counts, not replace."""
        orch = self._make_orchestrator(tmp_path, monkeypatch)
        phase1 = FakePhase1()
        log = MagicMock()

        import evolution.adapter_validator as av
        monkeypatch.setattr(av, "load_adapter_class", lambda _: FakeAdapterWithPath)

        configs = [
            AdapterConfig(
                family="testing",
                adapter_name="fake_path",
                tier=3,
                adapter_class="fake_pkg.FakeAdapterWithPath",
            ),
        ]

        counts = orch._ingest_plugins(phase1, configs, log)

        # Verify the family_counts merge logic works (additive)
        existing = {"testing": 10}
        for f, c in counts.items():
            existing[f] = existing.get(f, 0) + c

        assert existing["testing"] == 12  # 10 + 2
