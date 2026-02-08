

# Evolution Engine — Core Contract & Truth Source Classification

> Architectural Reference Document — Version 1.0

---

## Part 1: Evolution Engine Core Contract

### 1.1 Overview

An `EvolutionEngine<TEvent>` is a self-contained observation-and-baseline system bound to exactly one type of truth source. It operates in two strict phases, produces deterministic output, and exposes a uniform signal interface that downstream layers consume without knowledge of the source type.

```
┌─────────────────────────────────────────────────────┐
│              Correlation / Explanation Layer          │
│         (consumes signals; source-agnostic)          │
└──────────┬──────────────┬───────────────┬────────────┘
           │              │               │
     ┌─────▼─────┐ ┌─────▼─────┐  ┌──────▼──────┐
     │ Engine<A> │ │ Engine<B> │  │ Engine<C>   │
     │ (e.g.Git) │ │ (e.g.CI)  │  │ (e.g.Schema)│
     └─────┬─────┘ └─────┬─────┘  └──────┬──────┘
       Phase 2            Phase 2          Phase 2
       Phase 1            Phase 1          Phase 1
           │              │               │
      [Source A]     [Source B]       [Source C]
```

---

### 1.2 Engine Responsibilities (What It Guarantees)

| Guarantee | Description |
|---|---|
| **Single-source binding** | Each engine instance observes exactly one truth source type. |
| **Immutable event log** | Phase 1 events, once persisted, are never modified or deleted. |
| **Deterministic replay** | Given the same ordered event sequence, Phase 2 produces byte-identical baselines and signals. |
| **Causal ordering** | Events carry enough information to reconstruct a total or partial order without relying on wall-clock time alone. |
| **Phase isolation** | Phase 1 output is the sole input to Phase 2. No other data enters Phase 2. |
| **Self-containment** | An engine never reads from, writes to, or depends on another engine instance. |

---

### 1.3 Phase 1 Contract — Source Event Observation

Phase 1 is an **append-only observation log**. Its job is to faithfully record what happened, in order, with proof of origin.

#### 1.3.1 The `SourceEvent<TPayload>` Shape

Every truth source must produce events conforming to this minimal shape:

```
SourceEvent<TPayload>
├── event_id        : ContentHash        // Deterministic, content-addressable identifier
├── predecessor_ref : ContentHash | null  // Causal link (null only for the first event)
├── observed_at     : Timestamp          // When the engine observed the event (monotonic)
├── origin_at       : Timestamp | null   // When the source claims it occurred (may be null)
├── attestation     : Attestation        // Proof of origin / trust anchor
├── source_id       : SourceIdentifier   // Stable identifier for the specific source instance
└── payload         : TPayload           // Source-specific, opaque to the core contract
```

**Key type definitions:**

- `ContentHash` — A cryptographic digest of the event's content (e.g., SHA-256). The engine computes this; the source does not choose its own ID.
- `Attestation` — Source-specific proof that the event is genuine. May be a cryptographic signature, a content hash from the source system, or a verifiable reference (e.g., a git commit SHA the engine independently verified). Must be **independently re-verifiable** against the source.
- `SourceIdentifier` — A stable, unique reference to the specific source instance (e.g., a repository URL + branch, a CI pipeline ARN, a schema registry namespace).

#### 1.3.2 Phase 1 Invariants

1. **Append-only.** The event store only supports `append`. No update, delete, or reorder operations exist.
2. **Content-addressing is authoritative.** `event_id` is derived from the event content. Two events with identical content produce the same `event_id`. Duplicates are idempotent (re-appending the same event is a no-op).
3. **Ordering is causal, not temporal.** `predecessor_ref` establishes order. `observed_at` is metadata for debugging, not for sequencing. If the source provides a DAG (e.g., git), the engine must preserve the DAG structure in `predecessor_ref`, not flatten it.
4. **Attestation is mandatory.** An event without a verifiable attestation must be rejected, not stored with a warning.

#### 1.3.3 What Is Explicitly Forbidden in Phase 1

| Forbidden Action | Rationale |
|---|---|
| Filtering or dropping events | The log must represent the complete observed history. Filtering is interpretation. |
| Enriching events with derived data | Adding computed fields (e.g., "files changed: 12") is Phase 2 work. |
| Interpreting, scoring, or classifying events | No labels like "large commit," "breaking change," or "anomalous." |
| Cross-referencing other sources or engines | Phase 1 sees only its own source. |
| Normalizing the payload | `TPayload` is stored as-received. Structural normalization happens at the adapter boundary before the event enters Phase 1, not inside Phase 1 itself. |
| Depending on wall-clock ordering | Two events with the same `observed_at` must still be orderable via `predecessor_ref`. |

---

### 1.4 Phase 2 Contract — Behavioral Baselines and Deviation Signals

Phase 2 is a **deterministic derivation layer**. It reads the Phase 1 log and produces baselines (what is structurally normal) and deviation signals (what has changed relative to normal).

#### 1.4.1 Baselines

A baseline is a statistical or structural summary computed over a defined window of Phase 1 events.

```
Baseline
├── baseline_id    : ContentHash           // Derived from inputs + parameters
├── engine_id      : EngineIdentifier      // Which engine produced this
├── window         : EventRange            // Start/end event_ids (inclusive)
├── dimension      : DimensionKey          // What is being measured (source-specific)
├── value          : BaselineValue         // The computed summary (numeric, distribution, structural hash, etc.)
└── computed_at    : Timestamp             // When derivation ran (metadata only)
```

- `DimensionKey` — A source-specific but engine-registered string identifying the measurable dimension (e.g., `"commit_frequency"`, `"build_duration"`, `"schema_field_count"`). The engine declares its supported dimensions at registration time.
- `BaselineValue` — One of a small set of permitted types: scalar ($\mathbb{R}$), distribution (histogram or percentiles), set (of content hashes), or structural fingerprint (a hash of a canonical form).
- `EventRange` — Defined by bounding `event_id` values, never by timestamps.

#### 1.4.2 Deviation Signals

A deviation signal is emitted when a new observation diverges from the current baseline beyond a defined threshold.

```
DeviationSignal
├── signal_id      : ContentHash           // Derived from inputs
├── engine_id      : EngineIdentifier
├── baseline_ref   : ContentHash           // The baseline being deviated from
├── event_ref      : ContentHash           // The event(s) that triggered the deviation
├── dimension      : DimensionKey
├── observed_value : BaselineValue         // What was actually observed
├── deviation      : DeviationMeasure      // Magnitude and direction of divergence
└── emitted_at     : Timestamp             // Metadata only
```

- `DeviationMeasure` — A numerical magnitude (e.g., standard deviations from mean, percentage change, Jaccard distance for sets) **plus** a direction enum: `{ increased, decreased, structural_change }`. No qualitative labels.

#### 1.4.3 Phase 2 Invariants

1. **Pure function of Phase 1.** $\text{Phase2}(E_1, E_2, \ldots, E_n) = (B, S)$ where $B$ is the set of baselines and $S$ is the set of signals. Same input → same output. Always.
2. **No external state.** Phase 2 reads the Phase 1 log and its own previously-computed baselines. Nothing else.
3. **Baselines are versioned, not mutated.** When a baseline is recomputed over a new window, a new `baseline_id` is produced. The old baseline remains in the store.
4. **Signals reference their evidence.** Every `DeviationSignal` must point to the specific `event_ref`(s) and `baseline_ref` that produced it. No orphan signals.
5. **Thresholds are configuration, not code.** Deviation thresholds are declared as engine parameters. Changing a threshold and replaying must produce different signals deterministically.

#### 1.4.4 What Is Explicitly Forbidden in Phase 2

| Forbidden Action | Rationale |
|---|---|
| Semantic judgment | No "risky," "suspicious," "good," "bad." That belongs to the correlation/explanation layer. |
| Cross-engine data access | Engine A's Phase 2 must not read Engine B's data. Correlation is a layer above. |
| Intent inference | "This developer intended to refactor" is not a baseline or deviation. |
| Mutating Phase 1 data | Phase 2 is read-only with respect to Phase 1. |
| Non-deterministic operations | No random sampling, no calls to external services, no time-dependent branching. |
| Natural language output | Signals are structured data. Human-readable explanations are the correlation layer's job. |

---

### 1.5 Engine Lifecycle & Registration

```
EngineDescriptor
├── engine_id       : EngineIdentifier
├── source_type     : string              // e.g., "git", "ci_pipeline", "schema_registry"
├── event_schema    : TPayload schema     // Declared shape of the payload
├── dimensions      : DimensionKey[]      // What Phase 2 will measure
├── version         : SemVer              // Contract version this engine implements
└── replay_cursor   : ContentHash | null  // Last processed event (for resumption)
```

- Engines register with the system before emitting events.
- Multiple engines of the same `source_type` may exist (e.g., two git repos).
- The correlation layer discovers engines via their descriptors, never by hard-coded references.

---

### 1.6 Contract Summary Diagram

```
                      ┌─────────────────────────────────────┐
                      │        EvolutionEngine<TEvent>       │
                      │                                     │
  [Truth Source] ───► │  Phase 1: Observe & Store           │
                      │    SourceEvent<TPayload> ───►       │
                      │    Append-only immutable log        │
                      │           │                         │
                      │           ▼                         │
                      │  Phase 2: Derive & Signal           │
                      │    Baselines (windowed summaries)   │
                      │    DeviationSignals (divergences)   │
                      │           │                         │
                      └───────────┼─────────────────────────┘
                                  │
                                  ▼
                      ┌─────────────────────────────────────┐
                      │  Uniform Signal Interface            │
                      │  (DeviationSignal + EngineDescriptor)│
                      └─────────────────────────────────────┘
                                  │
                                  ▼
                        Correlation / Explanation Layer
```

---

## Part 2: Future Truth Source Classification

### Classification Framework

Each source is evaluated on four axes:

| Axis | Question |
|---|---|
| **Atomicity** | Is there a natural, discrete, content-addressable event? |
| **Attestation** | Can the event's authenticity be independently verified? |
| **Signal Richness** | What structural or behavioral baselines can Phase 2 derive? |
| **Limitations** | What are the known risks, gaps, or failure modes? |

---

### Source 1: Git Repositories *(Reference Implementation)*

> **Status:** Implemented. This is the minimum viable and default source.

- **Atomic Event:** A git commit object (tree hash, parent references, author, committer, message, timestamp).
- **Attestation:** SHA-1/SHA-256 content-addressable hash computed by git itself. GPG/SSH signatures when available. The engine can independently verify the hash by re-hashing the object.
- **Phase 2 Signals:**
  - Commit frequency distribution (per-author, per-path, per-window)
  - File co-change coupling (which files change together)
  - Path churn rate (how often specific paths are modified)
  - Commit graph topology (merge patterns, branch lifetimes, linearity)
  - Author collaboration patterns (who touches overlapping paths)
  - Commit size distribution (insertions + deletions as a structural metric)
- **Limitations:**
  - Squash merges destroy intermediate history — the engine observes only the squashed result.
  - Force-pushes rewrite history — the engine must treat previously-observed events as canonical and flag divergence.
  - Shallow clones provide incomplete predecessor chains.
  - Submodules are references, not inline content; they require a separate engine instance or explicit pointer-following policy.

---

### Source 2: Build / CI Pipeline Executions

- **Atomic Event:** A build execution record: trigger event, pipeline identifier, step sequence with outcomes (pass/fail/skip + duration), final status, and output artifact references.
- **Attestation:** CI systems (GitHub Actions, GitLab CI, Jenkins, etc.) produce execution logs with run IDs, timestamps, and often signed artifact digests. The engine can verify by cross-referencing the CI system's API or stored run record. Provenance attestations (e.g., SLSA) provide stronger guarantees where available.
- **Phase 2 Signals:**
  - Build duration baselines (per-pipeline, per-step)
  - Failure rate trends (overall, per-step, per-trigger-type)
  - Step topology stability (are steps being added, removed, reordered?)
  - Trigger-to-completion latency distribution
  - Artifact output set changes (new artifacts appearing, old ones disappearing)
  - Dependency resolution duration (time spent fetching/resolving dependencies)
- **Limitations:**
  - CI configurations vary wildly across providers; the source adapter must normalize to a common pipeline-execution model before Phase 1 ingestion.
  - Flaky tests introduce noise into failure-rate baselines — Phase 2 cannot distinguish flakiness from genuine regression (that distinction is semantic judgment).
  - Parallel/matrix builds produce multiple execution records per logical build; the adapter must decide whether these are one event or many (this is a source-adapter design decision, not a Phase 1 decision).
  - Retried builds may share the same trigger but different outcomes — the engine must treat each execution as a distinct event.

---

### Source 3: Test Execution Topology

> **Distinct from CI pipelines.** CI records *whether* tests passed. This source records *what was tested, in what structure, with what coverage shape.*

- **Atomic Event:** A test suite execution report: test identifiers organized by module/suite hierarchy, pass/fail/skip per test, execution order, and a coverage map (which source paths were exercised by which tests).
- **Attestation:** Test runner output (JUnit XML, TAP, etc.) combined with a content hash of the test source files at execution time. The engine can verify that the declared test set matches the test source files present at the corresponding commit (cross-referenced via git engine, but only at the correlation layer — not within this engine).
- **Phase 2 Signals:**
  - Test count trends (per-module, per-suite)
  - Coverage shape stability (which paths are covered, not coverage *percentage* — that's a metric, not a structural observation)
  - Test-to-source ratio over time
  - Failure clustering (which tests fail together, structurally)
  - Test execution order stability
  - Orphaned test detection (tests whose target source paths no longer exist in the coverage map)
- **Limitations:**
  - Coverage shape depends on the coverage tool's granularity (file-level vs. function-level vs. line-level). The engine must declare its granularity and not mix them.
  - Tests that are never executed (skipped, commented out) produce no events — absence of evidence is not evidence of absence.
  - Integration/E2E tests may exercise paths outside the observed repository, creating coverage references the engine cannot resolve.
  - Test report formats are not standardized in practice; the adapter layer carries significant complexity.

---

### Source 4: Application Flow Shape Snapshots

> A "flow shape" is a structural graph describing the application's control flow or dependency flow at a point in time, derived from static analysis of source artifacts.

- **Atomic Event:** A point-in-time snapshot of the application's structural flow graph — nodes (modules, entry points, handlers) and edges (calls, imports, message routes) — tied to a specific source version (e.g., a commit hash).
- **Attestation:** The snapshot is derived deterministically from source artifacts at a known version. Attestation = content hash of input artifacts + the analyzer version + the resulting graph hash. Reproducible: re-running the same analyzer on the same inputs must produce the same graph.
- **Phase 2 Signals:**
  - Node count and edge count trends (structural growth/shrinkage)
  - Graph density and connectivity changes
  - Entry point proliferation or consolidation
  - Cyclomatic complexity of the flow graph over time (structural, not code-level)
  - Subgraph stability (which clusters of nodes remain stable vs. which are frequently restructured)
  - Dead node detection (nodes with no incoming edges that previously had them)
- **Limitations:**
  - **This is the highest-risk source for over-abstraction.** Flow shape extraction is inherently tied to language, framework, and project structure. The adapter is doing heavy lifting, and errors in the adapter silently corrupt Phase 1.
  - Dynamic dispatch, plugin systems, and runtime configuration make static flow shapes incomplete by definition.
  - Snapshot frequency must be defined carefully — too frequent produces noise, too infrequent misses transient structural states.
  - The boundary of "the application" must be explicitly configured. Microservice architectures have no natural single boundary.

---

### Source 5: Schema / API Surface Evolution

- **Atomic Event:** A versioned schema or API definition artifact: database migration files, OpenAPI/Swagger specs, Protocol Buffer definitions, GraphQL schemas, or similar machine-readable interface contracts.
- **Attestation:** These artifacts are typically version-controlled (and thus git-attested) or stored in a schema registry with version identifiers. The engine content-hashes the canonical form of the schema at each version.
- **Phase 2 Signals:**
  - Field/endpoint count trends (surface area growth)
  - Breaking vs. additive change ratios (structural classification only: field removed = breaking, field added = additive — no judgment on impact)
  - Schema complexity (nesting depth, reference cycles, polymorphic type usage)
  - Rate of surface change relative to source change (is the API surface changing faster or slower than the codebase?)
  - Deprecation lifecycle patterns (time between "deprecated" annotation and removal)
  - Coupling surface — how many distinct entity types are exposed through a single endpoint or message
- **Limitations:**
  - "Breaking change" classification is structural, but even structural classification has edge cases (e.g., adding a required field with a default — breaking or additive?). The engine's classification rules must be explicit and versioned.
  - Schema registries may allow non-linear version histories (e.g., branching compatibility modes in Confluent Schema Registry). The `predecessor_ref` model must accommodate this.
  - API specs can be auto-generated from code or hand-written; the provenance differs and affects trust level. The attestation must capture which case applies.
  - Internal APIs (never exposed externally) and external APIs may warrant separate engine instances — the same schema change has different structural significance depending on exposure.

---

### Source 6: Dependency Graph Snapshots

- **Atomic Event:** A resolved dependency tree at a specific point in time — the full transitive closure of declared dependencies with pinned versions, as captured by lock files (`package-lock.json`, `Cargo.lock`, `go.sum`, etc.) or SBOM (Software Bill of Materials) artifacts.
- **Attestation:** Lock files are typically version-controlled (git-attested). SBOMs can be signed. The engine hashes the resolved tree (sorted, canonical form) to produce a content-addressable snapshot.
- **Phase 2 Signals:**
  - Dependency count trends (direct and transitive)
  - Dependency churn rate (how often the resolved tree changes)
  - Tree depth trends (how deep does the transitive closure go?)
  - Update velocity per dependency (how quickly are individual dependencies updated after new versions are published — requires comparing against a known registry, which may be an external lookup performed by the adapter, not Phase 2)
  - Concentration risk (how many transitive dependencies share a single root dependency)
  - Dependency addition/removal rate as a ratio of source change velocity
- **Limitations:**
  - Lock file formats differ by ecosystem and change over time. The adapter must produce a canonical dependency-tree representation.
  - Optional, peer, and dev dependencies have different structural significance, but classifying that significance edges toward interpretation. The engine should preserve the dependency *kind* as a payload field and let Phase 2 compute baselines per-kind.
  - Some ecosystems (notably Python/pip without strict locking) have non-deterministic resolution. If the lock file is absent, the source does not meet the attestation requirement and should be rejected until a lock file is available.
  - Monorepos may have multiple lock files; each should be treated as a separate source instance or clearly scoped within the `SourceIdentifier`.

---

### Source 7: Configuration & Infrastructure-as-Code Artifacts

- **Atomic Event:** A change to a versioned configuration artifact — Terraform/OpenTofu plans, Kubernetes manifests, Helm charts, Dockerfiles, environment configuration, or feature flag definitions — captured as a before/after pair of the canonical artifact form.
- **Attestation:** Typically version-controlled (git-attested) or stored in a configuration management system with audit trails. For IaC, the `terraform plan` output (or equivalent) can serve as a deterministic attestation of intended state change.
- **Phase 2 Signals:**
  - Configuration surface area (resource count, parameter count) trends
  - Configuration drift rate (how often does prod config diverge from declared IaC state?)
  - Environment parity — structural similarity between staging/production configurations over time
  - Resource coupling (which resources are always modified together)
  - Feature flag lifecycle (creation-to-removal duration, active flag count trends)
  - Parameterization ratio (how much of the configuration is templated vs. hard-coded)
- **Limitations:**
  - IaC plans depend on provider state, which is external and mutable. A Terraform plan is deterministic given the same state + config, but state changes independently. The engine must snapshot the plan output, not re-derive it.
  - Configuration formats are extremely heterogeneous. Unlike schemas (which have a finite set of well-known formats), config can be YAML, JSON, HCL, TOML, INI, or proprietary. The adapter burden is high.
  - Secret management intersects with configuration — the engine must never ingest secret values. The adapter must redact or exclude secrets before events enter Phase 1. This is a hard security constraint, not an optional policy.
  - Feature flag systems (LaunchDarkly, etc.) may not have a version-controlled source of truth, relying instead on API state. The attestation model is weaker here.

---

### Candidate Classification Summary

| Source | Atomicity | Attestation Strength | Signal Richness | Adapter Complexity | Recommended Priority |
|---|---|---|---|---|---|
| **Git** | ★★★★★ | ★★★★★ | ★★★★★ | Low (reference) | **Implemented** |
| **Build / CI** | ★★★★ | ★★★★ | ★★★★ | Medium | **High** |
| **Test Topology** | ★★★ | ★★★ | ★★★★ | Medium-High | Medium |
| **Schema / API** | ★★★★ | ★★★★ | ★★★★ | Medium | **High** |
| **Dependency Graph** | ★★★★ | ★★★★ | ★★★ | Medium | Medium |
| **Flow Shape** | ★★ | ★★★ | ★★★★★ | **Very High** | Low (high risk) |
| **Config / IaC** | ★★★ | ★★★ | ★★★ | **High** | Low |

---

### Sources Explicitly Excluded (and Why)

| Excluded Source | Reason |
|---|---|
| **Runtime telemetry** (APM, metrics, traces) | Continuous streams, not discrete attested events. Extremely high volume. Non-deterministic by nature. |
| **Raw application logs** | Unstructured, non-attested, high noise, schema-less. Cannot meet the attestation or determinism requirements. |
| **Language-specific static analyzers** | These are *tools that produce data*, not truth sources themselves. Their output may feed into the Flow Shape source via an adapter, but they are not sources in their own right. |
| **Ticket/issue trackers** | Human-authored, non-attested (anyone can edit), semantic by nature. Cannot produce structural baselines without interpretation. |
| **Chat/communication logs** | Same problems as ticket trackers, plus privacy constraints. |
| **Code review comments/approvals** | Tempting, but approval is a human judgment — ingesting it as a structural event forces semantic interpretation in Phase 1. |

---

### Cross-Source Correlation — Architectural Boundary

This document deliberately stops at the single-engine boundary. However, one structural note for future reference:

The correlation layer above all engines should consume `DeviationSignal` objects uniformly. It should **never** need to understand `TPayload`. The only source-specific knowledge the correlation layer uses is:

1. `engine_id` — to know which engine produced a signal
2. `dimension` — to know what was measured
3. `deviation` — to know magnitude and direction

If the correlation layer ever requires knowledge of `TPayload` structure, the engine's Phase 2 has failed to sufficiently abstract its signals, and the contract has been violated.

---

*This document defines the architectural contract. Implementation decisions (storage backend, event serialization format, adapter plugin mechanism, etc.) are intentionally deferred and must be made in a separate document.*ß


# Evolution Engine — Addendum A: Scope, Trust, Cold‑Start, Ordering, and Deviation Placement

**Status:** Proposed addendum to *Evolution Engine — Core Contract & Truth Source Classification (v1.0)*
**Merge target:** Directly into v1.0 prior to lock

---

## A1. Engine Scope & Boundary

*Applies to: §1 (Engine Overview) — insert after engine definition.*

### A1.1 Scope Definition

A single `EvolutionEngine` instance is bound to exactly one **evolution scope**. A scope is defined by the tuple:

```
scope := (subject_kind, subject_identifier, environment)
```

| Field                  | Meaning                                                        | Example                          |
| ---------------------- | -------------------------------------------------------------- | -------------------------------- |
| `subject_kind`         | The type of entity whose evolution is being tracked            | `service`, `schema`, `pipeline`  |
| `subject_identifier`   | A stable, unique identifier for that entity                    | `payments-api`, `orders.v2`      |
| `environment`          | The deployment or lifecycle boundary within which observation occurs | `production`, `staging`, `ci`    |

### A1.2 Observation Boundary Rule

An engine instance **MUST NOT** ingest attestations whose `subject_kind`, `subject_identifier`, or `environment` differs from its bound scope. Cross‑scope correlation is the responsibility of a higher‑layer orchestrator, never the engine itself.

### A1.3 When a New Instance Is Required

A new engine instance **MUST** be created when any component of the scope tuple changes. Specifically:

- Tracking a **different entity** → new instance.
- Tracking the **same entity in a different environment** → new instance.
- A **subject_identifier rename or split** (e.g., service decomposition) → new instance(s); the prior instance enters terminal state.

> **Rationale:** This prevents a single engine from silently mixing signals across boundaries, which would corrupt both Phase 1 structural guarantees and Phase 2 trend analysis.

### A1.4 Scope Metadata

Every engine instance **MUST** persist its scope tuple as immutable metadata at creation time. This tuple is included in all emitted records and is available for external audit without payload inspection.

---

## A2. Attestation Strength / Trust Tier

*Applies to: §3 (Truth Source Classification) — append as subsection.*

### A2.1 Trust Tier Field

Each attestation record **MUST** carry a `trust_tier` field expressing the strength of the attestation's origin. This is a **source‑intrinsic** property, set at ingestion time by the engine based on the truth source classification already defined in §3. It is **not** a quality judgment on the payload.

```
trust_tier := T1 | T2 | T3
```

| Tier | Name            | Criteria                                                                                  | Example Sources                        |
| ---- | --------------- | ----------------------------------------------------------------------------------------- | -------------------------------------- |
| `T1` | **Cryptographic** | Source provides a cryptographically verifiable proof (signature, hash chain, Merkle root) | Signed commits, notarized artifacts    |
| `T2` | **Systemic**      | Source is a controlled system with authenticated output but no per‑record cryptographic proof | CI runner output, container registry metadata |
| `T3` | **Declared**      | Source is a human or process assertion without independent verification                    | Manual approval flags, config annotations |

### A2.2 Phase 1 Constraint

Phase 1 **MUST** assign `trust_tier` based solely on source classification. Phase 1 **MUST NOT** promote or demote a tier based on payload content or historical behavior. Tier assignment is deterministic given the source.

### A2.3 Downstream Use

Higher layers **MAY** use `trust_tier` to weight, filter, or gate signals without inspecting attestation payloads. The tier is exposed as a first‑class field in the attestation envelope:

```json
{
  "attestation_id": "...",
  "scope": { "subject_kind": "...", "subject_identifier": "...", "environment": "..." },
  "trust_tier": "T1",
  "predecessor_ref": "...",
  "timestamp": "...",
  "payload": { }
}
```

---

## A3. Cold‑Start & Confidence Semantics

*Applies to: §4 (Phase 2 — Trend & Deviation Analysis) — insert before deviation logic.*

### A3.1 Minimum History Threshold

Phase 2 analysis **MUST NOT** emit trend or deviation conclusions until a configurable **minimum history count** $n_{\min}$ of attestations has been recorded for the bound scope. Until this threshold is met, Phase 2 is in **cold‑start state**.

### A3.2 Cold‑Start Behavior

While in cold‑start state, Phase 2:

- **MUST** accept and store incoming attestations normally (Phase 1 guarantees are unaffected).
- **MUST NOT** emit deviation signals.
- **MUST** emit a `confidence_status` of `insufficient_history` on any query or output.

### A3.3 Confidence Metadata

Every Phase 2 output **MUST** include the following metadata:

```json
{
  "confidence_status": "insufficient_history | accumulating | sufficient",
  "history_depth": 14,
  "history_minimum": 30
}
```

| Status                  | Meaning                                                         |
| ----------------------- | --------------------------------------------------------------- |
| `insufficient_history`  | $\text{history\_depth} < n_{\min}$. No analytical output is valid. |
| `accumulating`          | $n_{\min} \leq \text{history\_depth} < 2 \cdot n_{\min}$. Output is valid but may lack stability. |
| `sufficient`            | $\text{history\_depth} \geq 2 \cdot n_{\min}$. Normal operating confidence. |

### A3.4 Absence of Signal

The absence of attestations over a time window **MUST NOT** be interpreted as stability or health by Phase 2. Silence is not success. Specifically:

- If no attestation has been received within a configurable **expected cadence window** $\Delta t_{\text{expected}}$, Phase 2 **MUST** emit a `signal_gap` advisory (not a deviation).
- A `signal_gap` carries no analytical weight but is visible to higher layers.
- Phase 2 **MUST NOT** interpolate, impute, or synthesize missing attestations.

---

## A4. Causal Ordering Flexibility

*Applies to: §2 or §3 (Attestation Record Structure) — amend `predecessor_ref` definition.*

### A4.1 Predecessor Reference Modes

The `predecessor_ref` field supports two modes, determined by the nature of the source:

| Mode        | Value of `predecessor_ref`        | When to Use                                                                                      |
| ----------- | --------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Explicit** | `attestation_id` of the causal predecessor | Source has clear causal lineage (e.g., commit chain, schema migration sequence)                  |
| **Temporal** | `null`                            | Source is naturally independent or non‑sequential (e.g., periodic CI runs, recurring health checks) |

### A4.2 Rules

1. **Phase 1 MUST accept `predecessor_ref: null`** as a valid value. A null predecessor does not indicate an error; it indicates the attestation has no causal antecedent within the engine's knowledge.

2. When `predecessor_ref` is `null`, **Phase 1 falls back to `timestamp` ordering** for sequencing within the scope. The attestation is appended to the timeline but does not participate in causal chain validation.

3. An attestation **MUST NOT** reference a `predecessor_ref` that does not exist in the engine's current scope. A reference to an unknown attestation is a **hard ingestion error**, not a graceful fallback.

4. **Phase 2 MAY use both causal chains and temporal sequences** as inputs, but **MUST track which ordering mode contributed** to any analytical conclusion. Mixed‑mode analysis within a single trend calculation is permitted but must be declared in output metadata.

### A4.3 Non‑Requirement

The engine **MUST NOT** force sources into artificial causal graphs. If a CI system produces independent, unrelated runs, each run's attestation stands alone with `predecessor_ref: null`. Imposing synthetic lineage would corrupt the causal model for all consumers.

---

## A5. Deviation Threshold Placement

*Applies to: §4 (Phase 2 — Trend & Deviation Analysis) — clarify boundary.*

### A5.1 Separation of Measure and Judgment

Phase 2 encompasses two distinct operations:

| Operation            | Description                                                      | Where It Lives |
| -------------------- | ---------------------------------------------------------------- | -------------- |
| **Deviation measure** | A raw, quantitative delta between observed and expected behavior | Phase 2        |
| **Deviation judgment**| A binary or categorical classification (e.g., "anomalous", "acceptable") based on a threshold applied to the measure | Phase 2 **or** higher layer |

### A5.2 Rules

1. Phase 2 **MUST** compute and emit raw deviation measures when `confidence_status` is `accumulating` or `sufficient`.

2. Phase 2 **MAY** apply built‑in thresholds and emit deviation judgments. If it does, the thresholds used **MUST** be declared in engine configuration and included in output metadata.

3. Phase 2 **MUST** always emit the raw deviation measure alongside any judgment. A higher layer must be able to apply its own thresholds without re‑deriving the measure.

4. **Raw deviation measures are not Phase 1 outputs.** They are analytical artifacts and carry Phase 2 confidence semantics (see §A3.3). They **MUST NOT** be treated as structural facts by any consumer.

### A5.3 Output Shape

```json
{
  "scope": { "..." : "..." },
  "confidence_status": "sufficient",
  "history_depth": 47,
  "deviation": {
    "measure": 0.73,
    "measure_unit": "stddev_from_mean",
    "judgment": "within_tolerance",
    "threshold_applied": 2.0,
    "threshold_source": "engine_config"
  }
}
```

If the engine is configured to **not** apply thresholds, `judgment`, `threshold_applied`, and `threshold_source` are omitted. The `measure` and `measure_unit` fields are always present when deviation output is emitted.

---

## Summary of Addendum Changes

| Addendum | Affects Section | Nature of Change     |
| -------- | --------------- | -------------------- |
| A1       | §1              | New constraint (scope binding) |
| A2       | §3              | New field (`trust_tier`) on existing attestation envelope |
| A3       | §4              | New pre‑condition (cold‑start) and required metadata |
| A4       | §2/§3           | Amended semantics of existing `predecessor_ref` field |
| A5       | §4              | Clarified boundary between measure and judgment |

No new architectural concepts were introduced. No Phase 1 guarantees were relaxed. All changes are enforceable at implementation time.