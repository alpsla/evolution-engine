"""Unit tests for KB export/import with security validation."""

import json
from pathlib import Path

import pytest

from evolution.knowledge_store import SQLiteKnowledgeStore
from evolution.kb_export import export_patterns, import_patterns


@pytest.fixture
def kb_with_patterns(tmp_path):
    """Create a KB with sample patterns and knowledge artifacts."""
    db_path = tmp_path / "knowledge.db"
    kb = SQLiteKnowledgeStore(db_path)

    # Create a pattern
    pid = kb.create_pattern({
        "fingerprint": "abc123def456",
        "scope": "local",
        "discovery_method": "statistical",
        "pattern_type": "co_occurrence",
        "sources": ["git", "ci"],
        "metrics": ["files_touched", "run_duration"],
        "description_statistical": "Git files and CI duration co-occur",
        "correlation_strength": 0.72,
        "occurrence_count": 15,
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-02-01T00:00:00Z",
        "confidence_tier": "confirmed",
        "confidence_status": "sufficient",
    })

    # Promote to knowledge
    kb.create_knowledge({
        "derived_from": pid,
        "fingerprint": "abc123def456",
        "scope": "local",
        "pattern_type": "co_occurrence",
        "sources": ["git", "ci"],
        "metrics": ["files_touched", "run_duration"],
        "description_statistical": "Git files and CI duration co-occur",
        "support_count": 15,
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-02-01T00:00:00Z",
        "approval_method": "automatic",
    })

    # Create another candidate pattern
    kb.create_pattern({
        "fingerprint": "bbb222ccc333",
        "scope": "local",
        "discovery_method": "statistical",
        "pattern_type": "co_occurrence",
        "sources": ["git", "dependency"],
        "metrics": ["dispersion", "dependency_count"],
        "description_statistical": "Git dispersion and dep count co-occur",
        "correlation_strength": 0.55,
        "occurrence_count": 5,
        "first_seen": "2026-01-15T00:00:00Z",
        "last_seen": "2026-02-01T00:00:00Z",
        "confidence_tier": "statistical",
        "confidence_status": "emerging",
    })

    kb.close()
    return db_path


class TestExport:
    def test_exports_knowledge_artifacts(self, kb_with_patterns):
        digests = export_patterns(kb_with_patterns)
        assert len(digests) >= 1

        # First should be the promoted knowledge artifact
        ka_digest = [d for d in digests if d["fingerprint"] == "abc123def456"]
        assert len(ka_digest) == 1
        assert ka_digest[0]["confidence_tier"] == "confirmed"

    def test_exports_strong_patterns(self, kb_with_patterns):
        digests = export_patterns(kb_with_patterns)
        fp_list = [d["fingerprint"] for d in digests]
        assert "bbb222ccc333" in fp_list

    def test_export_strips_identifying_info(self, kb_with_patterns):
        digests = export_patterns(kb_with_patterns)
        for d in digests:
            assert "pattern_id" not in d
            assert "signal_refs" not in d
            assert "event_refs" not in d
            assert d["scope"] == "community"

    def test_export_includes_required_fields(self, kb_with_patterns):
        digests = export_patterns(kb_with_patterns)
        for d in digests:
            assert "fingerprint" in d
            assert "sources" in d
            assert "metrics" in d
            assert "pattern_type" in d


class TestImport:
    def test_import_valid_pattern(self, tmp_path):
        db_path = tmp_path / "kb.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()

        patterns = [{
            "fingerprint": "aaa111bbb222",
            "scope": "community",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "description_statistical": "Test pattern",
            "correlation_strength": 0.6,
            "occurrence_count": 10,
            "confidence_tier": "statistical",
        }]

        result = import_patterns(db_path, patterns)
        assert result["imported"] == 1
        assert result["skipped"] == 0
        assert result["rejected"] == 0

        # Verify stored correctly
        kb = SQLiteKnowledgeStore(db_path)
        stored = kb.get_pattern_by_fingerprint("aaa111bbb222", "community")
        assert stored is not None
        assert stored["scope"] == "community"
        kb.close()

    def test_import_rejects_malicious_pattern(self, tmp_path):
        db_path = tmp_path / "kb.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()

        patterns = [{
            "fingerprint": "aaa111bbb222",
            "scope": "community",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "description_statistical": '<script>alert("xss")</script>',
            "correlation_strength": 0.6,
        }]

        result = import_patterns(db_path, patterns)
        assert result["imported"] == 0
        assert result["rejected"] == 1

    def test_import_skips_duplicates(self, tmp_path):
        db_path = tmp_path / "kb.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()

        pattern = {
            "fingerprint": "aaa111bbb222",
            "scope": "community",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": 0.6,
            "occurrence_count": 10,
            "confidence_tier": "statistical",
        }

        # Import once
        result1 = import_patterns(db_path, [pattern])
        assert result1["imported"] == 1

        # Import again — should skip
        result2 = import_patterns(db_path, [pattern])
        assert result2["imported"] == 0
        assert result2["skipped"] == 1

    def test_import_rejects_local_scope(self, tmp_path):
        db_path = tmp_path / "kb.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()

        patterns = [{
            "fingerprint": "aaa111bbb222",
            "scope": "local",  # Should be rejected
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
        }]

        result = import_patterns(db_path, patterns)
        assert result["rejected"] == 1

    def test_import_strips_signal_refs(self, tmp_path):
        db_path = tmp_path / "kb.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()

        patterns = [{
            "fingerprint": "aaa111bbb222",
            "scope": "community",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": 0.6,
            "occurrence_count": 5,
            "confidence_tier": "statistical",
            "signal_refs": ["../../etc/passwd"],  # Malicious ref
        }]

        result = import_patterns(db_path, patterns)
        assert result["imported"] == 1

        # Verify no signal refs stored
        kb = SQLiteKnowledgeStore(db_path)
        stored = kb.get_pattern_by_fingerprint("aaa111bbb222", "community")
        signals = kb.get_pattern_signals(stored["pattern_id"])
        assert len(signals) == 0
        kb.close()




    def test_import_promotes_local_instead_of_duplicating(self, tmp_path):
        """When a local pattern exists, import should promote it, not create a duplicate."""
        db_path = tmp_path / "kb.db"
        kb = SQLiteKnowledgeStore(db_path)

        # Pre-existing local pattern
        kb.create_pattern({
            "fingerprint": "aaa111bbb222",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": 0.6,
            "occurrence_count": 10,
            "confidence_tier": "statistical",
            "confidence_status": "emerging",
        })
        kb.close()

        # Import community pattern with same fingerprint
        community_pattern = {
            "fingerprint": "aaa111bbb222",
            "scope": "community",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": 0.6,
            "occurrence_count": 10,
            "confidence_tier": "statistical",
        }

        result = import_patterns(db_path, [community_pattern])
        assert result["imported"] == 1
        assert result["skipped"] == 0

        # Verify: local pattern promoted, NO community duplicate created
        kb = SQLiteKnowledgeStore(db_path)
        local = kb.get_pattern_by_fingerprint("aaa111bbb222", scope="local")
        community = kb.get_pattern_by_fingerprint("aaa111bbb222", scope="community")
        assert local is not None
        assert local["confidence_status"] == "community_confirmed"
        assert community is None  # No duplicate
        kb.close()

    def test_import_always_promotes_local(self, tmp_path):
        """When a local pattern exists, import always promotes it."""
        db_path = tmp_path / "kb.db"
        kb = SQLiteKnowledgeStore(db_path)

        kb.create_pattern({
            "fingerprint": "aaa111bbb222",
            "scope": "local",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": 0.6,
            "occurrence_count": 10,
            "confidence_tier": "statistical",
            "confidence_status": "emerging",
        })
        kb.close()

        community_pattern = {
            "fingerprint": "aaa111bbb222",
            "scope": "community",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git", "ci"],
            "metrics": ["files_touched", "run_duration"],
            "correlation_strength": 0.6,
            "occurrence_count": 10,
            "confidence_tier": "statistical",
        }

        # No attestations — should still promote (quorum removed)
        result = import_patterns(db_path, [community_pattern])
        assert result["imported"] == 1

        # Verify: local pattern promoted, no duplicate
        kb = SQLiteKnowledgeStore(db_path)
        local = kb.get_pattern_by_fingerprint("aaa111bbb222", scope="local")
        community = kb.get_pattern_by_fingerprint("aaa111bbb222", scope="community")
        assert local is not None
        assert local["confidence_status"] == "community_confirmed"
        assert community is None  # No duplicate
        kb.close()


class TestExportImportRoundTrip:
    def test_round_trip(self, kb_with_patterns, tmp_path):
        """Export from repo A → import to repo B → verify scope separation."""
        # Export
        digests = export_patterns(kb_with_patterns)
        assert len(digests) >= 1

        # Import into a new KB
        new_db = tmp_path / "new_kb.db"
        kb = SQLiteKnowledgeStore(new_db)
        kb.close()

        result = import_patterns(new_db, digests)
        assert result["imported"] >= 1
        assert result["rejected"] == 0

        # Verify scope
        kb = SQLiteKnowledgeStore(new_db)
        community = kb.list_patterns(scope="community")
        local = kb.list_patterns(scope="local")
        assert len(community) >= 1
        assert len(local) == 0  # Nothing local in the new KB
        kb.close()
