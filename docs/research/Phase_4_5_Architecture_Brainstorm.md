# Phase 4/5 Architecture Brainstorm — Research Document

> **Research Document — February 7, 2026**
>
> Captures the key architectural decisions made during the Phase 4/5 brainstorm session.
> This document is informative, not binding. Decisions formalized here are enacted
> through updates to contracts, design documents, and the implementation plan.

---

## Context

With all 8 source families implemented through Phase 1 → Phase 2 → Phase 3/3.1,
the system produces 162+ deviation signals across 7 families and renders them as
LLM-enhanced explanations. The question: **what comes next?**

---

## Key Decisions

### 1. Phase 4 Has Two Distinct Operations

Phase 4 is not a single engine. It performs two fundamentally different activities
that require different tools:

| Operation | Name | Input | Tool | Nature |
|-----------|------|-------|------|--------|
| **4a** | Pattern Matcher | Phase 2 signals (numbers) | Algorithm | Deterministic, fast |
| **4b** | Pattern Interpreter | Candidates + Phase 3 explanations | LLM | Non-deterministic, bounded |

**Phase 4a discovers.** It finds statistical co-occurrences, temporal sequences,
and structural alignments across signals. It uses correlation coefficients, not intuition.

**Phase 4b interprets.** It takes a statistical finding ("signals X, Y, Z co-occur")
and produces a semantic description ("API expansion outpacing test coverage").
It reads Phase 3 explanations as context — this is why Phase 3 exists for the machine,
not just for humans.

**Cascade with declining confidence:**
- Math finds pattern → high confidence candidate
- Math finds nothing → LLM may propose hypothesis → LOW confidence, requires MORE evidence
- Neither finds anything → honest "nothing notable" — no forced insights

### 2. Phase 3 Serves Double Duty

Phase 3 is NOT just a display layer. It serves two consumers:
- **Humans:** readable explanations of individual signals
- **Phase 4b:** natural language context for the LLM to reason about patterns

This resolves the question: "If Phase 4 reads Phase 2 directly, why do we need Phase 3?"
Answer: Phase 4a reads Phase 2 (numbers). Phase 4b reads Phase 3 (language). Both are needed.

### 3. Knowledge Base Architecture

**Start with SQLite** for local-only mode (single repo).
**Graduate to PostgreSQL + pgvector** when cross-account patterns matter.

The KB stores Knowledge Artifacts — each containing BOTH:
- Statistical evidence (from 4a): correlation strength, occurrence count
- Semantic description (from 4b): what the pattern means in English

Abstract behind a `KnowledgeStore` interface so the backend is swappable.

### 4. Universal Phase 4a Parameters

Pattern discovery uses a small set of universal parameters, not per-metric rules:

| Parameter | Purpose | Example |
|-----------|---------|---------|
| `min_support` | Minimum co-occurrences for candidacy | 10 |
| `min_correlation` | Minimum correlation strength | 0.7 |
| `promotion_threshold` | Occurrences to promote to knowledge | 50 |
| `decay_window` | Time before unseen patterns lose confidence | 90 days |
| `semantic_multiplier` | Extra evidence needed for LLM-only hypotheses | 3x |

### 5. Phase 5 Is the Compilation Layer

Phase 5 compiles everything into user-facing output. It is NOT a new analytical engine.
It reads:
- Current Phase 2 signals (what's happening now)
- Phase 3 explanations (what it means)
- Phase 4 knowledge (have we seen this before?)

And produces: **Advisory + Evidence Package**

### 6. Evidence Packages Are Critical

The advisory alone ("failure rate is 11%") is a worry flag without actionable detail.
The evidence package provides specific commits, files, tests, and dependencies that
the user (or their AI coding assistant) can immediately investigate.

**Levels of evidence integration:**
1. Evidence Package Export (structured data the user can paste into any AI)
2. Pre-Built Investigation Prompt (ready-made prompt + evidence)
3. Integrated AI Investigation (we call an AI API with the evidence — future)

### 7. The System Detects Structural Deviation, Not Intent

The Evolution Engine does not detect "AI hallucination" directly. It detects
**structural signatures** that correlate with AI-influenced development:
- Higher dispersion, lower locality
- Dependency sprawl
- Test coverage gaps
- API surface explosion
- Commit pattern changes

The human (or their AI assistant) investigates the specific cause.
The system provides the evidence trail that makes investigation efficient.

---

## System Flow — Complete Picture

```
Sources → Phase 1 → Phase 2 → Phase 3 (+ 3.1 LLM)
                        │          │
                        │          └── Phase 4b reads (semantic context)
                        │
                        ├── Phase 4a reads (statistical discovery)
                        │       │
                        │       ├── KB lookup: known pattern?
                        │       │       YES → retrieve artifact
                        │       │       NO  → discover new correlation
                        │       │               │
                        │       │               ▼
                        │       │          Phase 4b: LLM interprets
                        │       │               │
                        │       │               ▼
                        │       │          Store in KB
                        │       │
                        │       ▼
                        │   Knowledge Base
                        │       │
                        ▼       ▼
                    Phase 5: Advisory
                    ├── Human Summary ("what changed vs normal")
                    ├── Pattern Context ("seen 47 times before")
                    └── Evidence Package (commits, files, tests)
                            │
                            ▼
                        HUMAN / AI ASSISTANT
```

---

## Implications for Existing Architecture

1. **Architecture Vision** needs updated phase definitions (4a/4b, Phase 5)
2. **Phase 4 Contract** needs the 4a/4b split, KB requirements, and cascade rules
3. **Phase 5 Contract** needs to be created (advisory + evidence package)
4. **Implementation Plan** needs complete rewrite reflecting current state
5. **Phase 3 role** is clarified — dual consumer (human + Phase 4b)

---

> **Summary:** The system discovers patterns algorithmically, interprets them
> semantically, remembers them in a knowledge base, and presents them to humans
> with enough evidence to act. The algorithm proposes, the LLM describes,
> the human approves.
