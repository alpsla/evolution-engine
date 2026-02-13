# Phase 3 — Explanation Layer Contract

> **Normative Contract**
>
> This document defines the guarantees, boundaries, and invariants of **Phase 3 (Explanation Layer)** of the Evolution Engine.
> It is binding for all Phase 3 implementations. If implementation or design conflicts with this document, the implementation is incorrect.

---

## 1. Purpose

Phase 3 exists to:

> **Translate Phase 2 deviation signals into human‑understandable explanations without adding judgment, enforcement, or new facts.**

Phase 3 explains *what changed and how it compares to history*, not *what should be done*.

---

## 2. Inputs (Strict)

Phase 3 MAY read:
- Phase 2 deviation signals that conform to the canonical signal shape
- Phase 1 event references *only as cited evidence* (read‑only)
- Phase 2 baseline metadata referenced by signals

Phase 3 MUST NOT read:
- Source systems
- Adapters
- Runtime telemetry
- Other engines’ raw data
- External services (unless explicitly configured as a pure rendering aid)

Phase 3 MUST NOT modify any Phase 1 or Phase 2 artifacts.

---

## 3. Outputs (Canonical)

Phase 3 MUST emit **Explanation Objects**.

Each Explanation Object MUST:
- reference exactly one Phase 2 signal
- include cited historical context
- preserve numeric values from Phase 2 without alteration
- include explicit uncertainty annotations

Phase 3 outputs MAY be:
- structured JSON
- human‑readable text generated from structured templates
- LLM‑generated text *only if it is grounded entirely in the provided signal and citations*

Natural language is permitted **only** in Phase 3.

---

## 4. Explanation Object Shape (Required)

```json
{
  "explanation_id": "<content-addressable-id>",
  "engine_id": "git",
  "source_type": "git",
  "signal_ref": "<phase2-signal-id>",
  "summary": "<human-readable explanation>",
  "details": {
    "metric": "files_touched",
    "observed": 9,
    "baseline": {
      "mean": 3.4,
      "stddev": 1.2
    },
    "deviation": {
      "measure": 4.7,
      "unit": "stddev_from_mean"
    }
  },
  "historical_context": {
    "window": {
      "type": "rolling",
      "size": 50
    },
    "examples": [
      "<event_id>",
      "<event_id>"
    ]
  },
  "confidence": {
    "status": "accumulating",
    "sample_count": 12
  },
  "limitations": [
    "Baseline still accumulating",
    "Merge commits excluded"
  ]
}
```

Fields may be omitted only when logically inapplicable.

---

## 5. Invariants

Phase 3 implementations MUST satisfy all of the following:

1. **No new facts** — Phase 3 must not derive metrics or modify numeric values
2. **No judgment** — No labels such as "good", "bad", "risky", "safe"
3. **No recommendations** — Phase 3 must not suggest actions
4. **Evidence‑first** — Every claim must be traceable to a Phase 2 signal or Phase 1 event
5. **Deterministic option** — A non‑LLM, template‑based explanation path must exist

Violations are considered critical defects.

---

## 6. Uncertainty & Confidence Rules

Phase 3 MUST:
- surface Phase 2 confidence status verbatim
- explain uncertainty in plain language when confidence is not sufficient
- avoid masking low confidence with fluent language

Phase 3 MUST NOT:
- imply certainty where none exists
- suppress explanations due to low confidence

---

## 7. Forbidden Behaviors

Phase 3 MUST NOT:
- perform correlation across sources (Phase 4)
- aggregate multiple signals into a single explanation
- apply thresholds or escalation logic
- trigger alerts or notifications
- write back to any earlier phase

---

## 8. LLM Usage (Optional and Constrained)

If LLMs are used in Phase 3:

- They MUST be provided only:
  - the Phase 2 signal
  - referenced Phase 1 event metadata
  - an explicit explanation template or instruction
- They MUST NOT:
  - infer intent
  - add new facts
  - generalize beyond the provided data

A deterministic, non‑LLM explanation path MUST remain available.

---

## 9. Relationship to Other Documents

- Architecture Vision defines *why* explanations exist
- Phase 2 Contract defines *what* is explained
- This contract defines *how explanation is constrained*
- Phase 3 Design will define *how explanations are produced*

This contract takes precedence over Phase 3 design documents.

---

> **Invariant Summary:**
> Phase 3 explains deviations without judging them. Trust is preserved by grounding every explanation in evidence and uncertainty.
