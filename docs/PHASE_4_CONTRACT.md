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

## 2. Inputs (Strict)

Phase 4 MAY read:
- Phase 2 deviation signals from one or more Evolution Engines
- Phase 3 explanations *only as descriptive context*
- Time‑ordered signal histories
- Previously approved Phase 4 knowledge artifacts

Phase 4 MAY depend on wall‑clock time for:
- temporal windowing
- approval tracking

This is permitted because pattern discovery inherently operates across temporal boundaries, unlike Phase 2 which operates on event sequences.

Phase 4 MUST NOT read:
- Phase 1 raw events directly
- Source systems or adapters
- External telemetry or runtime metrics
- Human judgments unless explicitly recorded as approvals

---

## 3. Outputs (Canonical)

Phase 4 MUST emit **Pattern Objects** and **Knowledge Artifacts**.

Pattern Objects represent **candidate patterns**.
Knowledge Artifacts represent **approved, retained patterns**.

Phase 4 outputs are **not explanations** and **not decisions**.

---

## 4. Pattern Object (Candidate) Shape

```json
{
  "pattern_id": "<content-addressable-id>",
  "scope": "local | global",
  "sources": ["git", "ci"],
  "signal_refs": ["<signal_id>", "<signal_id>"],
  "pattern_type": "co_occurrence | sequence | alignment | stability | drift",
  "description": "<structured, non-narrative description>",
  "support": {
    "occurrence_count": 27,
    "window": "last_90_days"
  },
  "confidence": {
    "status": "emerging | sufficient"
  }
}
```

Pattern Objects are **tentative** and must not be treated as truth.

> **Note:** Any numeric confidence score used for promotion logic is an **internal implementation detail** and MUST NOT be exposed as a canonical output.

---

## 5. Knowledge Artifact (Approved Pattern) Shape

```json
{
  "knowledge_id": "<content-addressable-id>",
  "derived_from": "<pattern_id>",
  "scope": "local | global",
  "pattern_type": "co_occurrence | sequence | alignment | stability",
  "constraints": {
    "sources": ["git", "ci"],
    "metrics": ["files_touched", "change_locality"]
  },
  "confidence": {
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

## 6. Knowledge Scopes

Phase 4 MUST distinguish between:

### 6.1 Local Knowledge
- Derived from a single repository
- Reflects repository‑specific architecture and workflows
- Must not be generalized beyond its scope
- Always takes precedence over any global knowledge

### 6.2 Global Knowledge
- Derived from multiple repositories
- Represents reusable engineering patterns
- MAY be used only as **explicit, defeasible priors** when local history is insufficient
- MUST be clearly labeled as global when surfaced
- MUST decay to zero influence once sufficient local baselines exist
- MUST NOT override or replace local evidence

Local and global knowledge MUST be stored, versioned, and evaluated separately.

---

## 7. Learning & Approval Rules

Phase 4 MUST:
- treat all detected patterns as candidates by default
- accumulate evidence over time
- track confidence and support explicitly

Phase 4 MUST NOT:
- promote candidates to knowledge without an explicit approval step
- delete knowledge silently
- rewrite history

Approval MAY be:
- automatic (threshold‑based and conservative)
- human‑mediated

All approval paths MUST be explicit, auditable, and reversible.

---

## 8. Invariants

All Phase 4 implementations MUST satisfy:

1. **No judgment** — patterns describe relationships, not quality
2. **No recommendations** — Phase 4 never suggests actions
3. **No enforcement** — Phase 4 cannot trigger alerts or blocks
4. **Traceability** — every pattern links to concrete signal IDs
5. **Scope safety** — local knowledge must not leak into global claims

Violations are considered critical defects.

---

## 9. Relationship to Other Phases

- Phase 2 provides the raw deviation signals
- Phase 3 provides human‑readable explanations (optional context)
- Phase 4 discovers and retains patterns
- Phase 5 (future) may consume Phase 4 knowledge to inform decisions

Phase 3 MUST NOT consume Phase 4 knowledge directly.

---

## 10. Determinism & Evolution

Phase 4 detection algorithms SHOULD be deterministic where possible.

This relaxation from strict determinism is intentional:
- pattern discovery may involve heuristic thresholds or statistical processes
- future implementations MAY use LLM‑assisted pattern discovery

Replayability and auditability are preserved through:
- versioned knowledge artifacts
- traceable signal references
- explicit approval records

Phase 4 knowledge bases:
- MUST be versioned
- MUST support replay from historical signals
- MAY evolve as new evidence accumulates

---

> **Invariant Summary:**
> Phase 4 learns patterns and remembers them. It does not judge, decide, or act.
