# Phase 3 — LLM Role Analysis

> **Research Document**
>
> This analysis evaluates how much of Phase 3 (Explanation Layer) could be performed
> by an LLM rather than predefined template rules, while remaining fully compliant
> with `PHASE_3_CONTRACT.md` and `ARCHITECTURE_VISION.md`.
>
> **Conclusion in brief:** The LLM's role in Phase 3 is significantly larger than
> the current design suggests. The design undervalues LLM capability within the
> existing contract constraints. However, the contract's safety rails are exactly
> right — the question is not whether to loosen them, but how much more an LLM
> can do *within* them.

---

## 1. Current Design: LLM as Paraphrase Engine

The current Phase 3 Design defines two rendering modes:

- **Mode A (Template):** Fill-in-the-blank deterministic templates. Required.
- **Mode B (Template + LLM):** LLM "paraphrases" the template output. Optional.

This frames the LLM as a **cosmetic layer** — it makes templates sound nicer.

This is the weakest possible use of an LLM. It's safe, but it dramatically
underestimates what an LLM can contribute without violating any contract invariant.

---

## 2. What Templates Do Well

Templates are reliable for:

- **Numeric fill-in:** "This change touched **{observed} files**"
- **Binary branching:** Different phrasing for high vs low deviation
- **Confidence qualifiers:** Appending "based on limited history" when accumulating
- **Consistent structure:** Every explanation follows the same shape

Templates are appropriate when:
- The explanation is structurally identical every time
- Only the numbers change
- The audience doesn't need context beyond the immediate signal

---

## 3. What Templates Cannot Do

Templates fail or become unwieldy when:

| Challenge | Why Templates Struggle |
|-----------|----------------------|
| **Contextual variation** | The 200th "touched more files than usual" is noise, not signal |
| **Baseline characterization** | Describing *what kind of repo this is* from baseline statistics |
| **Comparative framing** | "This is the widest change since commit abc, 3 weeks ago" |
| **Edge case narration** | First-ever explanation, baseline just crossed to "sufficient", perfect streak broken |
| **Multi-metric coherence** | When 4 metrics fire for one commit, templates can't make them read as a coherent story |
| **Magnitude calibration** | Distinguishing 1.5σ (mildly unusual) from 8σ (unprecedented) in tone |
| **Uncertainty narration** | Authentically conveying "we're not sure yet" beyond boilerplate |
| **Adaptive detail** | More context for extreme deviations, less for mild ones |

To cover these cases with templates requires **combinatorial explosion** —
hundreds of template variants for edge cases, metric combinations, deviation
magnitudes, confidence states, and audience contexts.

An LLM handles all of these naturally.

---

## 4. The Contract-Compliant LLM Spectrum

The Phase 3 Contract (Section 8) permits LLM usage under strict constraints:

> **LLMs MUST be provided only:**
> - the Phase 2 signal
> - referenced Phase 1 event metadata
> - an explicit explanation template or instruction
>
> **LLMs MUST NOT:**
> - infer intent
> - add new facts
> - generalize beyond the provided data

This is more permissive than the Design realizes. Here is the full spectrum
of what an LLM can do within these constraints:

### 4.1 Tier 1 — Paraphrase (Current Design)

**What:** Reword a template's output.

**Example Input:**
> Template: "This change touched 14 files. Recent changes typically touched 3–5 files."

**LLM Output:**
> "This commit modified 14 files — substantially broader than the typical 3 to 5."

**Value:** Marginal. Slightly more readable.
**Risk:** Minimal.
**Contract compliance:** Full.

---

### 4.2 Tier 2 — Contextual Narration

**What:** Generate explanations that incorporate baseline characterization and
comparative framing, using *only* data from the signal and referenced events.

**Example Input:**
```json
{
  "signal": { "metric": "files_touched", "observed": 14, "baseline": { "mean": 3.4, "stddev": 1.2 }, "deviation": { "measure": 8.8, "unit": "stddev_from_mean" }, "confidence": { "sample_count": 50, "status": "sufficient" } },
  "event_metadata": { "commit_hash": "abc123", "message": "refactor auth module", "files": ["auth/login.py", "auth/session.py", ...], "authored_at": "2026-02-01T..." },
  "instruction": "Explain what changed and how it compares to history. Do not judge, recommend, or infer intent."
}
```

**LLM Output:**
> "This change modified 14 files across the auth directory. Over the last 50 changes,
> commits in this repository typically touched around 3 files (±1.2). At 8.8 standard
> deviations from the mean, this is the most structurally broad change in the
> observed history window."

**Value:** Significantly more informative than a template. The LLM contextualizes
the magnitude (8.8σ is *extreme*, not just "above average") and references the
actual files and directories involved.

**Risk:** Low — all facts are from the signal. The LLM describes what the numbers
mean, not what they imply.

**Contract compliance:** Full. No new facts, no judgment, no recommendations.
Every claim is traceable to the signal or event metadata.

---

### 4.3 Tier 3 — Historical Comparison

**What:** When provided with *additional Phase 1 event references* (e.g., the
last N events from the same window), the LLM can describe how the current
observation compares to specific historical events.

**Example Input (additional context):**
```json
{
  "historical_events": [
    { "event_ref": "evt_042", "files_touched": 12, "message": "migrate database schema", "authored_at": "2026-01-15" },
    { "event_ref": "evt_019", "files_touched": 8, "message": "add logging infrastructure", "authored_at": "2025-12-01" }
  ]
}
```

**LLM Output:**
> "This change touched 14 files — the broadest in the current observation window.
> The most comparable change was a database schema migration on January 15th,
> which touched 12 files. Most other changes in this period modified 2–5 files."

**Value:** High. Humans naturally want to know "has anything like this happened
before?" Templates cannot answer this without enumerating every possible comparison.

**Risk:** Medium-low. The LLM must be constrained to only reference events
explicitly provided. A validation step can verify that all cited event_refs exist
in the input.

**Contract compliance:** Full, per Section 2: "Phase 3 MAY read Phase 1 event
references *only as cited evidence* (read-only)."

---

### 4.4 Tier 4 — Adaptive Explanation Depth

**What:** The LLM adjusts explanation depth based on deviation magnitude
and confidence state, producing richer output for unusual situations and
terser output for unremarkable ones.

**Mild deviation (1.2σ):**
> "This change touched 5 files, slightly above the usual 3–4."

**Extreme deviation (8.8σ):**
> "This change modified 14 files across 5 directories — significantly broader
> than any change in the last 50 observations. The established baseline for this
> repository shows a mean of 3.4 files (σ=1.2), placing this change at 8.8
> standard deviations from the norm. The last change of comparable breadth was
> a schema migration 3 weeks ago (12 files)."

**Value:** Very high. Template systems produce the same verbosity regardless of
significance. An LLM naturally calibrates detail to deviation magnitude — which
is exactly how humans communicate relevance.

**Risk:** Low. The LLM is still working from the same data. It's choosing *how much*
to say, not *what* to say.

**Contract compliance:** Full. The contract requires explanations to "preserve
numeric values from Phase 2 without alteration" and "include cited historical
context." It does not mandate uniform verbosity.

---

### 4.5 Tier 5 — Confidence-Aware Framing

**What:** Rather than appending a boilerplate disclaimer, the LLM weaves
confidence awareness into the explanation's structure and tone.

**Template approach:**
> "This change touched 14 files. Recent changes typically touched 3–5 files.
> *Note: This comparison is based on limited history and may change as more
> data becomes available.*"

**LLM approach (accumulating, 12 samples):**
> "Based on the 12 changes observed so far, this commit's 14-file scope is
> notably broader than the emerging pattern of 3–5 files. This baseline is
> still forming — the comparison will become more reliable as history accumulates."

**Value:** High. The template bolts on uncertainty as an afterthought. The LLM
integrates it into the explanation, which is how humans naturally communicate
qualified claims.

**Risk:** Low. The confidence status from Phase 2 is preserved ("still forming"
maps to "accumulating"), and the qualification is honest.

**Contract compliance:** Full, per Section 6: "Phase 3 MUST explain uncertainty
in plain language when confidence is not sufficient."

---

## 5. What the LLM Must NOT Do (Contract Red Lines)

These constraints are correct and should not be relaxed:

| Forbidden | Example Violation | Why It's Dangerous |
|-----------|------------------|--------------------|
| **Infer intent** | "This looks like a refactoring" | Phase 3 doesn't know intent; the commit message says "refactor" but the system must not interpret it |
| **Add facts** | "This directory contains test files" | Phase 3 has no file-content knowledge |
| **Judge quality** | "This change is concerning" | Judgment belongs to humans |
| **Recommend action** | "Consider splitting this into smaller commits" | Recommendations belong to Phase 5 |
| **Generalize** | "AI-generated code tends to touch more files" | No general claims about development patterns |
| **Suppress uncertainty** | Omitting confidence caveats for readability | Contract Section 6 explicitly forbids this |
| **Fabricate history** | "Changes like this usually precede bugs" | No causal claims without evidence |

---

## 6. Proposed Architecture: LLM-Primary, Template-Fallback

### Current Architecture (Design Document)
```
Phase 2 Signal → Template Rendering → [Optional LLM Paraphrase] → Explanation
```

### Proposed Architecture
```
Phase 2 Signal
     ↓
Context Assembly (unchanged)
     ↓
┌─────────────────────────────┐
│  Rendering Strategy Router  │
│                             │
│  IF LLM available:          │
│    → LLM Grounded Render    │
│    → Validation Gate        │─── REJECT if hallucination detected
│    → Explanation Object     │
│                             │
│  ELSE (fallback):           │
│    → Template Render        │
│    → Explanation Object     │
└─────────────────────────────┘
```

### Key Changes from Current Design

1. **LLM is the primary renderer** (not an optional enhancement)
2. **Templates become the fallback** (not the primary path)
3. **A validation gate** sits between LLM output and the explanation object
4. **The deterministic path is preserved** (contract invariant 5)

---

## 7. The Validation Gate (Critical Component)

If the LLM's role expands, validation becomes essential. The gate ensures
contract compliance by verifying:

### 7.1 Numeric Fidelity
Every numeric value in the explanation must match the Phase 2 signal exactly.

**Implementation:** Extract all numbers from LLM output, verify each appears
in the input signal. Reject if any number is absent from the source data.

### 7.2 Citation Verification
Every event reference in the explanation must exist in the provided context.

**Implementation:** Extract all event_ref or commit_hash mentions from LLM output,
verify each appears in the input context. Reject if any citation is fabricated.

### 7.3 Forbidden Language Detection
The explanation must not contain judgment, recommendations, or alarm.

**Implementation:** Check for forbidden terms from the contract:
- Risk labels: "risk", "dangerous", "concerning", "problematic"
- Recommendations: "should", "needs", "must", "consider"
- Judgment: "good", "bad", "correct", "incorrect"

### 7.4 Factual Boundary Check
The explanation must not introduce claims that aren't derivable from the input.

**Implementation:** This is the hardest check. A lightweight approach:
- Compare LLM output against template output
- Any claim present in LLM output but absent from template output is suspicious
- Flag for review or reject

### 7.5 Fallback on Rejection
If the LLM output fails any validation gate, the system falls back to
template rendering. This preserves the contract's deterministic guarantee
and ensures the system never produces an invalid explanation.

---

## 8. LLM Selection Considerations

### 8.1 Local vs Cloud

| Factor | Local (e.g., Ollama) | Cloud (e.g., OpenAI/Claude API) |
|--------|---------------------|--------------------------------|
| **Latency** | ~1-5s per explanation | ~0.5-2s per explanation |
| **Cost** | Hardware only | Per-token |
| **Privacy** | Full control | Data leaves the machine |
| **Determinism** | More reproducible (fixed seed) | Less reproducible |
| **Quality** | Adequate for grounded narration | Superior for nuance |
| **Offline** | Works without internet | Requires connectivity |

**Recommendation:** Start with cloud API (quality matters for trust). Add local
fallback for offline use. Both behind the same interface.

### 8.2 Model Requirements

Phase 3's LLM needs are modest:
- **Input:** Structured JSON (small — typically <1KB per signal)
- **Output:** 1-3 sentences per explanation
- **Reasoning:** Low complexity (no chain-of-thought needed)
- **Instruction following:** High (must respect constraints strictly)

This means:
- A small, fast model is sufficient (e.g., GPT-4o-mini, Claude Haiku, Llama 3.x 8B)
- Large reasoning models are overkill
- Cost per explanation will be minimal (<$0.001)

### 8.3 Temperature & Reproducibility

- **Temperature 0** for maximum reproducibility
- **System prompt** encodes contract constraints
- **Same input → near-identical output** (not byte-identical, but semantically stable)

Note: This means LLM-rendered explanations are **near-deterministic but not
perfectly deterministic**. The contract requires a fully deterministic path
(templates), which serves as the reproducibility guarantee.

---

## 9. Concrete Responsibilities: LLM vs Template

### Phase 3 Task Breakdown

| Task | Template | LLM | Notes |
|------|----------|-----|-------|
| **Numeric fill-in** | ✅ Primary | ❌ Unnecessary | Templates are perfect for this |
| **Deviation magnitude description** | ⚠️ Adequate | ✅ Superior | LLM calibrates language to magnitude naturally |
| **Baseline characterization** | ❌ Poor | ✅ Strong | "This repo typically sees small, focused changes" |
| **Historical comparison** | ❌ Cannot | ✅ Strong | "The last change this broad was 3 weeks ago" |
| **Confidence narration** | ⚠️ Boilerplate | ✅ Strong | LLM weaves uncertainty into the explanation |
| **Edge case handling** | ❌ Combinatorial | ✅ Natural | First explanation, baseline transition, etc. |
| **Multi-metric coherence** | ❌ Cannot | ✅ Possible | Multiple signals for one commit read coherently |
| **Adaptive verbosity** | ❌ Cannot | ✅ Natural | More detail for extreme deviations |
| **Audit/reproducibility** | ✅ Perfect | ⚠️ Near-deterministic | Template is the reproducibility anchor |

### Summary

- **Templates win at:** reproducibility, numeric accuracy, minimal computation
- **LLMs win at:** contextual narration, adaptive detail, historical comparison,
  edge cases, natural uncertainty communication
- **Neither wins alone:** The system needs both, with the LLM as primary and
  template as fallback/audit anchor

---

## 10. Estimated LLM Contribution to Phase 3

Based on the analysis above, here is an estimate of how much of Phase 3's
explanatory power can be LLM-driven:

```
┌──────────────────────────────────────────────────────┐
│                  Phase 3 Capability                  │
│                                                      │
│  ████████████████████░░░░░░░░░  LLM-Driven: ~70%    │
│  ░░░░░░░░░░░░░░░░░░░████████░  Template-Only: ~25%  │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░██  Shared/Both: ~5%     │
│                                                      │
│  LLM handles: narration, comparison, adaptation,     │
│  confidence framing, edge cases, coherence            │
│                                                      │
│  Templates handle: numeric accuracy anchor,           │
│  deterministic fallback, audit/reproducibility        │
└──────────────────────────────────────────────────────┘
```

**~70% of Phase 3's explanatory value** can be delivered by a constrained LLM.

The remaining **~25%** (template infrastructure) is not wasted — it serves as:
- The fallback when LLM is unavailable
- The validation reference for LLM output
- The reproducibility guarantee required by the contract

---

## 11. Risks of LLM-Primary Phase 3

| Risk | Mitigation |
|------|-----------|
| **Hallucination** | Validation gate + template fallback |
| **Inconsistency** | Temperature 0 + structured input |
| **API dependency** | Local model fallback |
| **Cost** | Small model, short outputs, ~$0.001/explanation |
| **Latency** | Batch rendering, async processing |
| **Contract violation** | Automated forbidden-language detection |
| **Trust erosion** | Every LLM explanation links to its template equivalent |

---

## 12. Recommended Implementation Approach

### Phase 3.0 — Template Foundation (Do First)
1. Implement template-based rendering for all metrics
2. Validate against contract
3. This becomes the permanent fallback and audit reference

### Phase 3.1 — LLM Grounded Render (Do Second)
1. Add LLM rendering path (behind feature flag)
2. Implement validation gate
3. A/B test LLM vs template output quality
4. LLM receives: signal + event metadata + system instruction

### Phase 3.2 — Historical Comparison (Do Third)
1. Extend context assembly to include relevant historical events
2. LLM receives: signal + event + historical comparisons
3. Produces richer comparative explanations

### Phase 3.3 — Adaptive Depth (Do Fourth)
1. LLM adjusts verbosity to deviation magnitude
2. Terse for mild deviations, detailed for extreme ones
3. Validate that confidence handling scales accordingly

---

## 13. Impact on Architecture

### What Changes
- Phase 3 gains an **optional external dependency** (LLM API)
- A **validation gate** becomes a new architectural component
- Template rendering shifts from **primary** to **fallback** role

### What Doesn't Change
- Phase 3 Contract: fully respected
- Architecture Vision: no violations
- Determinism guarantee: template path preserved
- Phase isolation: LLM receives only Phase 2 signals + Phase 1 references
- One-way data flow: LLM never writes back to earlier phases

### Contract Amendment Needed
The Phase 3 Contract (Section 8) should be updated to:
- Explicitly permit LLM as primary renderer (not just optional enhancer)
- Require the validation gate as a mandatory component
- Define validation gate criteria formally

---

## 14. Final Assessment

The Phase 3 Design as written treats the LLM as a cosmetic afterthought.
This is architecturally conservative but functionally limiting.

**The contract already permits a much larger LLM role.** The constraints in
Section 8 are well-designed safety rails that prevent the real dangers
(hallucination, judgment, recommendations) without preventing the real value
(contextual narration, adaptive depth, historical comparison).

The recommended approach:
1. **Build templates first** — they are the safety net and audit anchor
2. **Build LLM rendering second** — behind a validation gate
3. **Make LLM primary** — once the validation gate is proven reliable
4. **Keep templates forever** — as fallback and reproducibility guarantee

This gives Phase 3 the explanatory power of an LLM with the trust guarantees
of a deterministic system.

---

> **Summary:**
> The LLM's role in Phase 3 is not "paraphrase" — it is **grounded narration**.
> Templates provide the safety net. The LLM provides the understanding.
> Together, they satisfy the contract's dual mandate: trust and communication.
