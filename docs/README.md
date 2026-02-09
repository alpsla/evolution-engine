# Documentation Structure & Authority

This directory contains the architectural, contractual, and research documentation
for the Evolution Engine project.

Understanding **which documents are authoritative** is critical.

---

## Authority Order (Highest -> Lowest)

1. **ARCHITECTURE_VISION.md**
   The project constitution. Defines purpose, principles, boundaries, and phase definitions.

2. **Phase Contracts (`PHASE_*_CONTRACT.md`)**
   Normative guarantees and invariants for each major layer.
   - `PHASE_2_CONTRACT.md` -- behavioral baselines (measure)
   - `PHASE_3_CONTRACT.md` -- explanation layer (communicate)
   - `PHASE_4_CONTRACT.md` -- pattern learning (remember) -- with 4a/4b sub-layers
   - `PHASE_5_CONTRACT.md` -- advisory & evidence (inform)

3. **Adapter Contracts**
   - `ADAPTER_CONTRACT.md` -- universal adapter contract
   - `adapters/<family>/FAMILY_CONTRACT.md` -- family-specific contracts (8 families)
   - See `adapters/README.md` for the full world map, correlation diagram, and priority.

4. **Design Documents (`*_DESIGN.md`)**
   Implementation approaches that must conform to the contracts.
   - `PHASE_2_DESIGN.md` -- behavioral baselines design
   - `PHASE_3_DESIGN.md` -- explanation layer design (with 3.1 evolution)
   - `PHASE_4_DESIGN.md` -- pattern learning design (KB schema, fingerprinting, lifecycle)
   - `PHASE_5_DESIGN.md` -- advisory & evidence design (formats, evidence packages)

5. **IMPLEMENTATION_PLAN.md**
   Execution order, milestone tracking, and next actionable steps.

6. **Research (`docs/Research/`)**
   Exploratory work and historical context. Informative but not binding.
   - `Engine_Abstract_Base.md` -- core contract & truth source classification
   - `Phase_3_LLM_Role_Analysis.md` -- LLM role in explanation
   - `Phase_4_5_Architecture_Brainstorm.md` -- Phase 4/5 architecture decisions

7. **Archive (`docs/archive/`)**
   Superseded documents retained for traceability.
   - `ARCHITECTURE_v0.md` -- original v0 architecture (superseded by `ARCHITECTURE_VISION.md`)
   - `PROJECT_VISION_AND_MILESTONES_v0.md` -- original milestone map (superseded by `IMPLEMENTATION_PLAN.md`)
   - `PHASE_1_DESIGN.md` -- Phase 1 design (completed, archived)

8. **External Reviews (`docs/`)**
   - `EXTERNAL_REVIEW_2026_02_06.md` -- architectural review snapshot

---

## Conflict Resolution Rule

If two documents conflict:

> Architecture Vision -> Phase Contracts -> Adapter Contracts -> Design -> Implementation -> Research

Lower-authority documents must be updated or archived.

---

## Phase Overview

| Phase | Name | Status | Purpose |
|-------|------|--------|---------|
| 1 | Observation | Done | Record immutable events from truth sources |
| 2 | Baselines | Done | Measure deviation from historical behavior (MAD/IQR) |
| 3 | Explanation | Done | Translate signals into human language |
| 3.1 | LLM Enhancement | Done | Improve explanations with bounded LLM |
| 4 | Pattern Learning | Done | Discover and remember cross-source patterns |
| 4a | -> Algorithmic | Done | Correlation, lift, presence-based discovery |
| 4b | -> Semantic | Done | LLM-assisted pattern interpretation |
| 5 | Advisory | Done | User-facing reports + evidence packages |

## Implementation Status

| # | Component | Status | Key Files |
|---|-----------|--------|-----------|
| 1 | 5-Phase Pipeline | Done | `phase1_engine.py` - `phase5_engine.py` |
| 2 | 8 Adapter Families | Done | `adapters/git/`, `ci/`, `dependency/`, etc. |
| 3 | Git History Walker | Done | `adapters/git/git_history_walker.py` |
| 4 | GitHub API Adapters | Done | `adapters/ci/`, `deployment/`, `security/` |
| 5 | Data Quality (6-wave fix) | Done | MAD/IQR baselines, degenerate handling |
| 6 | Calibration Toolkit | Done | `examples/calibrate_repo.py`, `batch_calibrate.py` |
| 7 | Adapter Auto-Detection | Done | `registry.py` (Tier 1/2/3) |
| 8 | CLI Tool | Done | `cli.py`, `orchestrator.py` |
| 9 | Knowledge Base | Done | `knowledge_store.py` (SQLite) |
| 10 | KB Export/Import | Done | `kb_export.py`, `kb_security.py` |
| 11 | Universal Patterns | Done | `data/universal_patterns.json` |
| 12 | Report Generator | Done | `report_generator.py` (HTML) |
| 13 | Adapter Ecosystem | Done | `adapter_validator.py`, `adapter_scaffold.py` |
| 14 | License Gating | Done | `license.py` |
| 15 | Test Suite | Done | 246 tests (unit + integration) |
| 16 | Packaging & Distribution | Pending | Cython compilation, wheel building |
| 17 | CI Integration Channel | Pending | PR comments, check annotations |
| 18 | Community KB Sync Server | Pending | Registry service for pattern sharing |

## Delivery Channels

| Priority | Channel | Status | Description |
|----------|---------|--------|-------------|
| 1 | CLI Tool (`evo`) | Done | `evo analyze .`, zero-config, HTML reports |
| 2 | GitHub / GitLab CI | Pending | PR comments, check annotations, evidence artifacts |
| 3 | IDE Extension | Pending | Inline annotations, status bar, quick actions |
| 4 | Web Dashboard | Pending | Visual "normal vs now", timeline, pattern catalog |
| 5 | API Service (SaaS) | Pending | REST API, webhook ingestion, multi-tenant |

---

## Guiding Principle

> **Clarity beats cleverness.**
>
> If it is not obvious which document to trust, the documentation has failed.
