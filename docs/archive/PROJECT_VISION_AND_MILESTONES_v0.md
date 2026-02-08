# Evolution Engine — Research Summary & Milestone Map

This document captures the **current state of research, frozen conclusions, and the forward milestone map** for the Evolution Engine project. It represents a line drawn between exploration and execution.

---

## 1. Research Summary — What We Now Know

After synthesizing multiple frontier model analyses and reconciling them against the original vision, the following conclusions are considered **locked**:

### Core Truths (No Longer Hypotheses)
- Software repositories behave as **evolving systems**, not static artifacts
- The **commit** is a sufficient atomic proxy for change in v0
- **Local history** is the only trustworthy baseline for evaluating change
- **Structural and behavioral signals** (co‑change, dispersion) are more reliable than semantics early
- **Immutable history with replayability** is non‑negotiable
- **Explanation must precede judgment** to earn trust
- AI‑generated code amplifies entropy but is best detected **statistically, not semantically**

### Explicit Exclusions from v0
- Language‑specific analysis
- AST‑level reasoning
- Semantic embeddings
- Global or absolute health scores
- Dashboards or heavy UI
- Cross‑repository intelligence

These exclusions are **intentional discipline**, not missing features.

---

## 2. Current Vision — Where This Is Going

> **Evolution Engine is an application and service that provides a trust and observability layer for AI‑influenced software development by observing, remembering, and explaining how a codebase evolves over time.**

The system is:
- not a linter
- not a CI gatekeeper
- not a productivity metric generator

It is:
- a **memory** of structural change
- a **behavioral baseline** for how a system normally evolves
- an **early‑warning signal** for unexpected evolutionary drift
- a **human‑in‑the‑loop escalation surface** when intent becomes unclear

Long‑term ambitions (explicitly deferred):
- Slow‑moving drift detection across long horizons
- Architectural trajectory and baseline‑over‑baseline comparison
- AI‑to‑AI feedback loops with bounded authority
- Evolutionary fingerprints of systems
- Optional correlation with behavioral / flow‑level signals (separate systems)

These are only pursued **after trust is established** at the core.

---

## 3. v0 Architectural Pillars (Frozen)

- **Git‑native ingestion** only
- **Immutable Change Event log** (append‑only, replayable)
- **~8–12 atomic, dimensionless metrics** per event
- **Co‑change and dispersion** as the structural core
- **Baseline deviation** using local history
- **Natural‑language explanations** grounded in historical comparison
- **No ASTs, no embeddings, no dashboards** in v0

---

## 4. Milestone Map

Each phase has a hard scope boundary and a definition of done.

---

### Phase 0 — Concept Lock ✅ (Complete)
**Goal:** Eliminate ambiguity and contradictions.

**Done when:**
- v0 pillars agreed
- atomic metrics bounded
- no unresolved conceptual conflicts

**Forbidden:**
- coding
- tooling decisions
- UX design

---

### Phase 1 — Evolution Indexer (Foundation)
**Goal:** Correctly observe and remember change.

**Deliverables:**
- Git ingestion pipeline
- Immutable Change Event log
- Atomic metric extraction
- Deterministic replay
- Basic CLI inspection

**Success criteria:**
- Works on any git repo
- Deterministic output
- Handles large histories (10k+ commits)

**Explicitly NOT included:**
- health scoring
- alerts
- UI
- semantics

---

### Phase 2 — Behavioral Memory & Baselines
**Goal:** Learn each repository’s identity.

**Deliverables:**
- Co‑change matrix
- Dispersion metrics
- Rolling baselines
- Cold‑start confidence handling
- Local deviation computation

**Success criteria:**
- Stable baselines on real repos
- Meaningful deviation signals
- Graceful degradation for young repos

---

### Phase 3 — Explanation Engine
**Goal:** Make deviations understandable and trustworthy.

**Deliverables:**
- Natural‑language explanation generator
- Historical comparison references
- Confidence annotations
- CLI / API explanation output

**Success criteria:**
- Humans understand *why* a deviation exists
- Explanations reference concrete history
- No unexplained math or opaque scores

---

### Phase 4 — Controlled Intelligence Expansion
**Goal:** Carefully add intelligence without breaking trust.

**Potential additions (gated):**
- AST‑assisted structural refinement
- Confidence‑weighted semantic embeddings
- Repository archetype detection
- AI‑to‑AI feedback experiments

All additions must be:
- optional
- reversible
- non‑destructive to earlier phases

---

### Phase 5 — Productization (Deferred)
**Goal:** Turn proven capability into user value.

**Possible forms:**
- Non‑blocking CI companion
- AI copilots consuming evolution signals
- Longitudinal architecture reports
- Enterprise trust layer

Only after:
- real repos
- real users
- demonstrated trust

---

## 5. Guiding Principle

> **The Evolution Engine is not a judge — it is a memory‑based observer of change.**

It watches.
It remembers.
It compares.
It explains.

Everything else comes later.
