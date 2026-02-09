"""Unit tests for KnowledgeStore (SQLite backend)."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from evolution.knowledge_store import SQLiteKnowledgeStore


@pytest.fixture
def kb(tmp_path):
    """Fresh in-memory-like SQLite KB in a temp directory."""
    db_path = tmp_path / "test_kb.db"
    store = SQLiteKnowledgeStore(db_path)
    yield store
    store.close()


def _make_pattern(fingerprint="abc123", scope="local", **overrides):
    """Create a minimal valid pattern dict."""
    base = {
        "fingerprint": fingerprint,
        "scope": scope,
        "discovery_method": "statistical",
        "pattern_type": "co_occurrence",
        "sources": ["git", "ci"],
        "metrics": ["files_touched", "run_duration"],
        "description_statistical": "test pattern",
        "correlation_strength": 0.75,
        "occurrence_count": 1,
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-01-01T00:00:00Z",
        "confidence_tier": "statistical",
        "confidence_status": "emerging",
        "signal_refs": ["sig-001", "sig-002"],
    }
    base.update(overrides)
    return base


class TestPatternCRUD:
    def test_create_and_get(self, kb):
        pattern = _make_pattern()
        pid = kb.create_pattern(pattern)

        assert pid is not None
        assert len(pid) == 16  # content hash

        retrieved = kb.get_pattern(pid)
        assert retrieved is not None
        assert retrieved["fingerprint"] == "abc123"
        assert retrieved["sources"] == ["git", "ci"]
        assert retrieved["occurrence_count"] == 1

    def test_get_by_fingerprint(self, kb):
        pattern = _make_pattern(fingerprint="unique_fp")
        kb.create_pattern(pattern)

        result = kb.get_pattern_by_fingerprint("unique_fp", "local")
        assert result is not None
        assert result["fingerprint"] == "unique_fp"

    def test_get_by_fingerprint_respects_scope(self, kb):
        kb.create_pattern(_make_pattern(fingerprint="fp1", scope="local"))
        kb.create_pattern(_make_pattern(fingerprint="fp1", scope="community"))

        local = kb.get_pattern_by_fingerprint("fp1", "local")
        community = kb.get_pattern_by_fingerprint("fp1", "community")

        assert local is not None
        assert community is not None
        assert local["pattern_id"] != community["pattern_id"]

    def test_update_pattern(self, kb):
        pid = kb.create_pattern(_make_pattern())
        kb.update_pattern(pid, {
            "description_semantic": "Updated description",
            "confidence_tier": "confirmed",
        })

        updated = kb.get_pattern(pid)
        assert updated["description_semantic"] == "Updated description"
        assert updated["confidence_tier"] == "confirmed"

    def test_update_rejects_unknown_fields(self, kb):
        pid = kb.create_pattern(_make_pattern())
        kb.update_pattern(pid, {"bad_field": "ignored"})

        # Should not crash, and bad field should not appear
        updated = kb.get_pattern(pid)
        assert "bad_field" not in updated

    def test_list_patterns(self, kb):
        kb.create_pattern(_make_pattern(fingerprint="fp1"))
        kb.create_pattern(_make_pattern(fingerprint="fp2"))

        patterns = kb.list_patterns()
        assert len(patterns) == 2

    def test_list_patterns_by_scope(self, kb):
        kb.create_pattern(_make_pattern(fingerprint="fp1", scope="local"))
        kb.create_pattern(_make_pattern(fingerprint="fp2", scope="community"))

        local = kb.list_patterns(scope="local")
        community = kb.list_patterns(scope="community")

        assert len(local) == 1
        assert len(community) == 1

    def test_list_patterns_by_min_occurrences(self, kb):
        kb.create_pattern(_make_pattern(fingerprint="fp1", occurrence_count=5))
        kb.create_pattern(_make_pattern(fingerprint="fp2", occurrence_count=1))

        result = kb.list_patterns(min_occurrences=3)
        assert len(result) == 1
        assert result[0]["occurrence_count"] == 5


class TestPatternIncrement:
    def test_increment_increases_count(self, kb):
        pid = kb.create_pattern(_make_pattern())
        kb.increment_pattern(pid, ["sig-003"], "2026-01-02T00:00:00Z")

        updated = kb.get_pattern(pid)
        assert updated["occurrence_count"] == 2
        assert updated["last_seen"] == "2026-01-02T00:00:00Z"

    def test_increment_links_signal_refs(self, kb):
        pid = kb.create_pattern(_make_pattern(signal_refs=["sig-001"]))
        kb.increment_pattern(pid, ["sig-003", "sig-004"], "2026-01-02T00:00:00Z")

        signals = kb.get_pattern_signals(pid)
        refs = {s["signal_ref"] for s in signals}
        assert "sig-001" in refs
        assert "sig-003" in refs
        assert "sig-004" in refs


class TestKnowledgeCRUD:
    def test_promote_creates_knowledge(self, kb):
        pid = kb.create_pattern(_make_pattern(occurrence_count=10))

        knowledge = {
            "derived_from": pid,
            "fingerprint": "abc123",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "description_statistical": "Promoted pattern",
            "support_count": 10,
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-01-10T00:00:00Z",
            "approval_method": "automatic",
        }
        kid = kb.create_knowledge(knowledge)

        assert kid is not None
        retrieved = kb.get_knowledge(kid)
        assert retrieved is not None
        assert retrieved["support_count"] == 10
        assert retrieved["derived_from"] == pid

    def test_get_knowledge_by_fingerprint(self, kb):
        pid = kb.create_pattern(_make_pattern())
        kid = kb.create_knowledge({
            "derived_from": pid,
            "fingerprint": "abc123",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "description_statistical": "test",
            "support_count": 10,
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-01-01T00:00:00Z",
            "approval_method": "automatic",
        })

        result = kb.get_knowledge_by_fingerprint("abc123", "local")
        assert result is not None
        assert result["knowledge_id"] == kid

    def test_list_knowledge_by_scope(self, kb):
        pid = kb.create_pattern(_make_pattern())
        kb.create_knowledge({
            "derived_from": pid,
            "fingerprint": "abc123",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "description_statistical": "test",
            "support_count": 10,
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-01-01T00:00:00Z",
            "approval_method": "automatic",
        })

        local = kb.list_knowledge(scope="local")
        community = kb.list_knowledge(scope="community")

        assert len(local) == 1
        assert len(community) == 0


class TestPatternLifecycle:
    def test_decay_finds_old_patterns(self, kb):
        # Pattern last seen 100 days ago
        old_time = (datetime.utcnow() - timedelta(days=100)).isoformat() + "Z"
        pid = kb.create_pattern(_make_pattern(last_seen=old_time))

        decayed = kb.get_decayed_patterns(decay_window_days=90)
        assert len(decayed) == 1
        assert decayed[0]["pattern_id"] == pid

    def test_decay_ignores_recent_patterns(self, kb):
        recent = datetime.utcnow().isoformat() + "Z"
        kb.create_pattern(_make_pattern(last_seen=recent))

        decayed = kb.get_decayed_patterns(decay_window_days=90)
        assert len(decayed) == 0

    def test_expire_pattern(self, kb):
        pid = kb.create_pattern(_make_pattern())
        kb.expire_pattern(pid)

        # Expired pattern should not appear in list
        patterns = kb.list_patterns()
        assert len(patterns) == 0

        # But should still be retrievable by ID
        expired = kb.get_pattern(pid)
        assert expired is not None
        assert expired["expired"] == 1

    def test_expired_not_found_by_fingerprint(self, kb):
        pid = kb.create_pattern(_make_pattern(fingerprint="expired_fp"))
        kb.expire_pattern(pid)

        result = kb.get_pattern_by_fingerprint("expired_fp", "local")
        assert result is None


class TestAuditHistory:
    def test_create_logs_history(self, kb):
        pid = kb.create_pattern(_make_pattern())
        history = kb.get_pattern_history(pid)

        assert len(history) >= 1
        assert history[0]["action"] == "created"

    def test_increment_logs_history(self, kb):
        pid = kb.create_pattern(_make_pattern())
        kb.increment_pattern(pid, ["sig-new"], "2026-02-01T00:00:00Z")

        history = kb.get_pattern_history(pid)
        actions = [h["action"] for h in history]
        assert "incremented" in actions

    def test_promote_logs_history(self, kb):
        pid = kb.create_pattern(_make_pattern(occurrence_count=10))
        kb.create_knowledge({
            "derived_from": pid,
            "fingerprint": "abc123",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "description_statistical": "test",
            "support_count": 10,
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-01-01T00:00:00Z",
            "approval_method": "automatic",
        })

        history = kb.get_pattern_history(pid)
        actions = [h["action"] for h in history]
        assert "promoted" in actions
