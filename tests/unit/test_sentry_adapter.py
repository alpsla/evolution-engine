"""
Tests for Sentry error tracking adapter.

Tests use fixture mode (pre-parsed data) — no network calls.
"""

import json
import pytest
from unittest.mock import patch
from pathlib import Path

from evolution.adapters.error_tracking.sentry_adapter import SentryAdapter


# ---- Helpers ----

def _make_issue(id=1, title="ValueError in module.py", level="error",
                status="unresolved", is_unhandled=True,
                first_seen="2025-01-15T10:00:00Z",
                last_seen="2025-01-15T12:00:00Z",
                count=100, user_count=10):
    return {
        "id": str(id),
        "title": title,
        "level": level,
        "status": status,
        "isUnhandled": is_unhandled,
        "firstSeen": first_seen,
        "lastSeen": last_seen,
        "count": count,
        "userCount": user_count,
        "metadata": {},
    }


# ---- Fixture Mode ----

class TestSentryAdapterFixture:

    def test_fixture_mode_basic(self):
        """Fixture mode emits events without API calls."""
        adapter = SentryAdapter(
            issues=[_make_issue()],
            source_id="test",
        )
        events = list(adapter.iter_events())
        assert len(events) == 1

    def test_event_structure(self):
        """Validates SourceEvent fields."""
        adapter = SentryAdapter(
            issues=[_make_issue(id=42, title="TypeError: foo")],
            source_id="test",
        )
        events = list(adapter.iter_events())
        event = events[0]

        assert event["source_family"] == "error_tracking"
        assert event["source_type"] == "sentry"
        assert event["source_id"] == "test"
        assert event["ordering_mode"] == "temporal"
        assert event["attestation"]["type"] == "error_issue"
        assert event["attestation"]["issue_id"] == "42"
        assert event["attestation"]["trust_tier"] == "medium"
        assert event["predecessor_refs"] is None

        payload = event["payload"]
        assert payload["issue_id"] == "42"
        assert payload["title"] == "TypeError: foo"
        assert payload["level"] == "error"
        assert payload["status"] == "unresolved"
        assert payload["is_unhandled"] is True
        assert payload["trigger"]["type"] == "error"
        assert payload["timing"]["first_seen"] == "2025-01-15T10:00:00Z"
        assert payload["stats"]["event_count"] == 100
        assert payload["stats"]["user_count"] == 10

    def test_event_count_and_order(self):
        """Multiple issues sorted by firstSeen."""
        issues = [
            _make_issue(id=3, first_seen="2025-01-17T10:00:00Z"),
            _make_issue(id=1, first_seen="2025-01-15T10:00:00Z"),
            _make_issue(id=2, first_seen="2025-01-16T10:00:00Z"),
        ]
        adapter = SentryAdapter(issues=issues, source_id="test")
        events = list(adapter.iter_events())

        assert len(events) == 3
        # Should be sorted by firstSeen
        ids = [e["payload"]["issue_id"] for e in events]
        assert ids == ["1", "2", "3"]

    def test_status_normalization(self):
        """Maps Sentry statuses."""
        for sentry_status, expected in [
            ("unresolved", "unresolved"),
            ("resolved", "resolved"),
            ("ignored", "ignored"),
            ("muted", "ignored"),
            ("resolvedInNextRelease", "resolved"),
        ]:
            adapter = SentryAdapter(
                issues=[_make_issue(status=sentry_status)],
                source_id="test",
            )
            events = list(adapter.iter_events())
            assert events[0]["payload"]["status"] == expected, \
                f"Expected {expected} for {sentry_status}"

    def test_level_normalization(self):
        """Maps error/warning/fatal/info levels."""
        for sentry_level, expected in [
            ("error", "error"),
            ("warning", "warning"),
            ("fatal", "fatal"),
            ("info", "info"),
            ("debug", "debug"),
            ("sample", "info"),
        ]:
            adapter = SentryAdapter(
                issues=[_make_issue(level=sentry_level)],
                source_id="test",
            )
            events = list(adapter.iter_events())
            assert events[0]["payload"]["level"] == expected, \
                f"Expected {expected} for {sentry_level}"

    def test_unhandled_flag(self):
        """is_unhandled metric correctness."""
        adapter = SentryAdapter(
            issues=[
                _make_issue(id=1, is_unhandled=True),
                _make_issue(id=2, is_unhandled=False),
            ],
            source_id="test",
        )
        events = list(adapter.iter_events())
        assert events[0]["payload"]["is_unhandled"] is True
        assert events[1]["payload"]["is_unhandled"] is False

    def test_empty_fixture(self):
        """Empty fixture list produces no events."""
        adapter = SentryAdapter(issues=[], source_id="test")
        events = list(adapter.iter_events())
        assert len(events) == 0

    def test_source_id_default_fixture(self):
        """Fixture mode generates default source_id."""
        adapter = SentryAdapter(issues=[_make_issue()])
        assert adapter.source_id == "sentry:fixture"

    def test_source_id_with_org_project(self):
        """Source ID includes org/project."""
        adapter = SentryAdapter(
            issues=[_make_issue()],
            org="myorg", project="myproject",
        )
        assert adapter.source_id == "sentry:myorg/myproject"

    def test_stats_from_issue(self):
        """Stats extracted correctly from issue fields."""
        adapter = SentryAdapter(
            issues=[_make_issue(count=1500, user_count=42)],
            source_id="test",
        )
        events = list(adapter.iter_events())
        stats = events[0]["payload"]["stats"]
        assert stats["event_count"] == 1500
        assert stats["user_count"] == 42


# ---- API Mode Validation ----

class TestSentryAdapterAPIMode:

    def test_api_mode_requires_token(self):
        """Raises without token."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="Sentry auth token required"):
                SentryAdapter(org="myorg", project="myproject")

    def test_api_mode_requires_org_project(self):
        """Raises without org/project."""
        with patch.dict("os.environ", {"SENTRY_AUTH_TOKEN": "test-token"}):
            with pytest.raises(RuntimeError, match="Provide org and project"):
                SentryAdapter(token="test-token")

    def test_self_hosted_base_url(self):
        """Custom base URL for self-hosted Sentry."""
        adapter = SentryAdapter(
            issues=[_make_issue()],
            base_url="https://sentry.mycompany.com/api/0",
            source_id="test",
        )
        assert adapter._api_base == "https://sentry.mycompany.com/api/0"

    def test_default_base_url(self):
        """Default base URL is sentry.io."""
        adapter = SentryAdapter(issues=[_make_issue()], source_id="test")
        assert adapter._api_base == "https://sentry.io/api/0"


# ---- Link Header Parsing ----

class TestSentryLinkParsing:

    def test_parse_next_link(self):
        """Parses Sentry cursor pagination Link header."""
        header = (
            '<https://sentry.io/api/0/projects/myorg/myproject/issues/?cursor=abc>; '
            'rel="previous"; results="false"; cursor="abc", '
            '<https://sentry.io/api/0/projects/myorg/myproject/issues/?cursor=xyz>; '
            'rel="next"; results="true"; cursor="xyz"'
        )
        url = SentryAdapter._parse_next_link(header)
        assert url == "https://sentry.io/api/0/projects/myorg/myproject/issues/?cursor=xyz"

    def test_parse_next_link_no_more(self):
        """Returns None when no more results."""
        header = (
            '<https://sentry.io/api/0/issues/?cursor=abc>; '
            'rel="next"; results="false"; cursor="abc"'
        )
        url = SentryAdapter._parse_next_link(header)
        assert url is None

    def test_parse_next_link_empty(self):
        """Returns None for empty header."""
        assert SentryAdapter._parse_next_link("") is None
        assert SentryAdapter._parse_next_link(None) is None


# ---- Phase 2 Integration ----

class TestSentryPhase2Integration:

    def test_phase2_signals(self, tmp_path):
        """Integration test: Sentry events → Phase 2 error_tracking_signals.json."""
        from evolution.phase1_engine import Phase1Engine
        from evolution.phase2_engine import Phase2Engine

        evo_dir = tmp_path / "evo"
        evo_dir.mkdir()

        # Create 10 issues with varying stats (need >= min_baseline)
        issues = []
        for i in range(10):
            issues.append(_make_issue(
                id=i,
                first_seen=f"2025-01-{10+i:02d}T10:00:00Z",
                count=100 + i * 10,
                user_count=5 + i,
                is_unhandled=(i % 2 == 0),
            ))

        adapter = SentryAdapter(issues=issues, source_id="test")

        # Phase 1: ingest
        phase1 = Phase1Engine(evo_dir)
        count = phase1.ingest(adapter)
        assert count == 10

        # Phase 2: compute signals
        phase2 = Phase2Engine(evo_dir, window_size=10, min_baseline=5)
        signals = phase2.run_error_tracking()
        assert len(signals) > 0

        # Verify signal structure
        signal = signals[0]
        assert signal["engine_id"] == "error_tracking"
        assert signal["source_type"] == "sentry"
        assert signal["metric"] in ("event_count", "user_count", "is_unhandled")

        # Verify output file
        out_file = evo_dir / "phase2" / "error_tracking_signals.json"
        assert out_file.exists()
        saved = json.loads(out_file.read_text())
        assert len(saved) == len(signals)

    def test_phase2_run_all_includes_error_tracking(self, tmp_path):
        """run_all() includes error_tracking."""
        from evolution.phase2_engine import Phase2Engine

        evo_dir = tmp_path / "evo"
        (evo_dir / "events").mkdir(parents=True)
        (evo_dir / "phase2").mkdir(parents=True)

        phase2 = Phase2Engine(evo_dir, window_size=10, min_baseline=5)
        results = phase2.run_all()
        assert "error_tracking" in results


# ---- Registry ----

class TestSentryRegistry:

    def test_registry_has_sentry_token(self):
        """error_tracking in TIER2_DETECTORS."""
        from evolution.registry import TIER2_DETECTORS
        assert "sentry_token" in TIER2_DETECTORS
        families = [f for _, f in TIER2_DETECTORS["sentry_token"]]
        assert "error_tracking" in families

    def test_orchestrator_family_label(self):
        """error_tracking in orchestrator family labels."""
        # Just verify the label is referenced in the code
        from evolution.phase5_engine import FAMILY_LABELS
        assert "error_tracking" in FAMILY_LABELS
        assert FAMILY_LABELS["error_tracking"] == "Error Tracking"
