# Evolution Engine — Architecture (v0)

This document describes the **architectural model** of the Evolution Engine.
It is intentionally short and opinionated. It explains *how the system thinks*, not how it is implemented.

---

## 1. Architectural Goal

> **Preserve structural truth over time while allowing interpretation, escalation, and integration to evolve.**

The Evolution Engine is designed as an **application / service**, not just an engine. It exists to:
- observe structural change deterministically
- remember it immutably
- derive behavioral context locally
- surface uncertainty and escalation points
- integrate (optionally) with external systems without losing authority

---

## 2. Layered Architecture (Epistemic Order)

The system is composed of **layers with strict authority ordering**.
Higher layers may read lower layers, but never modify or override them.

```
┌───────────────────────────────────────────┐
│ Phase 4–5: Advisory / Speculative Layers │
├───────────────────────────────────────────┤
│ Phase 3: Explanation / Narrative Layer   │
├───────────────────────────────────────────┤
│ Phase 2: Behavioral / Baseline Layer     │
├───────────────────────────────────────────┤
│ Phase 1: Reality / Observation Layer     │
└───────────────────────────────────────────┘
```

### Authority Rules
- Phase 1 defines **what happened** (absolute truth)
- Phase 2 defines **what is normal** (statistical context)
- Phase 3 defines **how we explain it** (human narrative)
- Phase 4–5 define **what we might do** (optional advice)

No numeric blending of layers is allowed.

---

## 3. Phase 1 — Reality Layer (Core)

### Responsibility
- Observe git history
- Extract atomic facts
- Store immutable Change Events

### Guarantees
- Deterministic output
- Replayable history
- Platform‑agnostic (GitHub / GitLab / bare git)

### Output
- Append‑only Change Event log
- No judgments
- No scores
- No interpretation

---

## 4. Phase 2 — Behavioral Layer (Derived)

### Responsibility
- Learn co‑change relationships
- Establish local baselines
- Compute deviation statistics

### Constraints
- Cannot modify Phase 1 data
- Can be recomputed at any time
- Windows and models are replaceable

---

## 5. Phase 3 — Explanation Layer

### Responsibility
- Translate deviations into human‑readable explanations
- Reference historical facts explicitly
- Surface uncertainty

### Constraints
- Cannot suppress or alter signals
- Cannot rewrite history

---

## 6. Phase 4–5 — Advisory Layers (Future)

### Responsibility
- Forecast
- Recommend
- Assist humans or AIs

### Constraints
- Always optional
- Always defeatable
- Never authoritative

---

## 7. Data Flow (One‑Way)

```
Git Repo
   │
   ▼
Phase 1: Change Events (immutable)
   │
   ▼
Phase 2: Baselines / Patterns (derived)
   │
   ▼
Phase 3: Explanations (textual)
   │
   ▼
Phase 4+: Advice (optional)
```

No backward writes are allowed.

---

## 8. Failure Model (Expected and Safe)

The system assumes:
- higher layers will be wrong sometimes
- models will drift
- explanations will age poorly

This is acceptable because:
- Phase 1 facts never change
- Phase 2–5 can be deleted and recomputed

---

## 9. Core Invariant

> **History is sacred. Interpretation is disposable.**

This invariant must never be violated.

---

## 10. Non‑Goals (v0)

- Real‑time enforcement
- Blocking CI
- Global health scores
- Cross‑repo judgment
- UI dashboards

---

## 11. Summary

The Evolution Engine is not an analyzer or a judge.
It is a **memory system with disciplined interpretation layers**.

If this architecture is respected, the system can grow indefinitely without losing trust.
