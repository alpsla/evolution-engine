"""
Tests for pattern security hardening: HMAC signing, attestations, quorum.

Covers:
  - Instance secret generation and persistence
  - Instance ID derivation
  - Pattern HMAC signing and verification
  - Attestation creation and validation
  - Quorum enforcement on import
  - Rejection of forged/malformed attestations
"""

import time
from pathlib import Path

import pytest

from evolution.kb_security import (
    get_instance_secret,
    get_instance_id,
    sign_pattern,
    verify_own_signature,
    create_attestation,
    validate_attestations,
    count_unique_attestations,
)


# ─── Sample pattern for testing ───

SAMPLE_PATTERN = {
    "fingerprint": "abcdef1234567890",
    "sources": ["ci", "git"],
    "metrics": ["dispersion", "files_touched"],
    "pattern_type": "co_occurrence",
    "correlation_strength": 0.75,
    "scope": "community",
}


# ─── Instance Secret ───


class TestInstanceSecret:
    def test_generates_secret(self, tmp_path):
        """First call generates and stores a 64-char hex secret."""
        evo_dir = tmp_path / ".evo"
        secret = get_instance_secret(evo_dir)
        assert len(secret) == 64
        assert (evo_dir / "instance_secret").exists()

    def test_persists_across_calls(self, tmp_path):
        """Same secret returned on subsequent calls."""
        evo_dir = tmp_path / ".evo"
        s1 = get_instance_secret(evo_dir)
        s2 = get_instance_secret(evo_dir)
        assert s1 == s2

    def test_different_dirs_different_secrets(self, tmp_path):
        """Different evo dirs produce different secrets."""
        s1 = get_instance_secret(tmp_path / "a")
        s2 = get_instance_secret(tmp_path / "b")
        assert s1 != s2


# ─── Instance ID ───


class TestInstanceId:
    def test_returns_16_char_hex(self, tmp_path):
        """Instance ID is a 16-char hex string."""
        iid = get_instance_id(tmp_path / ".evo")
        assert len(iid) == 16
        assert all(c in "0123456789abcdef" for c in iid)

    def test_stable_across_calls(self, tmp_path):
        """Same instance ID from same directory."""
        evo_dir = tmp_path / ".evo"
        assert get_instance_id(evo_dir) == get_instance_id(evo_dir)

    def test_derived_from_secret(self, tmp_path):
        """Instance ID is derived from the secret, not the path."""
        evo_dir = tmp_path / ".evo"
        secret = get_instance_secret(evo_dir)
        iid = get_instance_id(evo_dir)
        import hashlib
        expected = hashlib.sha256(secret.encode()).hexdigest()[:16]
        assert iid == expected


# ─── Pattern Signing ───


class TestPatternSigning:
    def test_sign_returns_64_char_hex(self, tmp_path):
        """HMAC signature is 64-char hex (SHA-256)."""
        sig = sign_pattern(SAMPLE_PATTERN, tmp_path / ".evo")
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_verify_own_signature(self, tmp_path):
        """Can verify a signature we created."""
        evo_dir = tmp_path / ".evo"
        sig = sign_pattern(SAMPLE_PATTERN, evo_dir)
        assert verify_own_signature(SAMPLE_PATTERN, sig, evo_dir)

    def test_wrong_secret_fails_verification(self, tmp_path):
        """Signature from a different instance fails."""
        sig = sign_pattern(SAMPLE_PATTERN, tmp_path / "a")
        assert not verify_own_signature(SAMPLE_PATTERN, sig, tmp_path / "b")

    def test_tampered_pattern_fails_verification(self, tmp_path):
        """Modifying the pattern invalidates the signature."""
        evo_dir = tmp_path / ".evo"
        sig = sign_pattern(SAMPLE_PATTERN, evo_dir)
        tampered = {**SAMPLE_PATTERN, "correlation_strength": 0.99}
        assert not verify_own_signature(tampered, sig, evo_dir)

    def test_deterministic_for_same_input(self, tmp_path):
        """Same pattern + same secret = same signature."""
        evo_dir = tmp_path / ".evo"
        s1 = sign_pattern(SAMPLE_PATTERN, evo_dir)
        s2 = sign_pattern(SAMPLE_PATTERN, evo_dir)
        assert s1 == s2


# ─── Attestation Creation ───


class TestCreateAttestation:
    def test_structure(self, tmp_path):
        """Attestation has required fields."""
        att = create_attestation(SAMPLE_PATTERN, tmp_path / ".evo")
        assert "instance_id" in att
        assert "signature" in att
        assert "timestamp" in att
        assert "ee_version" in att

    def test_instance_id_matches(self, tmp_path):
        """Attestation's instance_id matches get_instance_id()."""
        evo_dir = tmp_path / ".evo"
        att = create_attestation(SAMPLE_PATTERN, evo_dir)
        assert att["instance_id"] == get_instance_id(evo_dir)

    def test_signature_is_valid(self, tmp_path):
        """Attestation's signature verifies against this instance."""
        evo_dir = tmp_path / ".evo"
        att = create_attestation(SAMPLE_PATTERN, evo_dir)
        assert verify_own_signature(SAMPLE_PATTERN, att["signature"], evo_dir)

    def test_timestamp_is_recent(self, tmp_path):
        """Attestation timestamp is within a few seconds of now."""
        att = create_attestation(SAMPLE_PATTERN, tmp_path / ".evo")
        assert abs(att["timestamp"] - time.time()) < 5


# ─── Attestation Validation ───


class TestValidateAttestations:
    def _make_attestation(self, instance_id="abcdef0123456789",
                          signature="a" * 64, timestamp=None):
        return {
            "instance_id": instance_id,
            "signature": signature,
            "timestamp": timestamp or int(time.time()),
            "ee_version": "0.1.1",
        }

    def test_valid_attestation_passes(self):
        """Well-formed attestation is preserved."""
        atts = [self._make_attestation()]
        result = validate_attestations(atts)
        assert len(result) == 1
        assert result[0]["instance_id"] == "abcdef0123456789"

    def test_rejects_non_hex_instance_id(self):
        """Instance ID with non-hex chars is rejected."""
        atts = [self._make_attestation(instance_id="ZZZZZZZZZZZZZZZZ")]
        assert validate_attestations(atts) == []

    def test_rejects_wrong_length_instance_id(self):
        """Instance ID with wrong length is rejected."""
        atts = [self._make_attestation(instance_id="abcdef")]
        assert validate_attestations(atts) == []

    def test_rejects_short_signature(self):
        """Signature shorter than 64 chars is rejected."""
        atts = [self._make_attestation(signature="abcd1234")]
        assert validate_attestations(atts) == []

    def test_rejects_future_timestamp(self):
        """Timestamp far in the future is rejected."""
        atts = [self._make_attestation(timestamp=int(time.time()) + 7200)]
        assert validate_attestations(atts) == []

    def test_rejects_negative_timestamp(self):
        """Negative timestamp is rejected."""
        atts = [self._make_attestation(timestamp=-1)]
        assert validate_attestations(atts) == []

    def test_deduplicates_by_instance_id(self):
        """Only one attestation per instance ID."""
        iid = "abcdef0123456789"
        atts = [
            self._make_attestation(instance_id=iid, signature="a" * 64),
            self._make_attestation(instance_id=iid, signature="b" * 64),
        ]
        result = validate_attestations(atts)
        assert len(result) == 1

    def test_multiple_unique_instances(self):
        """Multiple attestations from different instances are kept."""
        atts = [
            self._make_attestation(instance_id="a" * 16, signature="1" * 64),
            self._make_attestation(instance_id="b" * 16, signature="2" * 64),
            self._make_attestation(instance_id="c" * 16, signature="3" * 64),
        ]
        result = validate_attestations(atts)
        assert len(result) == 3

    def test_rejects_non_dict(self):
        """Non-dict entries are skipped."""
        assert validate_attestations(["not a dict", 42, None]) == []

    def test_rejects_non_list_input(self):
        """Non-list input returns empty."""
        assert validate_attestations("bad") == []
        assert validate_attestations(None) == []

    def test_caps_at_max(self):
        """Attestation count capped at MAX_ATTESTATIONS."""
        from evolution.kb_security import MAX_ATTESTATIONS
        atts = [
            self._make_attestation(
                instance_id=f"{i:016x}", signature=f"{i:064x}"
            )
            for i in range(MAX_ATTESTATIONS + 10)
        ]
        result = validate_attestations(atts)
        assert len(result) == MAX_ATTESTATIONS


# ─── Import Behavior ───


class TestImportBehavior:
    def test_imports_with_single_attestation(self, tmp_path):
        """Patterns with any valid attestation are imported successfully."""
        from evolution.kb_export import import_patterns
        from evolution.knowledge_store import SQLiteKnowledgeStore

        db_path = tmp_path / "knowledge.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()

        patterns = [{
            "fingerprint": "abcdef1234567890",
            "sources": ["ci"],
            "metrics": ["dispersion"],
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "scope": "community",
            "attestations": [
                {
                    "instance_id": "a" * 16,
                    "signature": "b" * 64,
                    "timestamp": int(time.time()),
                    "ee_version": "0.1.1",
                }
            ],
        }]

        result = import_patterns(db_path, patterns)
        assert result["imported"] == 1
        assert "quarantined" not in result

    def test_imports_with_multiple_attestations(self, tmp_path):
        """Patterns with multiple attestations are imported."""
        from evolution.kb_export import import_patterns
        from evolution.knowledge_store import SQLiteKnowledgeStore

        db_path = tmp_path / "knowledge.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()

        patterns = [{
            "fingerprint": "abcdef1234567890",
            "sources": ["ci"],
            "metrics": ["dispersion"],
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "scope": "community",
            "attestations": [
                {
                    "instance_id": "a" * 16,
                    "signature": "b" * 64,
                    "timestamp": int(time.time()),
                    "ee_version": "0.1.1",
                },
                {
                    "instance_id": "c" * 16,
                    "signature": "d" * 64,
                    "timestamp": int(time.time()),
                    "ee_version": "0.1.1",
                },
            ],
        }]

        result = import_patterns(db_path, patterns)
        assert result["imported"] == 1

    def test_forged_attestations_stripped_but_still_imports(self, tmp_path):
        """Malformed attestations are stripped; pattern still imports with 1 valid."""
        from evolution.kb_export import import_patterns
        from evolution.knowledge_store import SQLiteKnowledgeStore

        db_path = tmp_path / "knowledge.db"
        kb = SQLiteKnowledgeStore(db_path)
        kb.close()

        # 3 attestations, but 2 are malformed → only 1 valid → still imports
        patterns = [{
            "fingerprint": "abcdef1234567890",
            "sources": ["ci"],
            "metrics": ["dispersion"],
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "scope": "community",
            "attestations": [
                {
                    "instance_id": "a" * 16,
                    "signature": "b" * 64,
                    "timestamp": int(time.time()),
                    "ee_version": "0.1.1",
                },
                {
                    "instance_id": "INVALID",  # bad format
                    "signature": "c" * 64,
                    "timestamp": int(time.time()),
                },
                {
                    "instance_id": "d" * 16,
                    "signature": "short",  # bad signature
                    "timestamp": int(time.time()),
                },
            ],
        }]

        result = import_patterns(db_path, patterns)
        assert result["imported"] == 1
