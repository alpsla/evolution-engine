# Evolution Engine — Architecture Vision

> **Canonical Architecture Reference (Constitution)**  
> This document defines the architectural vision, principles, and boundaries of the Evolution Engine application.  
> It answers *why the system exists*, *what it guarantees*, and *how its major parts relate*.  
> It intentionally avoids implementation details and low‑level contracts.

---

## 1. Purpose & Product Promise

Modern software development — especially AI‑influenced development — evolves faster than humans can reliably reason about change.  
Risk is rarely introduced by a single commit or action; it emerges **gradually**, **structurally**, and often **without obvious intent**.

The Evolution Engine application exists to:
- Observe how trusted systems of record evolve over time
- Learn what "normal evolution" looks like for each system
- Surface unexpected deviation or drift early
- Discover and remember structural patterns across time and sources
- Escalate uncertainty to humans with evidence, context, and actionable detail

**The product promise is risk reduction through structural memory.**

The system does not judge, enforce, or block change.  
It provides **memory, comparison, pattern recognition, and evidence** so humans can intervene before risk compounds.

---

## 2. Core Architectural Principles (Non‑Negotiable)

1. **Observation precedes interpretation**  
   Facts are captured before any meaning is assigned.

2. **History is immutable; interpretation is disposable**  
   Raw observations are never rewritten. Derived views may be recomputed or discarded.

3. **Determinism beats intelligence**  
   Given the same inputs, the system must always produce the same outputs.  
   Where non‑determinism is permitted (LLM rendering, pattern interpretation), it is bounded, validated, and fallback‑protected.

4. **Local baselines over global heuristics**  
   Each system is evaluated only against its own historical behavior.  
   Global knowledge serves only as a defeasible prior when local history is insufficient.

5. **Multiple weak signals are better than one strong opinion**  
   Risk emerges from correlation, not single metrics.

6. **Absence of signal is not evidence of safety**  
   Confidence must be earned through sufficient history.

7. **Humans are escalated to, not replaced**  
   The system supports human judgment; it does not automate it away.

8. **Evidence enables action**  
   Every report must include enough specific evidence (commits, files, tests, dependencies) for the user or their AI assistant to investigate immediately.

Any change that violates these principles is considered architectural regression.

---

## 3. System Architecture — Complete Pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│                    EVOLUTION ENGINE PIPELINE                      │
│                                                                    │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                      │
│  │ Phase 1  │──▶│ Phase 2  │──▶│ Phase 3  │                      │
│  │ Observe  │   │ Baseline │   │ Explain  │                      │
│  │ & Record │   │ & Signal │   │ (+ 3.1)  │                      │
│  └──────────┘   └─────┬────┘   └─────┬────┘                      │
│                       │              │                             │
│              numbers  │              │  language                   │
│                       ▼              ▼                             │
│                  ┌─────────────────────────┐                      │
│                  │       Phase 4           │                      │
│                  │  4a: Pattern Discovery  │ ←──── Knowledge Base │
│                  │  4b: Pattern Interpret  │ ────▶ (SQLite)       │
│                  └────────────┬────────────┘                      │
│                               │                                    │
│                               ▼                                    │
│                  ┌─────────────────────────┐                      │
│                  │       Phase 5           │                      │
│                  │  Advisory & Evidence    │                      │
│                  └────────────┬────────────┘                      │
│                               │                                    │
│                               ▼                                    │
│                           HUMAN                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. The Evolution Engine Concept

An **Evolution Engine** is a self‑contained system that observes the evolution of **one trusted source of truth** and produces structured signals about how that source changes over time.

Each Evolution Engine operates in two strict phases:
- **Phase 1 — Observation**: faithfully records atomic events from a source, immutably and without interpretation.
- **Phase 2 — Behavioral Baselines**: derives statistical or structural baselines from observed history and emits deviation signals.

An Evolution Engine never:
- reads data from another engine
- interprets intent
- produces human‑facing explanations

---

## 5. Phase Definitions

### Phase 1 — Observation (Record)
Records atomic events from truth sources. Append‑only, content‑addressable, immutable.

### Phase 2 — Behavioral Baselines (Measure)
Derives statistical baselines and emits deviation signals. Deterministic, per‑source, no cross‑source access.

### Phase 3 — Explanation (Communicate)
Translates Phase 2 signals into human‑readable explanations. Template‑based with optional LLM enhancement (Phase 3.1). No judgment, no recommendations.

**Phase 3 serves two consumers:**
- Humans (readable understanding of individual signals)
- Phase 4b (natural language context for semantic pattern interpretation)

### Phase 4 — Pattern Learning (Remember)
Discovers, validates, and retains reusable patterns across signals, time, and sources.

**Phase 4 has two sub‑layers:**

- **Phase 4a — Algorithmic Pattern Discovery**: Statistical correlation, co‑occurrence detection, temporal sequence analysis. Deterministic. Reads Phase 2 signals.
- **Phase 4b — Semantic Pattern Interpretation**: LLM‑assisted enrichment of discovered patterns with human‑understandable descriptions. Reads Phase 3 explanations as context. Non‑deterministic but bounded and validated.

**Cascade rule:** Phase 4a (math) proposes → Phase 4b (LLM) describes → evidence accumulates → knowledge is approved. If math finds no pattern, the LLM may propose a low‑confidence hypothesis, but it requires significantly more evidence before promotion.

Patterns are stored in the **Knowledge Base** as Knowledge Artifacts containing both statistical evidence and semantic descriptions.

### Phase 5 — Advisory (Inform)
Compiles current signals, pattern context, and historical knowledge into user‑facing reports.

**Phase 5 produces three layers:**
1. **Human Summary** — "What changed compared to normal?" with visual comparisons
2. **Pattern Context** — "We've seen this combination before" with historical frequency and typical duration
3. **Evidence Package** — Specific commits, files, tests, and dependencies the user or their AI assistant can immediately investigate

Phase 5 does not recommend, judge, or enforce. It presents evidence.

### Phase 5 Extension — Fix Verification (Validate)
After an advisory triggers investigation and the user applies fixes, Phase 5 can re‑run
and compare the new state against the previous advisory.

**The feedback loop:**
```
Advisory → Investigation Prompt → User's AI → Fix Applied → Re‑run → Verification Report
```

**Fix Verification produces:**
- Resolved changes (deviation returned to normal range)
- Persisting changes (still flagged despite fix)
- New changes (introduced by the fix itself)
- Fix outcome fed back to Phase 4 as pattern lifecycle evidence

This turns the system from a "flag raiser" into an "outcomes tracker" — verifying
that corrective actions actually resolved the structural issues that were flagged.

---

## 6. Plural Truth Sources

The application is designed to support **multiple independent truth sources**, organized into source families.

Currently defined families:
- Version Control (Git)
- CI / Build Pipeline
- Test Execution
- Dependency Graph / SBOM
- Schema / API Evolution
- Deployment / Release
- Configuration / IaC
- Security Scanning

Each truth source:
- has its own Evolution Engine instance
- has its own history and baselines
- has its own limitations and trust characteristics

**Git is the default and minimum viable source**, but it is not the only one.

> The application behaves identically whether one or many Evolution Engines are present.

---

## 7. Knowledge Base

The Knowledge Base is the system's **long‑term memory**. It stores:
- **Pattern Objects** — candidate patterns under evaluation
- **Knowledge Artifacts** — approved, retained patterns with full evidence

Each Knowledge Artifact contains:
- Statistical evidence (correlation strength, occurrence count, source families involved)
- Semantic description (what the pattern means in human terms)
- Confidence and approval metadata
- Scope designation (local to one repo, or global across repos)

**Knowledge scopes:**
- **Local** — discovered on this repository; always takes precedence
- **Community** — imported from shared anonymized digests; never overwrites local
- **Confirmed** — discovered locally AND matches a community pattern; highest confidence
- **Universal** — found in 3+ repos across calibration; bundled in the pip package as defeasible priors; decays to zero influence when sufficient local baselines exist

---

## 8. Confidence, Drift, and Slow Change

The system explicitly acknowledges that:
- early history is incomplete
- baselines evolve
- slow drift may normalize undesirable behavior

Therefore:
- confidence is always contextual
- signals may carry uncertainty metadata
- long‑horizon comparison is a first‑class concern
- lack of alerts does not imply safety

---

## 9. Evidence Enables Action

A report that says "something is wrong" without actionable detail creates anxiety, not value.

The system ensures that every advisory includes:
- **Specific event references** (which commits, which test runs, which scans)
- **Specific artifacts** (which files, which dependencies, which endpoints)
- **Temporal context** (when it started, how long it's been happening)
- **Historical comparison** (how the current state differs from the baseline)

This evidence is structured so that:
- Humans can investigate directly
- AI coding assistants can consume it for automated investigation
- No additional data gathering is required to begin diagnosis

---

## 10. Delivery Channels

The Evolution Engine is a **local-first product** that reaches users through multiple delivery channels, added iteratively in priority order.

```
┌──────────────────────────────────────────────┐
│              DELIVERY CHANNELS               │
│                                              │
│  Priority 1: CLI Tool (evo analyze .)        │
│     (local analysis, zero config,            │
│      HTML reports, pattern KB)               │
│                                              │
│  Priority 2: GitHub / GitLab CI Integration  │
│     (PR comments, check annotations,         │
│      evidence as build artifact)             │
│                                              │
│  Priority 3: IDE Extension                   │
│     (inline annotations, status bar,         │
│      evidence quick action)                  │
│                                              │
│  Priority 4: Web Dashboard                   │
│     ("normal vs now" visuals, timeline,      │
│      pattern catalog, evidence browser)      │
│                                              │
│  Priority 5: API Service (SaaS)              │
│     (webhook ingestion, REST endpoints,      │
│      multi‑repo, multi‑tenant)               │
└──────────────────────────────────────────────┘
```

### Delivery Principles

- **Local-first** — all analysis runs on the user's machine; no data leaves by default
- **CLI is the primary interface** — `evo analyze .` with zero config
- **CI integration is never blocking** — advisory only, never a gate
- **All channels consume the same engine** — no channel‑specific logic in core
- **Evidence format is channel‑agnostic** — structured JSON consumed by all renderers

### Adapter Ecosystem

The system supports three tiers of adapter discovery:

- **Tier 1 (File-based)**: Detect adapters from repository files (`.git/`, lockfiles, config files). Always works offline.
- **Tier 2 (API-enriched)**: Optional tokens unlock CI, deployment, and security data from hosted services.
- **Tier 3 (Plugins)**: Community adapters installed via `pip install evo-adapter-<name>`, auto-discovered through Python `entry_points`.

Third-party adapters must pass a **13-check certification gate** before publishing, validating contract compliance, event structure, JSON serialization, and attestation integrity.

---

## 11. Explicit Non‑Goals

To preserve trust and focus, the system does **not**:
- Ingest runtime telemetry, raw logs, or traces
- Perform real‑time enforcement or block CI
- Produce universal health or risk scores
- Infer developer intent or semantics
- Replace code review or human decision‑making
- Act as a general observability platform
- Recommend specific code changes (evidence enables external tools to do this)

---

## 12. Relationship to Other Documents

This document defines **vision and boundaries**.

- Core Contract documents define hard guarantees and interfaces
- Family Contract documents define source‑specific event semantics
- Research documents capture exploration and rationale
- Design documents describe how components are built
- Implementation Plan tracks execution order, milestones, and delivery channels

When conflicts arise:
> Architecture Vision > Phase Contracts > Family Contracts > Design > Implementation > Research

---

## 13. Architectural Invariant

> **The Evolution Engine application is a deterministic, memory‑based system that reduces risk by observing how trusted systems evolve, learning what is structurally normal, discovering and remembering cross‑source patterns, and escalating unexpected change to humans with evidence sufficient to act.**

This invariant must never be violated.
