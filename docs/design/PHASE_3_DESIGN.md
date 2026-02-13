# Phase 3 — Explanation Layer Design

> **Design Reference**
>
> This document defines the design of **Phase 3 (Explanation Layer)** for the Evolution Engine.
> It explains *how* explanations are produced while strictly conforming to `PHASE_3_CONTRACT.md`.
>
> Phase 3 is about **trustworthy communication**, not intelligence or automation.

---

## 1. Design Goals

Phase 3 is designed to:

1. Make Phase 2 signals understandable to humans
2. Preserve numerical truth and uncertainty
3. Avoid judgment, recommendations, or enforcement
4. Remain auditable and reproducible
5. Scale across different truth sources without redesign

The primary success criterion is:

> **A human understands what changed and how it compares to history, without being told what to do.**

---

## 2. Unit of Explanation

### Decision

**One explanation per Phase 2 signal.**

### Rationale
- Preserves traceability (1 signal → 1 explanation)
- Avoids hidden aggregation or weighting
- Keeps correlation as a future concern
- Simplifies auditing and debugging

Grouping (e.g., multiple explanations per commit) is treated as a **presentation concern**, not a Phase 3 responsibility.

---

## 3. Explanation Pipeline

The explanation process follows a strict, linear pipeline:

```
Phase 2 Signal
     ↓
Context Assembly
     ↓
Explanation Rendering
     ↓
Explanation Object
```

### 3.1 Context Assembly

Inputs:
- Phase 2 signal (canonical)
- Referenced Phase 1 event(s)
- Baseline metadata

Outputs:
- Fully populated explanation context
- No new computation
- No derived metrics

This step is purely data gathering.

---

### 3.2 Explanation Rendering

Rendering transforms structured context into human‑readable form.

Two rendering modes are supported:

#### Mode A — Template‑Based (Deterministic)

- Uses predefined templates per metric
- Fully deterministic
- Required for all deployments

Example template:

> "This change touched **{observed} files**. Over the last {window_size} changes, similar changes typically touched **{baseline_mean} ± {baseline_stddev} files**."

#### Mode B — Template + LLM Paraphrase (Optional)

- LLM receives:
  - structured context
  - rendered template
- LLM may only paraphrase or improve readability
- LLM must not add facts, intent, or recommendations

If LLM output deviates from the template’s facts, it is rejected.

---

## 4. Explanation Types (By Metric)

Each Phase 2 metric has a corresponding explanation pattern.

### 4.1 Files Touched

Focus:
- breadth of change

Example explanation:
> "This change modified **14 files**. Recent changes typically modified **3–5 files**, making this change broader than usual."

---

### 4.2 Dispersion

Focus:
- structural spread across directories

Example explanation:
> "Files in this change were spread across **5 directories**, whereas recent changes were usually concentrated in **1–2 directories**."

---

### 4.3 Change Locality

Focus:
- focus vs exploration

Example explanation:
> "Most files modified in this change were also modified recently, indicating focused work rather than exploratory changes."

---

### 4.4 Co‑Change Novelty

Focus:
- new or unusual file relationships

Example explanation:
> "This change modified file combinations that rarely changed together in the past, introducing new structural coupling."

---

## 5. Confidence & Uncertainty Messaging

Confidence handling is **not optional**.

### Rules
- Phase 2 confidence status is always surfaced
- Low confidence changes phrasing, not suppression

Examples:

- **Accumulating confidence:**
  > "This comparison is based on limited history and may change as more data becomes available."

- **Sufficient confidence:**
  > "This comparison is based on established historical patterns."

---

## 6. Tone & Language Guidelines

Phase 3 explanations MUST:
- be neutral
- be comparative
- be factual

Phase 3 explanations MUST NOT:
- sound alarming
- imply correctness or incorrectness
- recommend actions

Forbidden language examples:
- "risk"
- "problematic"
- "should"
- "needs review"

---

## 7. Output Surfaces

### Primary
- Structured JSON (API‑first)

### Secondary
- CLI text rendering (template‑based)

UI and notifications are deferred to later phases.

---

## 8. Determinism & Auditability

Phase 3 MUST support:
- deterministic rendering (Mode A)
- reproducible explanations from stored data
- explanation IDs derived from content

Every explanation must be traceable to:
- one Phase 2 signal
- referenced Phase 1 events

---

## 9. Non‑Goals (Reaffirmed)

Phase 3 does **not**:
- correlate multiple signals
- aggregate explanations
- prioritize issues
- suggest actions
- trigger alerts

These concerns belong to later phases.

---

## 10. Phase 3 → Phase 3.1 Evolution

### Phase 3 — Deterministic Explanation (Baseline)

**Purpose**  
Establish trust, clarity, and auditability by translating Phase 2 signals into human‑readable explanations **without adaptive behavior**.

**Characteristics**
- One explanation per Phase 2 signal
- Template‑based, deterministic rendering
- Fixed phrasing per metric
- Explicit surfacing of confidence and uncertainty
- No aggregation, prioritization, or narrative synthesis
- LLM optional only as cosmetic paraphrase

**Role in the system**
- Serves as the truth anchor for all future explanation layers
- Makes Phase 2 semantics visible without interpretation
- Exposes repetition, ambiguity, or explanatory gaps

**Success condition**
- Users understand what changed and how it compares to history
- Explanations are reproducible and auditable
- System behavior is predictable and non‑persuasive

---

### Phase 3.1 — Grounded Narrative Explanation (Evolution)

**Purpose**  
Increase explanatory usefulness and human comprehension **without weakening Phase 3 guarantees**.

**What changes**
- LLM becomes the primary renderer for explanations
- Explanations adapt:
  - verbosity to deviation magnitude
  - framing to confidence state
  - historical context when explicitly provided
- Narrative coherence improves across repeated explanations

**What does not change**
- One explanation per signal
- No judgment, recommendation, or prioritization
- No new facts or inferred intent
- No correlation across signals or sources
- Deterministic template path remains available

**New architectural element**
- **Validation Gate**
  - Verifies numeric fidelity
  - Verifies citation correctness
  - Detects forbidden language
  - Falls back to deterministic templates on violation

**Promotion criteria**
Phase 3 may evolve into Phase 3.1 only after:
- Deterministic Phase 3 explanations are deployed and observed
- Repetition or explanation fatigue is confirmed
- Users request richer context or historical framing
- Validation gates are proven reliable

---

## 11. Definition of Done

Phase 3 design is considered complete when:
- every Phase 2 metric has an explanation pattern
- confidence handling is specified
- deterministic rendering path exists
- Phase 3 → 3.1 transition criteria are documented
- contract constraints are fully respected

Implementation may begin only after this point.

---

> **Summary:**  
> Phase 3 explains reliably. Phase 3.1 explains fluently — without turning explanation into judgment.
