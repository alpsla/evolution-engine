"""
KB Export/Import — Anonymous pattern sharing.

Export: Strips identifying information (signal_refs, event_refs, repo path,
        author info). Produces anonymized pattern digests.

Import: Validates all patterns through kb_security.validate_pattern() before
        storage. Sets scope="community". Never overwrites local patterns.

Usage:
    digests = export_patterns(db_path)
    result = import_patterns(db_path, digests)
"""

import json
from pathlib import Path
from typing import Optional

from evolution.kb_security import (
    validate_pattern,
    verify_fingerprint_integrity,
    compute_import_digest,
    create_attestation,
    validate_attestations,
    PatternValidationError,
)
from evolution.knowledge_store import SQLiteKnowledgeStore


def export_patterns(
    db_path: str | Path,
    scope: str = None,
    evo_dir: str | Path = None,
) -> list[dict]:
    """Export anonymized pattern digests from a knowledge base.

    Strips all identifying information:
    - pattern_id, signal_refs, event_refs
    - repo path, author info
    - raw timestamps (only keep relative age bucket)

    All KB patterns already passed Phase 4 discovery thresholds
    (min_support=5, min_correlation=0.4), so no additional filtering
    is needed here.

    Each exported pattern includes an attestation from this EE instance,
    proving the pattern was computed by a real installation.

    Args:
        db_path: Path to knowledge.db
        scope: Filter patterns by scope (default: all non-expired)
        evo_dir: Path to .evo directory (for signing)

    Returns:
        List of anonymized pattern digests with attestations.
    """
    from pathlib import Path as _Path
    evo_path = _Path(evo_dir) if evo_dir else None

    kb = SQLiteKnowledgeStore(db_path)

    digests = []

    # Knowledge artifacts (promoted patterns)
    for ka in kb.list_knowledge(scope=scope):
        digest = _anonymize_knowledge(ka)
        if digest:
            digest["attestations"] = [create_attestation(digest, evo_path)]
            digests.append(digest)

    # Candidate patterns (not yet promoted)
    for p in kb.list_patterns(scope=scope):
        if p.get("confidence_tier") == "confirmed":
            continue  # Already exported as knowledge artifact
        digest = _anonymize_pattern(p)
        if digest:
            digest["attestations"] = [create_attestation(digest, evo_path)]
            digests.append(digest)

    kb.close()

    return digests


def import_patterns(
    db_path: str | Path,
    patterns: list[dict],
) -> dict:
    """Import community patterns into a knowledge base.

    All patterns are validated through kb_security.validate_pattern().
    Imported patterns get scope="community" and never overwrite local patterns.

    Security layers:
      1. Field validation (sanitize all text, check types/ranges)
      2. Fingerprint integrity (hex format, minimum length)
      3. Attestation validation (strip malformed, deduplicate by instance)
      4. Duplicate check (skip if fingerprint already exists)

    Args:
        db_path: Path to knowledge.db
        patterns: List of pattern digests to import.

    Returns:
        Dict with counts: imported, skipped, rejected.
    """
    kb = SQLiteKnowledgeStore(db_path)

    imported = 0
    skipped = 0
    rejected = 0
    errors = []

    for raw_pattern in patterns:
        # Step 1: Security validation
        try:
            validated = validate_pattern(raw_pattern, require_external_scope=True)
        except PatternValidationError as e:
            rejected += 1
            errors.append(f"{e.field}: {e.reason}")
            continue

        # Step 2: Fingerprint integrity check
        if not verify_fingerprint_integrity(validated):
            rejected += 1
            errors.append(f"Invalid fingerprint: {validated.get('fingerprint', '?')}")
            continue

        # Step 3: Validate attestations
        raw_attestations = raw_pattern.get("attestations", [])
        validated_attestations = validate_attestations(raw_attestations)
        validated["attestations"] = validated_attestations

        # Step 4: Check for duplicates (any scope — local or community)
        existing = kb.get_pattern_by_fingerprint(
            validated["fingerprint"],
        )

        if existing:
            existing_scope = existing.get("scope", "local")

            if existing_scope == "community":
                # Already imported — skip
                skipped += 1
                continue

            # Local pattern exists — promote it
            kb.update_pattern(existing["pattern_id"], {
                "confidence_status": "community_confirmed",
            })
            imported += 1
            continue

        # Step 5: Store as community pattern
        validated["scope"] = "community"
        validated.setdefault("occurrence_count", validated.get("occurrence_count", 1))
        validated.setdefault("confidence_tier", "statistical")
        validated.setdefault("confidence_status", "imported")

        try:
            kb.create_pattern(validated)
            imported += 1
        except Exception as e:
            rejected += 1
            errors.append(str(e))

    kb.close()

    return {
        "imported": imported,
        "skipped": skipped,
        "rejected": rejected,
        "errors": errors[:20],  # Cap error messages
    }


# ─────────────────── Anonymization Helpers ───────────────────


def _anonymize_knowledge(ka: dict) -> Optional[dict]:
    """Anonymize a knowledge artifact for export."""
    sources = ka.get("sources", [])
    metrics = ka.get("metrics", [])
    if not sources or not metrics:
        return None

    return {
        "fingerprint": ka["fingerprint"],
        "pattern_type": ka.get("pattern_type", "co_occurrence"),
        "discovery_method": "statistical",
        "sources": sources,
        "metrics": metrics,
        "description_statistical": ka.get("description_statistical", ""),
        "correlation_strength": ka.get("correlation_strength"),
        "occurrence_count": ka.get("support_count", 1),
        "confidence_tier": "confirmed",
        "scope": "community",
    }


def _anonymize_pattern(p: dict) -> Optional[dict]:
    """Anonymize a candidate pattern for export."""
    sources = p.get("sources", [])
    metrics = p.get("metrics", [])
    if not sources or not metrics:
        return None

    return {
        "fingerprint": p["fingerprint"],
        "pattern_type": p.get("pattern_type", "co_occurrence"),
        "discovery_method": p.get("discovery_method", "statistical"),
        "sources": sources,
        "metrics": metrics,
        "description_statistical": p.get("description_statistical", ""),
        "correlation_strength": p.get("correlation_strength"),
        "occurrence_count": p.get("occurrence_count", 1),
        "confidence_tier": p.get("confidence_tier", "statistical"),
        "scope": "community",
    }
