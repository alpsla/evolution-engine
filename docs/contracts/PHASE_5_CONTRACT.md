# Phase 5 — Advisory & Evidence Layer Contract

> **Normative Contract**
>
> This document defines the guarantees, boundaries, and invariants of **Phase 5 (Advisory & Evidence Layer)** of the Evolution Engine.
> It is binding for all Phase 5 implementations. If implementation or design conflicts with this document, the implementation is incorrect.

---

## 1. Purpose

Phase 5 exists to:

> **Compile current signals, pattern context, and historical knowledge into user‑facing advisories with enough specific evidence for the user or their AI assistant to investigate and act immediately.**

Phase 5 is the **presentation and evidence compilation layer**. It does not analyze, judge, or recommend.

---

## 2. Inputs (Strict)

Phase 5 MAY read:
- Phase 2 deviation signals (current state)
- Phase 3 explanations (human‑readable context)
- Phase 4 knowledge artifacts (historical pattern context)
- Phase 1 event metadata (for evidence traceability — read‑only)

Phase 5 MUST NOT read:
- Source systems or adapters directly
- External services for analysis
- Human preferences for prioritization

Phase 5 MUST NOT perform:
- New analytical computation
- Pattern discovery (that is Phase 4)
- Signal aggregation or scoring (no "health score")

---

## 3. Outputs (Canonical)

Phase 5 emits **Advisory Reports** and **Evidence Packages**.

### 3.1 Advisory Report

An Advisory Report presents the current state of a monitored system in three layers:

| Layer | Question It Answers | Source |
|-------|-------------------|--------|
| **Current State** | "What changed compared to normal?" | Phase 2 signals + Phase 3 explanations |
| **Pattern Context** | "Have we seen this combination before?" | Phase 4 knowledge artifacts |
| **Evidence Detail** | "What specific artifacts are involved?" | Phase 1 event metadata + Phase 2 signal refs |

### 3.2 Evidence Package

An Evidence Package is a structured, exportable data object containing specific, actionable references. It is designed to be consumed by:
- Humans investigating directly
- AI coding assistants (ChatGPT, Claude, Copilot, etc.)
- Automated tooling

---

## 4. Advisory Report Shape

```json
{
  "advisory_id": "<content-addressable-id>",
  "scope": "<repository-or-project-id>",
  "generated_at": "<ISO-8601>",
  "period": {
    "from": "<ISO-8601>",
    "to": "<ISO-8601>"
  },
  "summary": {
    "significant_changes": 3,
    "families_affected": ["schema", "testing", "dependency"],
    "known_patterns_matched": 1,
    "new_observations": 1
  },
  "changes": [
    {
      "family": "schema",
      "metric": "endpoint_count",
      "normal": {"mean": 12.0, "stddev": 2.6},
      "current": 18,
      "deviation_stddev": 2.3,
      "description": "API surface grew from ~12 to 18 endpoints in 2 weeks — 2.3x faster than usual growth rate."
    }
  ],
  "pattern_matches": [
    {
      "knowledge_id": "<id>",
      "pattern_name": "API expansion outpacing test coverage",
      "confidence": "approved",
      "seen_count": 47,
      "typical_duration": "2-4 weeks",
      "description": "Rapid API surface growth accompanied by rising test failures and dependency additions."
    }
  ],
  "evidence": "<evidence-package>"
}
```

---

## 5. Evidence Package Shape

```json
{
  "evidence_id": "<content-addressable-id>",
  "advisory_ref": "<advisory_id>",
  "commits": [
    {
      "sha": "<commit-hash>",
      "message": "<commit message>",
      "author": "<name>",
      "timestamp": "<ISO-8601>",
      "files_changed": ["<path>", "<path>"]
    }
  ],
  "files_affected": [
    {
      "path": "<file-path>",
      "change_type": "created | modified | deleted",
      "first_seen_in": "<commit-sha>"
    }
  ],
  "tests_impacted": [
    {
      "name": "<test-name>",
      "status_before": "passed",
      "status_now": "failed",
      "since_commit": "<commit-sha>"
    }
  ],
  "dependencies_changed": [
    {
      "name": "<package-name>",
      "change": "added | removed | upgraded",
      "version": "<version>"
    }
  ],
  "timeline": [
    {
      "timestamp": "<ISO-8601>",
      "family": "<source-family>",
      "event": "<brief description>"
    }
  ]
}
```

The Evidence Package MUST contain only data already present in Phase 1/2/3.
It MUST NOT introduce new analysis or derived facts.

---

## 6. Presentation Formats

Phase 5 MUST support multiple output formats:

| Format | Use Case | Description |
|--------|----------|-------------|
| **Structured JSON** | API consumption, AI assistants | Full advisory + evidence |
| **Human Summary** | Dashboard, email digest | "Normal vs now" comparisons with visual metaphors |
| **Chat Format** | Telegram, Slack, Discord | Conversational, compact, platform‑appropriate |

### 6.1 Human Summary Requirements

The human summary MUST:
- show "normal" vs "current" for each significant change
- use comparative language ("typically X, now Y")
- include magnitude context ("2.3x faster than usual")
- avoid technical jargon (no "standard deviations" in user‑facing text)
- present pattern matches as historical context, not warnings

### 6.2 Evidence Export Requirements

The evidence package MUST:
- be self‑contained (no external lookups needed to understand it)
- reference specific artifacts (commit SHAs, file paths, test names)
- include a timeline of relevant events
- be formatted for easy consumption by AI coding assistants

---

## 7. Investigation Prompt (Optional Enhancement)

Phase 5 MAY include a pre‑built investigation prompt alongside the evidence package:

```
"Here is a structural analysis of [project] over the last [period].
[evidence package]. Based on this evidence, identify the most likely
root cause of [observed changes] and suggest specific files to review."
```

This prompt is a **convenience feature**, not an analytical output. The system does not execute the prompt — it provides it for the user to use with their preferred AI tool.

---

## 8. Invariants

All Phase 5 implementations MUST satisfy:

1. **No judgment** — advisories describe changes, not quality
2. **No recommendations** — Phase 5 never suggests specific fixes
3. **No scoring** — no "health score," "risk level," or traffic lights
4. **Evidence completeness** — every claimed change must link to specific artifacts
5. **Presentation neutrality** — same information, different formats; no format‑dependent analysis
6. **No new analysis** — Phase 5 compiles and presents; it does not compute

Violations are considered critical defects.

---

## 9. What Phase 5 Is NOT

Phase 5 is NOT:
- A recommendation engine ("you should fix X")
- A prioritization system ("fix this first")
- A blocking gate ("deployment denied")
- An AI assistant ("let me investigate for you")
- A scoring dashboard ("project health: 73%")

Phase 5 IS:
- A compilation layer (assembles information from Phases 2, 3, 4)
- An evidence curator (selects relevant artifacts)
- A presentation engine (formats for different consumers)
- An enabler of external investigation (provides enough for AI tools to help)

---

## 10. Relationship to Other Phases

- Phase 2 provides current deviation signals
- Phase 3 provides human‑readable explanations
- Phase 4 provides pattern context and historical knowledge
- Phase 1 provides event metadata for evidence traceability
- Phase 5 compiles all of these into user‑facing output

Phase 5 MUST NOT feed back into any earlier phase.
Phase 5 outputs are terminal — they leave the system.

---

> **Invariant Summary:**
> Phase 5 presents evidence clearly enough for the user — or their AI assistant — to act. It never tells them what to do.
