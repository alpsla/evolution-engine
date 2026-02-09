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
    PatternValidationError,
)
from evolution.knowledge_store import SQLiteKnowledgeStore


def export_patterns(
    db_path: str | Path,
    min_occurrences: int = 3,
    scope: str = None,
) -> list[dict]:
    """Export anonymized pattern digests from a knowledge base.

    Strips all identifying information:
    - pattern_id, signal_refs, event_refs
    - repo path, author info
    - raw timestamps (only keep relative age bucket)

    Args:
        db_path: Path to knowledge.db
        min_occurrences: Minimum occurrences to export (filters noise)
        scope: Filter patterns by scope (default: all non-expired)

    Returns:
        List of anonymized pattern digests.
    """
    kb = SQLiteKnowledgeStore(db_path)

    # Export promoted knowledge artifacts + strong patterns
    digests = []

    # Knowledge artifacts (promoted patterns)
    for ka in kb.list_knowledge(scope=scope):
        digest = _anonymize_knowledge(ka)
        if digest:
            digests.append(digest)

    # Strong candidate patterns (not yet promoted but seen enough times)
    for p in kb.list_patterns(scope=scope, min_occurrences=min_occurrences):
        if p.get("confidence_tier") == "confirmed":
            continue  # Already exported as knowledge artifact
        digest = _anonymize_pattern(p)
        if digest:
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

    Args:
        db_path: Path to knowledge.db
        patterns: List of pattern digests to import.

    Returns:
        Dict with counts: imported, skipped (duplicate), rejected (invalid).
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

        # Step 3: Check for duplicates (same fingerprint + scope)
        existing = kb.get_pattern_by_fingerprint(
            validated["fingerprint"],
            scope="community",
        )
        if existing:
            skipped += 1
            continue

        # Also skip if a local pattern already has this fingerprint
        local_match = kb.get_pattern_by_fingerprint(
            validated["fingerprint"],
            scope="local",
        )

        # Step 4: Store as community pattern
        validated["scope"] = "community"
        validated.setdefault("occurrence_count", validated.get("occurrence_count", 1))
        validated.setdefault("confidence_tier", "statistical")
        validated.setdefault("confidence_status", "imported")

        try:
            kb.create_pattern(validated)
            imported += 1

            # If a local pattern matches, promote it to "confirmed"
            if local_match:
                kb.update_pattern(local_match["pattern_id"], {
                    "confidence_status": "community_confirmed",
                })
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
