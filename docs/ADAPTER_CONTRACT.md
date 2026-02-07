# Source Adapter Contract

> **Architectural Contract**
> 
> This document defines the contract between external truth sources and the Evolution Engine.
> Adapters are mandatory. The Evolution Engine never interfaces with sources directly.

---

## 1. Purpose

A **Source Adapter** isolates source‑specific complexity from the Evolution Engine.

Its purpose is to:
- connect to an external system of record
- extract atomic, trusted facts
- normalize them into `SourceEvent` objects
- attach verifiable attestation
- declare scope and ordering semantics

Adapters are intentionally **impure**. That impurity must never leak into the engine.

---

## 2. Responsibilities of an Adapter

A Source Adapter **MUST**:
- bind to exactly one concrete source instance
- emit deterministic events for the same source state
- attach verifiable attestation
- declare ordering semantics (causal or temporal)
- define the atomicity of events

A Source Adapter **MUST NOT**:
- compute metrics or aggregates
- infer intent or semantics
- apply baselines or thresholds
- correlate with other sources
- mutate historical events

---

## 3. Abstract Adapter Interface

Conceptual interface (language‑agnostic):

```text
SourceAdapter
 ├── source_type        : string
 ├── source_id          : string
 ├── ordering_mode      : 'causal' | 'temporal'
 ├── attestation_tier   : 'strong' | 'medium' | 'weak'
 └── iter_events()      → Iterable<SourceEvent>
```

---

## 4. Adapter Output: SourceEvent

Adapters emit `SourceEvent` objects which are then validated and persisted by the Phase 1 Engine.

Adapters:
- MAY normalize formats
- MAY canonicalize payloads
- MUST NOT enrich payloads with derived data

All interpretation happens strictly after Phase 1.

---

## 5. Git Adapter (Reference)

The Git adapter is the reference implementation.

- Source: git repository
- Atomic event: commit object
- Ordering: causal (commit graph)
- Attestation: commit hash (content‑addressable)
- Trust tier: strong

All future adapters must meet or exceed this bar.

---

## 6. Architectural Invariant

> **No Evolution Engine may ingest data that does not originate from a Source Adapter.**

This invariant is non‑negotiable.
