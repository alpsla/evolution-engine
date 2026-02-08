# Source Adapter Contract (Universal)

> **Architectural Contract**
>
> This document defines the **universal contract** between external truth sources and the Evolution Engine.
> It applies to all source families (version control, CI/CD, testing, dependencies, etc.)
> and all vendor‑specific adapters within those families.
>
> Adapters are mandatory. The Evolution Engine never interfaces with sources directly.
>
> **Family‑specific contracts** extend this contract with source‑specific semantics.
> See `docs/adapters/` for family contracts and vendor references.

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
- declare its source family and source type

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
 ├── source_family      : string      # e.g. 'version_control', 'ci', 'testing'
 ├── source_type         : string      # e.g. 'git', 'github_actions', 'junit'
 ├── source_id           : string      # unique instance identifier
 ├── ordering_mode       : 'causal' | 'temporal'
 ├── attestation_tier    : 'strong' | 'medium' | 'weak'
 └── iter_events()       → Iterable<SourceEvent>
```

---

## 4. Source Families

The Evolution Engine organizes truth sources into **families**.

Each family:
- has its own **Family Contract** (in `docs/adapters/<family>/`)
- defines the atomic event type for that source kind
- defines family‑specific payload requirements
- defines applicable Phase 2 metrics

Each family may have **multiple vendor adapters** (e.g., the CI family may have GitHub Actions, GitLab CI, and Jenkins adapters).

Currently defined families:

| # | Family | Directory | Atomic Event | Ordering | Trust | Reference Adapter | Status |
|---|--------|-----------|-------------|----------|-------|-------------------|--------|
| 1 | Version Control | `docs/adapters/git/` | Commit | Causal | Strong | Git | ✅ Implemented |
| 2 | CI / Build Pipeline | `docs/adapters/ci/` | Workflow run | Temporal | Medium | GitHub Actions | 🚧 Adapter ready |
| 3 | Test Execution | `docs/adapters/testing/` | Test suite run | Temporal | Medium | JUnit XML | 📋 Contract defined |
| 4 | Dependency Graph | `docs/adapters/dependency/` | Dependency snapshot | Temporal | Medium | npm / pip | 📋 Contract defined |
| 5 | Schema / API | `docs/adapters/schema/` | Schema version | Temporal/Causal | Medium | OpenAPI | 📋 Contract defined |
| 6 | Deployment / Release | `docs/adapters/deployment/` | Deployment event | Temporal | Medium | GitHub Releases | 📋 Contract defined |
| 7 | Configuration / IaC | `docs/adapters/config/` | Config snapshot | Temporal | Medium–Weak | Terraform | 📋 Contract defined |
| 8 | Security Scanning | `docs/adapters/security/` | Scan result | Temporal | Medium | Dependabot | 📋 Contract defined |

See `docs/adapters/README.md` for the full world map, cross‑source correlation diagram,
and implementation priority.

New families are added by:
1. Creating a family directory under `docs/adapters/`
2. Writing a family contract
3. Implementing at least one vendor adapter
4. Defining family‑specific Phase 2 metrics

---

## 5. Adapter Output: SourceEvent

Adapters emit `SourceEvent` objects which are then validated and persisted by the Phase 1 Engine.

Adapters:
- MAY normalize formats
- MAY canonicalize payloads
- MUST NOT enrich payloads with derived data

All interpretation happens strictly after Phase 1.

The `SourceEvent` shape is universal:

```json
{
  "source_family": "<family>",
  "source_type": "<vendor>",
  "source_id": "<instance>",
  "ordering_mode": "causal | temporal",
  "attestation": {
    "type": "<attestation-type>",
    "trust_tier": "strong | medium | weak",
    "verifier": "<verification-data>"
  },
  "predecessor_refs": ["<event_id>", ...],
  "payload": { "<family-specific content>" }
}
```

Family contracts define what `payload` must contain.

---

## 6. Trust Tiers

| Tier | Definition | Example |
|------|-----------|---------|
| **Strong** | Content‑addressable or cryptographically verifiable | Git commit hash |
| **Medium** | System‑assigned, externally verifiable, but not content‑addressed | CI run ID + commit SHA |
| **Weak** | Self‑reported, not independently verifiable | Log file timestamp |

Higher layers are trust‑tier‑aware. They do not treat all sources as equally reliable.

---

## 7. Adding a New Source

To add a new truth source to the Evolution Engine:

1. **Identify the family.** Does it belong to an existing family (version control, CI, testing, etc.) or is it a new family?
2. **If new family:** Write a Family Contract in `docs/adapters/<family>/`. Define atomic event, ordering, attestation, and required payload fields.
3. **Write the vendor adapter.** Implement the `SourceAdapter` interface for the specific vendor/tool.
4. **Define Phase 2 metrics.** What baselines and deviations make sense for this source?
5. **Validate.** Ingest through Phase 1, run Phase 2, verify determinism.

The system is designed so that **each new adapter immediately benefits from all existing layers** (Phase 2 baselines, Phase 3 explanations, Phase 4 pattern learning) without special‑case logic.

---

## 8. Architectural Invariant

> **No Evolution Engine may ingest data that does not originate from a Source Adapter.**

This invariant is non‑negotiable.
