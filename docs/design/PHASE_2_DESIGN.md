# Phase 2 — Behavioral Baselines & Deviation Signals

> **Design Reference**
>
> This document defines Phase 2 of the Evolution Engine.
> Phase 2 derives *behavioral context* from immutable Phase 1 events.
>
> It is the first layer where computation occurs — but still **no interpretation, no judgment, no explanation**.

---

## 1. Purpose of Phase 2

Phase 2 exists to answer one question:

> **“What is normal behavior for this system, based on its own history?”**

It does so by:
- deriving structural metrics from Phase 1 events
- learning statistical baselines over time
- emitting *raw deviation measures* when new observations diverge

Phase 2 **does not decide if something is good or bad**.
It only quantifies how different something is from learned norms.

---

## 2. Inputs & Outputs

### 2.1 Inputs (Strict)

Phase 2 reads **only**:
- persisted Phase 1 `SourceEvent` objects

Phase 2 must not:
- access source systems
- access adapters
- access other engines
- access runtime data

This guarantees determinism and replayability.

---

### 2.2 Outputs

Phase 2 produces:
- **Baselines** — summaries of historical behavior
- **Deviation Signals** — raw quantitative deltas

All outputs are:
- deterministic
- reproducible
- source‑agnostic in shape

No natural language appears in Phase 2 output.

---

## 3. Core Concepts

### 3.1 Metric

A **metric** is a dimensionless, structural quantity derived from a single Phase 1 event.

Examples:
- number of files touched
- number of directories touched
- entropy of file changes across directories

Metrics must be:
- numeric or structural
- derivable solely from Phase 1 payloads
- independent of semantics

---

### 3.2 Baseline

A **baseline** is a statistical summary of metric values over a window of events.

Baseline properties:
- local to a single engine
- windowed (rolling or cumulative)
- versioned (never mutated)

Common baseline statistics:
- mean
- standard deviation
- percentiles
- distributions

---

### 3.3 Deviation Measure

A **deviation measure** quantifies how far an observed metric deviates from a baseline.

Examples:
- z‑score (standard deviations from mean)
- percentile distance
- set distance (e.g., Jaccard distance)

Deviation measures:
- are numeric
- have explicit units
- carry no qualitative labels

---

### 3.4 Confidence & Cold‑Start

Baselines require sufficient history.

Phase 2 must explicitly track:
- sample count
- window size
- confidence status

Confidence statuses:
- `insufficient` — too little data, no deviation emitted
- `accumulating` — baseline forming, deviation emitted but flagged
- `sufficient` — baseline stable

Absence of deviation does **not** imply normality unless confidence is sufficient.

---

## 4. Git Phase 2 — Reference Metrics

Git is the reference Phase 2 implementation.

All other sources must meet or exceed its rigor.

---

### 4.1 Files Touched per Commit

**Definition:**
Number of unique file paths modified in a commit.

**Purpose:**
Distinguishes narrow changes from broad changes.

**Baseline:**
- rolling mean
- rolling standard deviation

---

### 4.2 Dispersion (Change Breadth)

**Definition:**
Entropy of changed files across directory hierarchy.

**Purpose:**
Detects wide, system‑spanning changes vs localized edits.

**Baseline:**
- rolling entropy distribution

---

### 4.3 Co‑Change Matrix

**Definition:**
Frequency with which files change together across commits.

**Purpose:**
Reveals structural coupling and emergent modules.

**Baseline:**
- normalized co‑occurrence frequencies

---

### 4.4 Change Locality Trend

**Definition:**
Likelihood that recently modified files are modified again in subsequent commits.

**Purpose:**
Separates iterative refinement from exploration or churn.

---

## 5. Output Signal Shape (Canonical)

Every deviation emitted by Phase 2 must conform to this shape:

```json
{
  "engine_id": "<engine-id>",
  "source_type": "git",
  "metric": "files_touched",
  "window": {
    "type": "rolling",
    "size": 50
  },
  "baseline": {
    "mean": 3.4,
    "stddev": 1.2
  },
  "observed": 9,
  "deviation": {
    "measure": 4.7,
    "unit": "stddev_from_mean"
  },
  "confidence": {
    "sample_count": 50,
    "status": "sufficient"
  },
  "event_ref": "<event_id>"
}
```

Fields may be omitted only when logically inapplicable.

---

## 6. Explicit Non‑Goals

Phase 2 does **not**:
- assign risk labels
- score health
- explain causes
- correlate sources
- recommend actions

These belong to later phases.

---

## 7. Determinism & Replay Guarantees

Phase 2 must satisfy:
- same Phase 1 events → same Phase 2 outputs
- deletion + recomputation yields identical results
- no dependence on wall‑clock time

Violations are considered critical bugs.

---

## 8. Phase 2 Definition of Done

Phase 2 is complete when:
- baselines stabilize on real repos
- deviations respond to injected anomalies
- cold‑start behavior is explicit and correct
- outputs are fully deterministic

Only then may Phase 3 begin.

---

> **Summary:**
> Phase 2 turns immutable history into behavioral memory.
> It quantifies difference — it does not judge it.
