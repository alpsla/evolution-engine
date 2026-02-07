# Evolution Engine — Implementation Plan

> **Authoritative Execution Roadmap**
>
> This document translates the Architecture Vision and research findings into an explicit, ordered implementation plan.
> It answers *what we build*, *in what order*, and *why that order exists*.
>
> The plan is intentionally conservative: each step validates an architectural assumption before expanding scope.

---

## 0. Guiding Rules for This Plan

1. **Vision precedes contracts** — architectural intent is fixed before guarantees.
2. **Contracts precede design** — no phase is implemented without a formal contract.
3. **Adapters precede engines** — no source may enter Phase 1 without an adapter.
4. **Phase purity is enforced** — Phase 1 observes, Phase 2 baselines, Phase 3 explains.
5. **Correlation requires plurality** — no correlation work begins until at least two engines produce Phase 2 signals.
6. **Research informs priority, not parallelism** — we do not build everything at once.

---

## 1. Completed Foundations ✅

### Architecture & Authority
- ✅ Architecture Vision (Constitution)
- ✅ Documentation authority model (`docs/README.md`)

### Contracts
- ✅ Source Adapter Contract
- ✅ Phase 2 Behavioral Baselines Contract

### Engine Infrastructure
- ✅ Phase 1 Engine (source‑agnostic)
- ✅ Git Source Adapter (reference)
- ✅ Phase 1 Git ingestion (adapter‑driven, contract‑clean)

These elements are considered **stable**. Changes require explicit architectural review.

---

## 2. Phase 2 — Behavioral Baselines (Git Reference Engine)

> This phase follows the **Phase 2 Contract** and **Phase 2 Design** documents.

### 2.1 Phase 2 Contract Definition ✅
- ✅ Inputs, outputs, invariants locked
- ✅ Confidence and cold‑start rules defined
- ✅ Forbidden behaviors explicitly stated

### 2.2 Phase 2 Design ✅
- ✅ Metrics defined (files touched, dispersion, co‑change, locality)
- ✅ Canonical signal shape defined
- ✅ Determinism and replay guarantees specified

### 2.3 Phase 2 Implementation ✅
- ✅ Phase 2 engine skeleton
- ✅ Git reference metrics (files touched, dispersion)
- ✅ Co‑change matrix
- ✅ Change locality trend

### 2.4 Phase 2 Testing ✅
- ✅ Determinism tests (toy repo)
- ✅ Baseline stability validation
- ✅ Sensitivity validation
- ✅ Cold‑start confidence behavior validated

---

## 3. Second Truth Source — Validation Adapter + Engine

> Purpose: validate that the abstraction holds beyond Git and unlock Phase 4.

Only **one** additional source is implemented at this stage.

### Status 🚧 (Next Priority)
- 🚧 Adapter design
- 🚧 Phase 1 ingestion
- 🚧 Phase 2 metrics

### Candidate Priority (from research)
1. **CI / Build Pipeline** ✅ (next)
2. Schema / API Evolution

### 3.1 Adapter Development
- Define atomic CI event (build/run/test)
- Define attestation strength
- Define ordering mode

### 3.2 Phase 1 Integration
- Ingest CI events via existing Phase 1 Engine
- Verify determinism and replay

### 3.3 Phase 2 Metrics (CI‑Specific)
Examples:
- Build duration distributions
- Failure rate trends
- Step topology stability

### Exit Criteria
- Two independent engines producing Phase 2 signals
- Phase 4 design unblocked
- No special‑case logic in core engine

---

## 4. Phase 3 — Explanation Layer

> Phase 3 begins **only after Phase 2 is validated**.

### Status ✅
- ✅ Phase 3 Contract finalized
- ✅ Phase 3 Design finalized
- ✅ Phase 3 deterministic explanation engine implemented
- ✅ Phase 3.1 validation‑gated LLM renderer implemented (opt‑in, safe fallback)
- ✅ End‑to‑end validation completed (with and without LLM enabled)

### Goal
Make Phase 2 signals understandable and trustworthy to humans.

### Scope
- Deterministic natural‑language explanations
- Evidence‑preserving numeric summaries
- Confidence annotations
- Optional LLM‑based readability enhancement (Phase 3.1)

### Constraints
- One explanation per signal
- No judgment, recommendations, or aggregation
- Phase 3 remains authoritative over Phase 3.1

---

## 5. Phase 4 — Pattern Learning & Correlation

> Phase 4 begins **only after multiple engines exist**.

### Status ✅ (Contract Only)
- ✅ Phase 4 Contract finalized and externally reviewed
- 🚧 Phase 4 Design (pending)
- 🚧 Phase 4 Implementation (blocked on second engine)

### Goal
Discover, validate, and retain reusable patterns across signals, time, and sources.

### Capabilities
- Cross‑engine signal alignment
- Pattern discovery and confidence accumulation
- Local vs global knowledge separation
- Long‑horizon drift detection

### Constraints
- Consumes Phase 2 signals only
- Introduces memory, not authority
- No access to raw Phase 1 events
- No decisions or recommendations

---

## 6. Additional Adapters (Incremental)

After correlation is validated, additional adapters may be added iteratively:

- Test execution topology
- Dependency graph snapshots
- Schema / API evolution
- Configuration / IaC artifacts

Each new adapter must:
- implement the Adapter Contract
- reuse Phase 1 Engine
- reuse Phase 2 Engine
- immediately benefit from existing correlation logic

---

## 7. Non‑Goals (Reconfirmed)

This plan explicitly excludes:
- Runtime telemetry
- Raw log ingestion
- Blocking enforcement
- Global risk scoring
- Semantic intent inference

---

## 8. Plan Maintenance

- This document is updated **only** when a phase is completed or reordered.
- Changes must reference Architecture Vision principles.
- Research documents inform changes but do not override this plan.

---

> **Summary:**
> We build confidence by layering truth sources, not features.
> Each step validates the architecture before expanding scope.
