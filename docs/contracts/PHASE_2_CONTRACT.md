# Phase 2 — Behavioral Baselines Contract

> **Normative Contract**
>
> This document defines the mandatory guarantees, boundaries, and invariants of Phase 2
> of the Evolution Engine. It is binding for all Phase 2 implementations, regardless of source.
>
> If code or design conflicts with this document, the code is wrong.

---

## 1. Purpose

Phase 2 exists to:

> **Derive behavioral baselines from immutable history and quantify deviation from those baselines.**

Phase 2 provides *context*, not *judgment*.

---

## 2. Inputs (Strict)

Phase 2 MAY read:
- Persisted Phase 1 `SourceEvent` objects

Phase 2 MUST NOT read:
- Source systems
- Adapters
- Runtime telemetry
- Other engines
- External services

This restriction is mandatory to guarantee determinism and replayability.

---

## 3. Outputs (Canonical)

Phase 2 MUST emit **structured deviation signals**.

Each signal MUST include:
- `engine_id`
- `source_type`
- `metric`
- `event_ref`
- `baseline` (statistical summary)
- `observed` value
- `deviation` (numeric, unit‑annotated)
- `confidence` metadata

Phase 2 outputs MUST:
- be deterministic
- be reproducible from Phase 1 history alone
- contain no natural language

---

## 4. Invariants

Phase 2 implementations MUST satisfy all of the following:

1. **Pure derivation** — Phase 2 is a pure function of Phase 1 events
2. **No mutation** — Phase 2 MUST NOT modify Phase 1 data
3. **Baseline versioning** — Baselines are immutable once computed
4. **Explicit confidence** — Cold‑start and low‑confidence states MUST be explicit
5. **Locality** — All baselines are local to a single engine

Violations are considered critical defects.

---

## 5. Confidence & Cold‑Start Rules

Phase 2 MUST track:
- sample count
- window size

Phase 2 MUST expose one of the following confidence states:
- `insufficient`
- `accumulating`
- `sufficient`

Phase 2 MUST NOT:
- suppress signals without declaring confidence
- imply safety when confidence is insufficient

---

## 6. Forbidden Behaviors

Phase 2 MUST NOT:
- assign risk labels
- score system health
- infer intent
- explain causes
- correlate multiple sources
- recommend actions
- depend on wall‑clock time

These behaviors belong to later phases.

---

## 7. Relationship to Other Documents

- Architecture Vision defines *why* Phase 2 exists
- This contract defines *what Phase 2 guarantees*
- Phase 2 Design defines *how Phase 2 is implemented*

This contract takes precedence over design documents.

---

> **Invariant Summary:**
> Phase 2 quantifies difference. It never decides meaning.
