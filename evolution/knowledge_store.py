"""
Knowledge Store — Abstract interface and SQLite backend for Phase 4.

Stores Pattern Objects (candidates) and Knowledge Artifacts (approved patterns).
Supports fingerprint-based lookup, temporal queries, scope separation,
versioned entries, and full audit history.

Conforms to PHASE_4_CONTRACT.md §8 and PHASE_4_DESIGN.md §6.
"""

import json
import sqlite3
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional


# ─────────────────── Abstract Interface ───────────────────


class KnowledgeStoreBase(ABC):
    """Abstract interface for the Knowledge Base.

    All backends (SQLite, PostgreSQL) MUST implement this interface.
    """

    # ── Pattern CRUD ──

    @abstractmethod
    def create_pattern(self, pattern: dict) -> str:
        """Store a new Pattern Object. Returns pattern_id."""

    @abstractmethod
    def get_pattern(self, pattern_id: str) -> Optional[dict]:
        """Retrieve a Pattern Object by ID."""

    @abstractmethod
    def get_pattern_by_fingerprint(self, fingerprint: str, scope: str = "local") -> Optional[dict]:
        """Retrieve a Pattern Object by fingerprint and scope."""

    @abstractmethod
    def update_pattern(self, pattern_id: str, updates: dict) -> None:
        """Update fields on a Pattern Object. Records history."""

    @abstractmethod
    def increment_pattern(self, pattern_id: str, signal_refs: list[str], observed_at: str) -> None:
        """Increment occurrence_count and update last_seen. Links signal refs."""

    @abstractmethod
    def list_patterns(self, scope: str = None, confidence_tier: str = None,
                      min_occurrences: int = None) -> list[dict]:
        """List patterns with optional filters."""

    # ── Knowledge CRUD ──

    @abstractmethod
    def create_knowledge(self, knowledge: dict) -> str:
        """Promote a pattern to a Knowledge Artifact. Returns knowledge_id."""

    @abstractmethod
    def get_knowledge(self, knowledge_id: str) -> Optional[dict]:
        """Retrieve a Knowledge Artifact by ID."""

    @abstractmethod
    def get_knowledge_by_fingerprint(self, fingerprint: str, scope: str = "local") -> Optional[dict]:
        """Retrieve a Knowledge Artifact by fingerprint and scope."""

    @abstractmethod
    def list_knowledge(self, scope: str = None) -> list[dict]:
        """List all knowledge artifacts, optionally filtered by scope."""

    # ── Signal Links ──

    @abstractmethod
    def get_pattern_signals(self, pattern_id: str) -> list[dict]:
        """Get all signal references linked to a pattern."""

    # ── History / Audit ──

    @abstractmethod
    def get_pattern_history(self, pattern_id: str) -> list[dict]:
        """Get full audit history for a pattern."""

    # ── Lifecycle ──

    @abstractmethod
    def get_decayed_patterns(self, decay_window_days: int) -> list[dict]:
        """Find patterns not seen within the decay window."""

    @abstractmethod
    def expire_pattern(self, pattern_id: str) -> None:
        """Mark a pattern as expired (archived, not deleted)."""


# ─────────────────── SQLite Backend ───────────────────


class SQLiteKnowledgeStore(KnowledgeStoreBase):
    """SQLite-backed Knowledge Store for local/single-repo use.

    Schema matches PHASE_4_DESIGN.md §6.1 exactly.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        """Create the KB schema from PHASE_4_DESIGN.md §6.1."""
        self._conn.executescript("""
            -- Pattern candidates
            CREATE TABLE IF NOT EXISTS patterns (
                pattern_id      TEXT PRIMARY KEY,
                fingerprint     TEXT NOT NULL,
                scope           TEXT NOT NULL,
                discovery_method TEXT NOT NULL,
                pattern_type    TEXT NOT NULL,
                sources         JSON NOT NULL,
                metrics         JSON NOT NULL,
                description_statistical TEXT,
                description_semantic    TEXT,
                correlation_strength    REAL,
                occurrence_count        INTEGER DEFAULT 1,
                repo_count              INTEGER DEFAULT 0,
                first_seen      TEXT NOT NULL,
                last_seen       TEXT NOT NULL,
                confidence_tier TEXT NOT NULL,
                confidence_status TEXT NOT NULL,
                expired         INTEGER DEFAULT 0,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            -- Approved knowledge
            CREATE TABLE IF NOT EXISTS knowledge (
                knowledge_id    TEXT PRIMARY KEY,
                derived_from    TEXT REFERENCES patterns(pattern_id),
                fingerprint     TEXT NOT NULL,
                scope           TEXT NOT NULL,
                pattern_type    TEXT NOT NULL,
                sources         JSON NOT NULL,
                metrics         JSON NOT NULL,
                description_statistical TEXT NOT NULL,
                description_semantic    TEXT,
                support_count   INTEGER NOT NULL,
                first_seen      TEXT NOT NULL,
                last_seen       TEXT NOT NULL,
                approval_method TEXT NOT NULL,
                approval_timestamp TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );

            -- Signal-to-pattern links (evidence trail)
            CREATE TABLE IF NOT EXISTS pattern_signals (
                pattern_id  TEXT REFERENCES patterns(pattern_id),
                signal_ref  TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (pattern_id, signal_ref)
            );

            -- Audit log
            CREATE TABLE IF NOT EXISTS pattern_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_id  TEXT NOT NULL,
                action      TEXT NOT NULL,
                details     JSON,
                timestamp   TEXT NOT NULL
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_patterns_fingerprint ON patterns(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_patterns_scope ON patterns(scope);
            CREATE INDEX IF NOT EXISTS idx_patterns_expired ON patterns(expired);
            CREATE INDEX IF NOT EXISTS idx_knowledge_fingerprint ON knowledge(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_knowledge_scope ON knowledge(scope);
            CREATE INDEX IF NOT EXISTS idx_pattern_history_pattern ON pattern_history(pattern_id);
        """)
        # Migration: add repo_count column to existing DBs
        try:
            self._conn.execute("ALTER TABLE patterns ADD COLUMN repo_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Column already exists
        self._conn.commit()

    @staticmethod
    def _content_hash(data: dict) -> str:
        """Generate a content-addressable ID from dict."""
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        # Parse JSON fields
        for key in ("sources", "metrics", "details"):
            if key in d and isinstance(d[key], str):
                d[key] = json.loads(d[key])
        return d

    def _log_history(self, pattern_id: str, action: str, details: dict = None):
        self._conn.execute(
            "INSERT INTO pattern_history (pattern_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
            (pattern_id, action, json.dumps(details) if details else None, self._now()),
        )

    # ── Pattern CRUD ──

    def create_pattern(self, pattern: dict) -> str:
        now = self._now()
        pattern_id = pattern.get("pattern_id") or self._content_hash({
            "fingerprint": pattern["fingerprint"],
            "scope": pattern.get("scope", "local"),
            "discovery_method": pattern["discovery_method"],
            "sources": pattern["sources"],
            "metrics": pattern["metrics"],
        })

        # Check if this pattern_id exists as expired — un-expire it instead
        existing = self._conn.execute(
            "SELECT pattern_id, expired FROM patterns WHERE pattern_id = ?",
            (pattern_id,),
        ).fetchone()
        if existing:
            if existing["expired"]:
                self._conn.execute(
                    "UPDATE patterns SET expired = 0, last_seen = ?, updated_at = ? WHERE pattern_id = ?",
                    (now, now, pattern_id),
                )
                self._log_history(pattern_id, "un-expired", {"reason": "rediscovered"})
                self._conn.commit()
                return pattern_id
            # Already exists and not expired — just return it
            return pattern_id

        self._conn.execute("""
            INSERT INTO patterns (
                pattern_id, fingerprint, scope, discovery_method, pattern_type,
                sources, metrics, description_statistical, description_semantic,
                correlation_strength, occurrence_count, repo_count, first_seen, last_seen,
                confidence_tier, confidence_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pattern_id,
            pattern["fingerprint"],
            pattern.get("scope", "local"),
            pattern["discovery_method"],
            pattern["pattern_type"],
            json.dumps(pattern["sources"]),
            json.dumps(pattern["metrics"]),
            pattern.get("description_statistical"),
            pattern.get("description_semantic"),
            pattern.get("correlation_strength"),
            pattern.get("occurrence_count", 1),
            pattern.get("repo_count", 0),
            pattern.get("first_seen", now),
            pattern.get("last_seen", now),
            pattern.get("confidence_tier", "statistical"),
            pattern.get("confidence_status", "emerging"),
            now,
            now,
        ))

        # Link initial signal refs
        for ref in pattern.get("signal_refs", []):
            self._conn.execute(
                "INSERT OR IGNORE INTO pattern_signals (pattern_id, signal_ref, observed_at) VALUES (?, ?, ?)",
                (pattern_id, ref, now),
            )

        self._log_history(pattern_id, "created", {
            "fingerprint": pattern["fingerprint"],
            "discovery_method": pattern["discovery_method"],
        })
        self._conn.commit()
        return pattern_id

    def get_pattern(self, pattern_id: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM patterns WHERE pattern_id = ?", (pattern_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_pattern_by_fingerprint(self, fingerprint: str, scope: str = None) -> Optional[dict]:
        if scope:
            row = self._conn.execute(
                "SELECT * FROM patterns WHERE fingerprint = ? AND scope = ? AND expired = 0",
                (fingerprint, scope),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM patterns WHERE fingerprint = ? AND expired = 0",
                (fingerprint,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def update_pattern(self, pattern_id: str, updates: dict) -> None:
        allowed = {
            "description_statistical", "description_semantic",
            "correlation_strength", "confidence_tier", "confidence_status",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return

        filtered["updated_at"] = self._now()
        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        values = list(filtered.values()) + [pattern_id]

        self._conn.execute(f"UPDATE patterns SET {set_clause} WHERE pattern_id = ?", values)
        self._log_history(pattern_id, "updated", filtered)
        self._conn.commit()

    def increment_pattern(self, pattern_id: str, signal_refs: list[str], observed_at: str) -> None:
        now = self._now()
        self._conn.execute("""
            UPDATE patterns
            SET occurrence_count = occurrence_count + 1,
                last_seen = ?,
                updated_at = ?
            WHERE pattern_id = ?
        """, (observed_at, now, pattern_id))

        for ref in signal_refs:
            self._conn.execute(
                "INSERT OR IGNORE INTO pattern_signals (pattern_id, signal_ref, observed_at) VALUES (?, ?, ?)",
                (pattern_id, ref, observed_at),
            )

        self._log_history(pattern_id, "incremented", {
            "signal_refs": signal_refs,
            "observed_at": observed_at,
        })
        self._conn.commit()

    def list_patterns(self, scope: str = None, confidence_tier: str = None,
                      min_occurrences: int = None) -> list[dict]:
        query = "SELECT * FROM patterns WHERE expired = 0"
        params = []

        if scope:
            query += " AND scope = ?"
            params.append(scope)
        if confidence_tier:
            query += " AND confidence_tier = ?"
            params.append(confidence_tier)
        if min_occurrences is not None:
            query += " AND occurrence_count >= ?"
            params.append(min_occurrences)

        query += " ORDER BY last_seen DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── Knowledge CRUD ──

    def create_knowledge(self, knowledge: dict) -> str:
        now = self._now()
        knowledge_id = knowledge.get("knowledge_id") or self._content_hash({
            "derived_from": knowledge["derived_from"],
            "fingerprint": knowledge["fingerprint"],
        })

        self._conn.execute("""
            INSERT INTO knowledge (
                knowledge_id, derived_from, fingerprint, scope, pattern_type,
                sources, metrics, description_statistical, description_semantic,
                support_count, first_seen, last_seen,
                approval_method, approval_timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            knowledge_id,
            knowledge["derived_from"],
            knowledge["fingerprint"],
            knowledge.get("scope", "local"),
            knowledge["pattern_type"],
            json.dumps(knowledge["sources"]),
            json.dumps(knowledge["metrics"]),
            knowledge["description_statistical"],
            knowledge.get("description_semantic"),
            knowledge["support_count"],
            knowledge["first_seen"],
            knowledge["last_seen"],
            knowledge.get("approval_method", "automatic"),
            knowledge.get("approval_timestamp", now),
            now,
        ))

        self._log_history(knowledge["derived_from"], "promoted", {
            "knowledge_id": knowledge_id,
            "approval_method": knowledge.get("approval_method", "automatic"),
        })
        self._conn.commit()
        return knowledge_id

    def get_knowledge(self, knowledge_id: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM knowledge WHERE knowledge_id = ?", (knowledge_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_knowledge_by_fingerprint(self, fingerprint: str, scope: str = "local") -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM knowledge WHERE fingerprint = ? AND scope = ?",
            (fingerprint, scope),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_knowledge(self, scope: str = None) -> list[dict]:
        if scope:
            rows = self._conn.execute(
                "SELECT * FROM knowledge WHERE scope = ? ORDER BY last_seen DESC", (scope,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM knowledge ORDER BY last_seen DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── Signal Links ──

    def get_pattern_signals(self, pattern_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM pattern_signals WHERE pattern_id = ? ORDER BY observed_at",
            (pattern_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── History / Audit ──

    def get_pattern_history(self, pattern_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM pattern_history WHERE pattern_id = ? ORDER BY timestamp",
            (pattern_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── Lifecycle ──

    def get_decayed_patterns(self, decay_window_days: int) -> list[dict]:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=decay_window_days)).isoformat() + "Z"
        rows = self._conn.execute(
            "SELECT * FROM patterns WHERE expired = 0 AND last_seen < ? ORDER BY last_seen",
            (cutoff,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def expire_pattern(self, pattern_id: str) -> None:
        now = self._now()
        self._conn.execute(
            "UPDATE patterns SET expired = 1, updated_at = ? WHERE pattern_id = ?",
            (now, pattern_id),
        )
        self._log_history(pattern_id, "expired", {"reason": "decay_window_exceeded"})
        self._conn.commit()

    def close(self):
        self._conn.close()
