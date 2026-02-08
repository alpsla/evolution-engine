# Phase 4 — Pattern Learning & Knowledge Layer Design

> **Design Reference**
>
> This document defines the design of **Phase 4 (Pattern Learning & Knowledge Layer)**.
> It explains *how* patterns are discovered, interpreted, stored, and promoted while
> strictly conforming to `PHASE_4_CONTRACT.md`.

---

## 1. Design Goals

Phase 4 is designed to:

1. Discover structural patterns across Phase 2 signals algorithmically
2. Enrich discovered patterns with semantic descriptions via LLM
3. Store patterns in a queryable Knowledge Base
4. Accumulate evidence and promote patterns through confidence tiers
5. Provide instant pattern recognition for known signal combinations

The primary success criterion is:

> **When the system sees a signal combination it has seen before, it recognizes it instantly. When it sees something new, it learns from it.**

---

## 2. Architecture

```
Phase 2 Signals ──────────────────────────────────┐
                                                    │
Phase 3 Explanations ─────────────────────────┐   │
                                                │   │
                                                ▼   ▼
                                    ┌─────────────────────┐
                                    │    Signal Router     │
                                    │ (fingerprint + route)│
                                    └──────────┬──────────┘
                                               │
                              ┌────────────────┼────────────────┐
                              ▼                                  ▼
                    ┌──────────────────┐              ┌──────────────────┐
                    │   Phase 4a       │              │   Phase 4b       │
                    │   Pattern Matcher│              │   Interpreter    │
                    │   (Algorithm)    │              │   (LLM)         │
                    └────────┬─────────┘              └────────┬─────────┘
                             │                                  │
                             └──────────┬───────────────────────┘
                                        ▼
                              ┌──────────────────┐
                              │  Knowledge Base   │
                              │  (SQLite / PG)    │
                              └──────────────────┘
```

---

## 3. Signal Fingerprinting

### 3.1 Purpose

Convert a set of concurrent Phase 2 signals into a queryable key that enables
fast Knowledge Base lookup.

### 3.2 Fingerprint Construction

A fingerprint is built from the **set of active deviations** within a time window:

```
fingerprint = hash(sorted([
    (signal.engine_id, signal.metric, direction(signal.deviation)),
    (signal.engine_id, signal.metric, direction(signal.deviation)),
    ...
]))
```

Where:
- `engine_id` identifies the source family
- `metric` identifies what was measured
- `direction` is one of: `increased`, `decreased`, `unchanged`

### 3.3 Example

If the system observes:
- `schema.endpoint_count` ↑ (increased)
- `testing.failure_rate` ↑ (increased)
- `dependency.dependency_count` ↑ (increased)

The fingerprint captures: "schema growth + test failures + dependency growth"
without encoding magnitudes. This allows fuzzy matching across different
severity levels.

### 3.4 Deviation Direction Threshold

A signal's direction is determined by:
- `increased`: deviation > +1.0 stddev
- `decreased`: deviation < -1.0 stddev
- `unchanged`: within ±1.0 stddev

This threshold is configurable via the `direction_threshold` parameter.

---

## 4. Phase 4a — Algorithmic Pattern Discovery

### 4.1 KB Lookup (Fast Path)

For every new signal batch:

1. Compute the signal fingerprint
2. Query the KB: `SELECT * FROM patterns WHERE fingerprint = ?`
3. If exact match → return the Knowledge Artifact (recognition)
4. If fuzzy match (similarity > threshold) → return candidate for review
5. If no match → proceed to discovery

### 4.2 Co‑Occurrence Discovery

When no existing pattern matches, Phase 4a analyzes the signal window:

1. Collect all signals within the current time window
2. Identify signals that deviate in the same direction simultaneously
3. Compute pairwise correlation across the window history
4. If correlation ≥ `min_correlation` across ≥ `min_support` observations:
   → Create a new Pattern Object (candidate)

### 4.3 Temporal Sequence Detection

Beyond co‑occurrence, Phase 4a detects ordered sequences:

- "Signal A precedes Signal B by 1–3 events with 0.8 correlation"
- Example: dependency_count spike → vulnerability_count spike (within 2 scans)

### 4.4 Correlation Metrics

| Metric | Purpose |
|--------|---------|
| Pearson correlation | Linear co‑occurrence strength |
| Temporal lag correlation | Sequence detection (A before B) |
| Jaccard similarity | Signal set overlap across windows |

---

## 5. Phase 4b — Semantic Pattern Interpretation

### 5.1 When 4b Is Invoked

Phase 4b is called ONLY when:
- Phase 4a discovers a new candidate pattern
- The candidate lacks a semantic description
- The candidate has sufficient Phase 3 explanations available

### 5.2 LLM Prompt Design

Phase 4b provides the LLM with:

1. The statistical finding (from 4a)
2. Phase 3 explanations for each signal in the pattern
3. A strict instruction prompt

```
You are analyzing a set of co-occurring software evolution signals.

Statistical finding: [Phase 4a output]

Signal explanations:
- [Phase 3 explanation for signal 1]
- [Phase 3 explanation for signal 2]
- [Phase 3 explanation for signal 3]

Describe the structural theme these signals represent in ONE sentence.
Do not add judgment, recommendations, or speculation.
Do not use words like "risk", "danger", "should", or "needs".
Describe only what is structurally happening.
```

### 5.3 Validation Gate (4b)

Phase 4b output is validated before storage:

- **No judgment language** (same forbidden terms as Phase 3.1)
- **No recommendations** (no "should", "needs", "consider")
- **Factual grounding** (description must reference signals that exist)
- **Length constraint** (1–3 sentences maximum)

If validation fails, the pattern is stored with `semantic: null` and flagged for human review.

---

## 6. Knowledge Base Schema

### 6.1 Tables

```sql
-- Pattern candidates
CREATE TABLE patterns (
    pattern_id      TEXT PRIMARY KEY,
    fingerprint     TEXT NOT NULL,
    scope           TEXT NOT NULL,  -- 'local' or 'global'
    discovery_method TEXT NOT NULL, -- 'statistical' or 'semantic'
    pattern_type    TEXT NOT NULL,
    sources         JSON NOT NULL,
    metrics         JSON NOT NULL,
    description_statistical TEXT,
    description_semantic    TEXT,
    correlation_strength    REAL,
    occurrence_count        INTEGER DEFAULT 1,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    confidence_tier TEXT NOT NULL,  -- 'statistical', 'speculative', 'confirmed'
    confidence_status TEXT NOT NULL, -- 'emerging', 'sufficient', 'hypothesis'
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Approved knowledge
CREATE TABLE knowledge (
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
    approval_method TEXT NOT NULL,  -- 'automatic' or 'human'
    approval_timestamp TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

-- Signal-to-pattern links (evidence trail)
CREATE TABLE pattern_signals (
    pattern_id  TEXT REFERENCES patterns(pattern_id),
    signal_ref  TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (pattern_id, signal_ref)
);

-- Audit log
CREATE TABLE pattern_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id  TEXT NOT NULL,
    action      TEXT NOT NULL,  -- 'created', 'updated', 'promoted', 'expired'
    details     JSON,
    timestamp   TEXT NOT NULL
);
```

### 6.2 Indexes

```sql
CREATE INDEX idx_patterns_fingerprint ON patterns(fingerprint);
CREATE INDEX idx_patterns_scope ON patterns(scope);
CREATE INDEX idx_knowledge_fingerprint ON knowledge(fingerprint);
CREATE INDEX idx_knowledge_scope ON knowledge(scope);
```

---

## 7. Pattern Lifecycle

```
             ┌──────────┐
             │ Discovered│ (Phase 4a finds correlation)
             └─────┬─────┘
                   │
                   ▼
             ┌──────────┐
             │ Enriched  │ (Phase 4b adds semantic description)
             └─────┬─────┘
                   │
                   ▼
             ┌──────────┐
             │Accumulating│ (each new observation increments support)
             └─────┬─────┘
                   │  occurrence_count >= promotion_threshold?
                   ▼
             ┌──────────┐
             │ Promoted  │ (becomes Knowledge Artifact)
             └─────┬─────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
    ┌──────────┐     ┌──────────┐
    │  Active   │     │ Decaying  │ (not seen in decay_window)
    │Knowledge  │     │           │
    └──────────┘     └─────┬─────┘
                           │ fully decayed?
                           ▼
                     ┌──────────┐
                     │  Expired  │ (archived, not deleted)
                     └──────────┘
```

---

## 8. Three Moments in the System's Life

### Moment 1: First Encounter (Learning)
- New signal combination → no KB match
- Phase 4a discovers correlation → creates candidate
- Phase 4b enriches with description
- Stored as Pattern Object (confidence: emerging)

### Moment 2: Reinforcement (Accumulating)
- Same fingerprint appears again
- Phase 4a matches → increments support count
- No LLM call needed (description already exists)
- Confidence grows toward promotion

### Moment 3: Recognition (Educated)
- Familiar fingerprint arrives
- Phase 4a matches → retrieves Knowledge Artifact instantly
- No discovery, no LLM — pure lookup
- Phase 5 includes historical context in advisory

---

## 9. Definition of Done

Phase 4 design is considered complete when:
- Signal fingerprinting strategy is specified
- KB schema is defined
- Phase 4a discovery algorithms are identified
- Phase 4b LLM interaction is bounded
- Pattern lifecycle is documented
- Cascade rule is explicit

Implementation may begin only after this point.

---

> **Summary:**
> Phase 4 discovers with math, interprets with language, and remembers with a database.
> Each new observation either confirms what it knows or teaches it something new.
