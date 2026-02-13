# Phase 4 — Pattern Learning & Knowledge Layer Contract

> **Normative Contract**
>
> This document defines the guarantees, boundaries, and invariants of **Phase 4 (Pattern Learning & Knowledge Layer)** of the Evolution Engine.
> It is binding for all Phase 4 implementations. If implementation or design conflicts with this document, the implementation is incorrect.

---

## 1. Purpose

Phase 4 exists to:

> **Discover, validate, accumulate, and retain reusable patterns across Phase 2 signals, over time and across sources, without producing judgment, recommendations, or actions.**

Phase 4 introduces **memory**, not authority.

---

## 2. Sub‑Layers

Phase 4 comprises two distinct sub‑layers with different characteristics:

### 2.1 Phase 4a — Algorithmic Pattern Discovery

**Purpose:** Find statistical correlations, co‑occurrences, temporal sequences, and structural alignments across Phase 2 signals.

**Characteristics:**
- Deterministic (same signals → same patterns)
- Fast (structured query + math)
- No LLM required
- Produces Pattern Objects (candidates)

**Operations:**
- Signal fingerprinting (converting signal combinations into queryable keys)
- Knowledge Base lookup (has this fingerprint been seen before?)
- Co‑occurrence detection (do these signals move together?)
- Temporal sequence analysis (does signal A precede signal B?)
- Structural alignment (do signals from different families share a trigger?)

### 2.2 Phase 4b — Semantic Pattern Interpretation

**Purpose:** Enrich discovered patterns with human‑understandable descriptions by reasoning over Phase 3 explanations.

**Characteristics:**
- Non‑deterministic (LLM‑based)
- Bounded by validation constraints
- Reads Phase 3 explanations as context
- Enriches Pattern Objects with semantic descriptions

**Phase 4b is invoked only when:**
- Phase 4a discovers a new pattern that lacks a semantic description
- A previously described pattern has changed significantly

Phase 4b MUST NOT be used for pattern discovery. Discovery is Phase 4a's responsibility.

---

## 3. Cascade Rule (Critical)

Phase 4 follows a strict confidence cascade:

```
Phase 4a (Math) finds correlation?
    │
    ├── YES → Candidate Pattern (confidence: emerging)
    │          Phase 4b enriches with semantic description
    │          Evidence accumulates over time
    │          Promotion when threshold met
    │
    └── NO → Phase 4b (LLM) notices semantic theme?
              │
              ├── YES → Hypothesis (confidence: speculative)
              │          Requires significantly MORE evidence
              │          Must eventually get statistical confirmation
              │          Hypotheses that never confirm → decay and expire
              │
              └── NO → Honest answer: "Nothing notable detected."
                       No forced insights. System moves on.
```

**Confidence tiers:**

| Tier | Source | Promotion Threshold | Label |
|------|--------|-------------------|-------|
| `statistical` | Phase 4a found correlation | `min_support` (e.g., 10) | `emerging` |
| `confirmed` | Phase 4a + accumulated evidence | `promotion_threshold` (e.g., 50) | `sufficient` |
| `speculative` | Phase 4b only (no statistical backing) | `promotion_threshold × semantic_multiplier` (e.g., 150) | `hypothesis` |
| `approved` | Meets threshold + approval step | N/A | `approved` |

A speculative hypothesis that never receives statistical confirmation MUST decay and eventually expire, never be promoted.

---

## 4. Inputs (Strict)

Phase 4a MAY read:
- Phase 2 deviation signals from one or more Evolution Engines
- Time‑ordered signal histories
- Previously stored Phase 4 pattern objects and knowledge artifacts

Phase 4b MAY read:
- Phase 3 explanations as descriptive context
- Phase 4a pattern objects (to enrich with descriptions)

Phase 4 MAY depend on wall‑clock time for:
- temporal windowing
- approval tracking
- decay calculations

Phase 4 MUST NOT read:
- Phase 1 raw events directly
- Source systems or adapters
- External telemetry or runtime metrics
- Human judgments unless explicitly recorded as approvals

---

## 5. Outputs (Canonical)

Phase 4 MUST emit **Pattern Objects** and **Knowledge Artifacts**.

Pattern Objects represent **candidate patterns** (tentative).
Knowledge Artifacts represent **approved, retained patterns** (institutional knowledge).

Phase 4 outputs are **not explanations** and **not decisions**.

---

## 6. Pattern Object (Candidate) Shape

```json
{
  "pattern_id": "<content-addressable-id>",
  "scope": "local | global",
  "discovery_method": "statistical | semantic",
  "sources": ["git", "ci", "testing"],
  "signal_refs": ["<signal_id>", "<signal_id>"],
  "pattern_type": "co_occurrence | sequence | alignment | stability | drift",
  "fingerprint": "<signal-combination-hash>",
  "description": {
    "statistical": "signals X, Y, Z co-occur with correlation 0.87",
    "semantic": "API expansion outpacing test coverage"
  },
  "support": {
    "occurrence_count": 27,
    "window": "last_90_days",
    "correlation_strength": 0.87
  },
  "confidence": {
    "tier": "statistical | confirmed | speculative",
    "status": "emerging | sufficient | hypothesis"
  }
}
```

Pattern Objects are **tentative** and must not be treated as truth.

---

## 7. Knowledge Artifact (Approved Pattern) Shape

```json
{
  "knowledge_id": "<content-addressable-id>",
  "derived_from": "<pattern_id>",
  "scope": "local | global",
  "pattern_type": "co_occurrence | sequence | alignment | stability",
  "fingerprint": "<signal-combination-hash>",
  "constraints": {
    "sources": ["git", "ci", "testing"],
    "metrics": ["endpoint_count", "failure_rate", "dependency_count"]
  },
  "description": {
    "statistical": "3 signals co-occur with 0.87 correlation across 103 observations",
    "semantic": "Rapid API surface growth accompanied by rising test failures and dependency additions. The codebase is expanding its interface faster than its validation infrastructure."
  },
  "support": {
    "occurrence_count": 103,
    "first_seen": "2026-01-15T00:00:00Z",
    "last_seen": "2026-02-07T00:00:00Z"
  },
  "confidence": {
    "tier": "confirmed",
    "status": "approved",
    "support_count": 103
  },
  "approval": {
    "method": "automatic | human",
    "timestamp": "2026-02-06T21:00:00Z"
  }
}
```

Knowledge Artifacts represent **retained institutional knowledge**.

---

## 8. Knowledge Base

### 8.1 Requirements

The Knowledge Base MUST:
- store Pattern Objects and Knowledge Artifacts
- support fingerprint‑based lookup (exact and fuzzy)
- support temporal queries (patterns within a time window)
- separate local and global knowledge
- version all entries (no silent mutations)
- support audit queries (full history of a pattern's lifecycle)

### 8.2 Backend Strategy

- **Local mode:** SQLite (single repo, no cross‑account)
- **Multi‑tenant mode:** PostgreSQL with pgvector extension (cross‑account patterns, similarity search)

The implementation MUST abstract behind a `KnowledgeStore` interface so the backend is swappable.

### 8.3 Universal Parameters

| Parameter | Purpose | Default |
|-----------|---------|---------|
| `min_support` | Minimum co‑occurrences for candidacy | 10 |
| `min_correlation` | Minimum correlation strength | 0.7 |
| `promotion_threshold` | Occurrences to promote to knowledge | 50 |
| `decay_window` | Time before unseen patterns lose confidence | 90 days |
| `semantic_multiplier` | Extra evidence needed for LLM‑only hypotheses | 3x |

These parameters apply universally across all source families. Per‑metric tuning is explicitly avoided.

---

## 9. Knowledge Scopes

Phase 4 MUST distinguish between:

### 9.1 Local Knowledge
- Derived from a single repository
- Reflects repository‑specific architecture and workflows
- Must not be generalized beyond its scope
- Always takes precedence over any global knowledge

### 9.2 Global Knowledge
- Derived from multiple repositories
- Represents reusable engineering patterns
- MAY be used only as **explicit, defeasible priors** when local history is insufficient
- MUST be clearly labeled as global when surfaced
- MUST decay to zero influence once sufficient local baselines exist
- MUST NOT override or replace local evidence

Local and global knowledge MUST be stored, versioned, and evaluated separately.

---

## 10. Learning & Approval Rules

Phase 4 MUST:
- treat all detected patterns as candidates by default
- accumulate evidence over time
- track confidence tier and support count explicitly
- distinguish statistical from speculative patterns

Phase 4 MUST NOT:
- promote candidates to knowledge without an explicit approval step
- promote speculative hypotheses without eventual statistical confirmation
- delete knowledge silently
- rewrite history

Approval MAY be:
- automatic (threshold‑based and conservative)
- human‑mediated

All approval paths MUST be explicit, auditable, and reversible.

---

## 11. Invariants

All Phase 4 implementations MUST satisfy:

1. **No judgment** — patterns describe relationships, not quality
2. **No recommendations** — Phase 4 never suggests actions
3. **No enforcement** — Phase 4 cannot trigger alerts or blocks
4. **Traceability** — every pattern links to concrete signal IDs
5. **Scope safety** — local knowledge must not leak into global claims
6. **Math first** — algorithmic discovery always precedes semantic interpretation
7. **Honest absence** — if no pattern is found, none is forced

Violations are considered critical defects.

---

## 12. Relationship to Other Phases

- Phase 2 provides the raw deviation signals (→ Phase 4a)
- Phase 3 provides human‑readable explanations (→ Phase 4b, as context)
- Phase 4 discovers and retains patterns
- Phase 5 consumes Phase 4 knowledge to contextualize advisories

Phase 3 MUST NOT consume Phase 4 knowledge directly.
Phase 5 MAY read Phase 4 knowledge artifacts.

---

## 13. Determinism & Evolution

Phase 4a detection algorithms MUST be deterministic.

Phase 4b interpretation is intentionally non‑deterministic (LLM‑based), but:
- is bounded by a validation gate (similar to Phase 3.1)
- must not add facts not present in the signals
- must not produce judgment language
- must produce a structured description, not a narrative essay

Replayability and auditability are preserved through:
- versioned knowledge artifacts
- traceable signal references
- explicit approval records

---

> **Invariant Summary:**
> Phase 4 learns patterns and remembers them. It discovers with math, interprets with language, and promotes only with evidence. It does not judge, decide, or act.
