# Documentation Structure & Authority

This directory contains the architectural, contractual, and research documentation
for the Evolution Engine project.

Understanding **which documents are authoritative** is critical.

---

## Authority Order (Highest → Lowest)

1. **ARCHITECTURE_VISION.md**  
   The project constitution. Defines purpose, principles, boundaries, and phase definitions.

2. **Phase Contracts (`PHASE_*_CONTRACT.md`)**  
   Normative guarantees and invariants for each major layer.
   - `PHASE_2_CONTRACT.md` — behavioral baselines (measure)
   - `PHASE_3_CONTRACT.md` — explanation layer (communicate)
   - `PHASE_4_CONTRACT.md` — pattern learning (remember) — with 4a/4b sub‑layers
   - `PHASE_5_CONTRACT.md` — advisory & evidence (inform)

3. **Adapter Contracts**  
   - `ADAPTER_CONTRACT.md` — universal adapter contract
   - `adapters/<family>/FAMILY_CONTRACT.md` — family‑specific contracts (8 families)
   - See `adapters/README.md` for the full world map, correlation diagram, and priority.

4. **Design Documents (`*_DESIGN.md`)**  
   Implementation approaches that must conform to the contracts.
   - `PHASE_2_DESIGN.md` — behavioral baselines design
   - `PHASE_3_DESIGN.md` — explanation layer design (with 3.1 evolution)
   - `PHASE_4_DESIGN.md` — pattern learning design (KB schema, fingerprinting, lifecycle)
   - `PHASE_5_DESIGN.md` — advisory & evidence design (formats, evidence packages)

5. **IMPLEMENTATION_PLAN.md**  
   Execution order, milestone tracking, and next actionable steps.

6. **Research (`docs/Research/`)**  
   Exploratory work and historical context. Informative but not binding.
   - `Engine_Abstract_Base.md` — core contract & truth source classification
   - `Phase_3_LLM_Role_Analysis.md` — LLM role in explanation
   - `Phase_4_5_Architecture_Brainstorm.md` — Phase 4/5 architecture decisions

7. **Archive (`docs/archive/`)**  
   Superseded documents retained for traceability.
   - `ARCHITECTURE_v0.md` — original v0 architecture (superseded by `ARCHITECTURE_VISION.md`)
   - `PROJECT_VISION_AND_MILESTONES_v0.md` — original milestone map (superseded by `IMPLEMENTATION_PLAN.md`)
   - `PHASE_1_DESIGN.md` — Phase 1 design (completed, archived)

8. **External Reviews (`docs/`)**  
   - `EXTERNAL_REVIEW_2026_02_06.md` — architectural review snapshot

---

## Conflict Resolution Rule

If two documents conflict:

> Architecture Vision → Phase Contracts → Adapter Contracts → Design → Implementation → Research

Lower‑authority documents must be updated or archived.

---

## Phase Overview

| Phase | Name | Status | Purpose |
|-------|------|--------|---------|
| 1 | Observation | ✅ | Record immutable events from truth sources |
| 2 | Baselines | ✅ | Measure deviation from historical behavior |
| 3 | Explanation | ✅ | Translate signals into human language |
| 3.1 | LLM Enhancement | ✅ | Improve explanations with bounded LLM |
| 4 | Pattern Learning | ✅ | Discover and remember cross‑source patterns |
| 4a | → Algorithmic | ✅ | Statistical correlation discovery |
| 4b | → Semantic | ✅ | LLM‑assisted pattern interpretation (Sonnet 4.5) |
| 5 | Advisory | ✅ | User‑facing reports + evidence packages |

## Immediate Priorities (Calibration & Product)

| # | Task | Status | Purpose |
|---|------|--------|---------|
| 1 | Git History Walker Adapter | ⏳ | Extract lockfiles/configs from past commits → unlock 3+ families |
| 2 | GitHub API Adapter | ⏳ | Fetch CI runs, releases, security → unlock 3+ families |
| 3 | Calibration Repo Search | ⏳ | Find repos with 4+ family data coverage |
| 4 | Multi‑Family Calibration | ⏳ | First real cross‑family pattern discovery |
| 5 | Fix Verification Loop | ⏳ | Verify user fixes resolved flagged issues |
| 6 | Report Generator (HTML/PDF) | ⏳ | Consulting‑ready deliverable |
| 7 | Marketing Materials | ⏳ | One‑pager, sample report, demo script |

## Calibration Status

| Finding | Status |
|---------|--------|
| Pipeline works end‑to‑end (Phases 1–5) | ✅ Validated (6,713 commits) |
| Phase 5 advisory output quality | ✅ Production‑ready |
| LLM integration scales | ✅ 26K explanations in 2 min |
| Pattern discovery with multi‑family data | ⏳ Blocked on Priority 1 & 2 |

## Delivery Channels (After Calibration)

| Priority | Channel | Status | Description |
|----------|---------|--------|-------------|
| 1 | GitHub / GitLab CI | ⏳ | PR comments, check annotations, evidence artifacts |
| 2 | API Service (SaaS) | ⏳ | REST API, webhook ingestion, multi‑tenant |
| 3 | Web Dashboard | ⏳ | Visual "normal vs now", timeline, pattern catalog |
| 4 | IDE Extension | ⏳ | Inline annotations, status bar, quick actions |
| 5 | CLI Tool | ⏳ | Local analysis, pipeline scripting |

---

## Guiding Principle

> **Clarity beats cleverness.**
> 
> If it is not obvious which document to trust, the documentation has failed.
