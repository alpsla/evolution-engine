# Phase 1 — Evolution Indexer Design

This document defines the **Phase 1 execution plan** for the Evolution Engine, covering:
- storage format
- local data model
- CLI surface

Phase 1 goal: **observe and remember change correctly**, without judgment.

---

## 1. Design Constraints (Non‑Negotiable)

Phase 1 MUST:
- be git‑native
- be deterministic and replayable
- work on any repository
- avoid language‑specific parsing
- avoid premature schema rigidity

Phase 1 MUST NOT:
- score health
- emit alerts
- infer semantics
- require cloud infrastructure

---

## 2. Storage Strategy (Local‑First)

### Guiding Principle

> **History is immutable; interpretation is derived.**

All Phase 1 data is stored locally in append‑only or versioned formats.

---

## 3. Directory Layout (per analyzed repo)

```
.evolution/
├── metadata.json            # repo identity, engine version
├── events/
│   ├── 00000001.json        # Change Event records (append‑only)
│   ├── 00000002.json
│   └── ...
├── snapshots/
│   ├── structure_0001.json  # optional future use
│   └── ...
├── indices/
│   └── commit_map.json      # commit hash → event id
└── logs/
    └── ingestion.log
```

Notes:
- `.evolution/` lives **inside the target repo**, not globally
- events are **ordered and append‑only**
- snapshots folder is reserved but unused in v0

---

## 4. Change Event — Canonical Schema (v0)

Each commit produces exactly **one Change Event**.

### ChangeEvent (JSON)

```json
{
  "event_id": "evt_00000042",
  "commit_hash": "abc123...",
  "parent_hashes": ["def456..."],
  "timestamp": "2026-02-05T12:34:56Z",
  "author": {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "class": "human | ai | hybrid | unknown"
  },
  "metrics": {
    "files_touched": 7,
    "modules_touched": 3,
    "lines_added": 120,
    "lines_removed": 45,
    "churn": 165,
    "net_delta": 75,
    "dispersion": 0.62,
    "scope_ratio": 0.08
  },
  "raw_diff_ref": "diffs/abc123.patch"
}
```

### Notes
- All metrics are **dimensionless or counts**
- No semantic interpretation
- `author.class` is best‑effort, nullable

---

## 5. Metric Computation Rules (Phase 1)

### Source of Truth

All metrics derived from:
- `git log`
- `git show --numstat`
- file paths

### Definitions
- **files_touched**: count of unique files in diff
- **modules_touched**: count of top‑level directories touched
- **dispersion**: Shannon entropy of changed lines across modules
- **scope_ratio**: files_touched / total_repo_files

No heuristics beyond this in Phase 1.

---

## 6. Determinism & Replay

Rules:
- same repo + same commit order → identical event log
- event_id derived from monotonic counter, not hash
- commit hash stored for traceability

Rebuild strategy:
- delete `.evolution/`
- re‑ingest history
- diff results byte‑for‑byte

---

## 7. CLI Surface (Phase 1)

### Core Commands

```
evolution init
```
- initializes `.evolution/` directory
- writes metadata.json

```
evolution ingest
```
- walks git history (oldest → newest)
- emits Change Events
- idempotent (skips already indexed commits)

```
evolution events [--limit N]
```
- prints recent Change Events
- human‑readable summary

```
evolution inspect <event_id>
```
- shows full JSON for a single Change Event

```
evolution stats
```
- prints aggregate stats (counts only, no judgment)

---

## 8. Phase 1 Definition of Done

Phase 1 is complete when:
- engine can ingest any git repo without error
- Change Event log is deterministic
- metrics are stable across re‑runs
- CLI inspection works
- no health or anomaly logic exists

---

## 9. Explicitly Deferred

- baselines
- deviation detection
- explanations
- AST parsing
- embeddings
- cloud sync

Those begin in Phase 2.

---

## 10. Phase 1 Success Metric

> A human can inspect the evolution of a repository **without reading code**, using only Change Events.

If this holds, Phase 1 succeeded.
