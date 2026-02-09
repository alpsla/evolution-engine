# Evolution Engine — Implementation Plan

> **Authoritative Execution Roadmap**
>
> This document translates the Architecture Vision and research findings into an explicit, ordered implementation plan.
> It answers *what we build*, *in what order*, and *why that order exists*.
>
> The plan is intentionally conservative: each step validates an architectural assumption before expanding scope.
>
> **Last updated:** February 9, 2026 (open-core pivot: local-first CLI, adapter registry, KB security, 148 tests)

---

## 0. Guiding Rules for This Plan

1. **Vision precedes contracts** — architectural intent is fixed before guarantees.
2. **Contracts precede design** — no phase is implemented without a formal contract.
3. **Design precedes implementation** — no code without a design document.
4. **Adapters precede engines** — no source may enter Phase 1 without an adapter.
5. **Phase purity is enforced** — each phase has one job.
6. **Correlation requires plurality** — no correlation work begins until at least two engines produce Phase 2 signals.
7. **Evidence enables action** — every user‑facing output must include enough detail to act on.
8. **Research informs priority, not parallelism** — we do not build everything at once.

---

## 1. Completed Foundations ✅

### Architecture & Authority
- ✅ Architecture Vision (Constitution) — updated with Phase 4/5 definitions
- ✅ Documentation authority model (`docs/README.md`)

### Contracts
- ✅ Source Adapter Contract (universal)
- ✅ Phase 2 Behavioral Baselines Contract
- ✅ Phase 3 Explanation Layer Contract
- ✅ Phase 4 Pattern Learning Contract — with 4a/4b split, KB design, cascade rules
- ✅ Phase 5 Advisory & Evidence Layer Contract

### Source Family Contracts (8 families)
- ✅ Version Control (`docs/adapters/git/`)
- ✅ CI / Build Pipeline (`docs/adapters/ci/`)
- ✅ Test Execution (`docs/adapters/testing/`)
- ✅ Dependency Graph / SBOM (`docs/adapters/dependency/`)
- ✅ Schema / API Evolution (`docs/adapters/schema/`)
- ✅ Deployment / Release (`docs/adapters/deployment/`)
- ✅ Configuration / IaC (`docs/adapters/config/`)
- ✅ Security Scanning (`docs/adapters/security/`)

### Design Documents
- ✅ Phase 2 Design
- ✅ Phase 3 Design (with 3.1 evolution)
- ✅ Phase 4 Design (signal fingerprinting, KB schema, lifecycle)
- ✅ Phase 5 Design (advisory format, evidence packages, chat format)

### Research
- ✅ Engine Abstract Base (core contract + truth source classification)
- ✅ Phase 3 LLM Role Analysis
- ✅ Phase 4/5 Architecture Brainstorm
- ✅ External Architectural Review

These elements are considered **stable**. Changes require explicit architectural review.

---

## 2. Phase 1 + 2 — Observation & Baselines ✅

### Phase 1 Engine ✅
- ✅ Source‑agnostic Phase 1 engine
- ✅ Universal dedup key (family‑aware, not Git‑only)
- ✅ Content‑addressable event storage
- ✅ `source_family` field in all events

### Phase 2 Engine ✅
- ✅ Git reference metrics (files_touched, dispersion, cochange, locality)
- ✅ Multi‑family metric engines (CI, testing, dependency, schema, deployment, config, security)
- ✅ `run_all()` method for all families
- ✅ Canonical one‑metric‑per‑signal output
- ✅ Cold‑start confidence handling

### Validated
- ✅ Determinism, replay, sensitivity (Git)
- ✅ 7 families through Phase 1 + Phase 2 pipeline (82 events → 162 signals)

---

## 3. Source Adapters — All Families ✅

| # | Family | Adapter | Status |
|---|--------|---------|--------|
| 1 | Version Control | `GitSourceAdapter` | ✅ Implemented (reference) |
| 2 | CI / Build Pipeline | `GitHubActionsAdapter` | ✅ Implemented |
| 3 | Test Execution | `JUnitXMLAdapter` | ✅ Implemented |
| 4 | Dependency Graph | `PipDependencyAdapter` | ✅ Implemented |
| 5 | Schema / API | `OpenAPIAdapter` | ✅ Implemented |
| 6 | Deployment / Release | `GitHubReleasesAdapter` | ✅ Implemented |
| 7 | Configuration / IaC | `TerraformAdapter` | ✅ Implemented |
| 8 | Security Scanning | `TrivyAdapter` | ✅ Implemented |

All adapters:
- conform to universal Adapter Contract
- conform to their family FAMILY_CONTRACT.md
- support fixture mode (for testing) and real‑source mode (for production)
- are organized in `evolution/adapters/<family>/`

### 3.1 Meta-Adapters — Git History Walker ✅

**Purpose:** Enable historical replay of dependency, schema, and config evolution by extracting file snapshots from git history.

- ✅ `GitHistoryWalker` meta-adapter (`evolution/adapters/git/git_history_walker.py`)
- ✅ Walks git commits (oldest → newest), extracts files at each commit SHA
- ✅ Feeds extracted content to existing family adapters (all via PipDependencyAdapter in fixture mode)
- ✅ **8 dependency lockfile formats** supported:
  - `go.sum`, `go.mod` → Go ecosystem
  - `package-lock.json`, `yarn.lock` → npm ecosystem
  - `Cargo.lock` → Cargo/Rust ecosystem
  - `Gemfile.lock` → Bundler/Ruby ecosystem
  - `requirements.txt`, `Pipfile.lock` → pip/Python ecosystem
- ✅ Schema: `openapi.yaml`, `openapi.yml`, `openapi.json`, `swagger.yaml`
- ✅ Config: `*.tf` (Terraform)
- ✅ Parser routing via `dependency_parsers` dict (file pattern → parser method)
- ✅ Links events to commits via `trigger.commit_sha` in payload
- ✅ Phase 1 `override_observed_at` parameter for temporal ordering
- ✅ Shallow clone safe (GitSourceAdapter handles missing parent objects)
- ✅ Calibration orchestrator (`examples/calibrate_repo.py`) wires all families together
- ✅ Parallel execution: concurrent API fetches + parallel Phase 2 families (`run_all_parallel()`)

**Validated on:**
- ✅ fastapi (Python) — 4,126 dependency events from requirements.txt, 500 CI + 254 deployment via API
- ✅ gin-gonic/gin (Go) — 500 dependency events from go.sum

**Files:**
- `evolution/phase1_engine.py` — `override_observed_at` parameter
- `evolution/adapters/git/git_history_walker.py` — Meta-adapter (451 lines)
- `evolution/adapters/git/git_adapter.py` — Shallow clone fix
- `examples/calibrate_repo.py` — Full 7-family calibration orchestrator
- `tests/test_git_history_walker.py` — Integration test suite
- `examples/run_git_history_walker.py` — Usage example

---

## 4. Phase 3 — Explanation Layer ✅

### Phase 3 (Deterministic) ✅
- ✅ Template‑based explanation engine
- ✅ Templates for all 23 metrics across all 8 families
- ✅ Confidence annotations
- ✅ Content‑addressable explanation IDs

### Phase 3.1 (LLM Enhanced) ✅
- ✅ Validation‑gated LLM renderer (OpenRouter)
- ✅ Preamble stripping
- ✅ Numeric fidelity validation
- ✅ Forbidden language detection
- ✅ Fallback to deterministic templates on validation failure
- ✅ End‑to‑end validated: 162/162 explanations LLM‑enhanced

---

## 5. Phase 4 — Pattern Learning & Knowledge Layer ✅

> **Status: Contract ✅ Design ✅ Implementation ✅ Complete**
>
> Phase 4 discovers cross‑family patterns, stores them in the Knowledge Base,
> accumulates evidence, promotes to knowledge artifacts, and decays stale patterns.

### 5.1 Knowledge Base Infrastructure ✅

- [x] `KnowledgeStore` abstract interface (`knowledge_store.py`)
- [x] SQLite backend (`SQLiteKnowledgeStore`) — full CRUD for patterns and knowledge
- [x] DB schema: `patterns`, `knowledge`, `pattern_signals`, `pattern_history`
- [x] Fingerprint index and lookup (exact match)
- [x] Audit log (all mutations recorded in `pattern_history`)

### 5.2 Phase 4a — Pattern Matcher ✅

- [x] Signal fingerprinting (`compute_fingerprint`, `classify_direction`)
- [x] KB lookup — fast path for batch fingerprint and per‑pattern fingerprint
- [x] Co‑occurrence detection — pairwise Pearson correlation across **commit-SHA-aligned** metric series
- [x] Cross‑family correlation via `_build_commit_index()` (maps event_id → commit_sha for all families)
- [x] Candidate Pattern Object creation with statistical descriptions

### 5.3 Phase 4b — Semantic Interpreter ✅

- [x] LLM prompt design (statistical finding + Phase 3 explanations → one‑sentence description)
- [x] Validation gate reuse (no judgment, no recommendations, length constraint)
- [x] Semantic description storage in Pattern Objects
- [x] Graceful fallback when LLM unavailable (pattern stored with `semantic: null`)

### 5.4 Pattern Lifecycle ✅

- [x] Evidence accumulation (`increment_pattern` on re‑occurrence)
- [x] Confidence tier progression (emerging → sufficient → approved)
- [x] Automatic promotion (threshold‑based, with confirmed/speculative distinction)
- [x] Decay logic (`get_decayed_patterns` + `expire_pattern`)
- [x] Duplicate promotion prevention (check existing knowledge before promoting)

### 5.5 Testing & Validation ✅

- [x] End‑to‑end: Phase 1 → 2 → 3 → 4 with all 7 families
- [x] Pattern discovery across 82 cross‑family pairs validated
- [x] Multi‑run accumulation and promotion cycle validated
- [x] Knowledge artifact creation from promoted patterns validated

### Exit Criteria — All Met
- ✅ KB stores and retrieves patterns correctly
- ✅ Phase 4a discovers patterns from multi‑family signal data
- ✅ Phase 4b enriches patterns with bounded semantic descriptions (when LLM enabled)
- ✅ Pattern lifecycle (discovery → accumulation → promotion) works end‑to‑end
- ✅ Known patterns are recognized and incremented on re‑occurrence

---

## 6. Phase 5 — Advisory & Evidence Layer ✅

> **Status: Contract ✅ Design ✅ Implementation ✅ Complete**
>
> Phase 5 compiles signals, patterns, and evidence into user‑facing advisories
> with 4 output formats: JSON, human summary, chat, and investigation prompt.

### 6.1 Advisory Engine ✅

- [x] Significance filter (configurable deviation threshold, default ±1.5 stddev)
- [x] Evidence collector (traces signals → Phase 1 events → commits, files, tests, deps)
- [x] Pattern matcher integration (queries Phase 4 KB for known patterns)
- [x] Advisory Report compilation (canonical JSON shape per contract)

### 6.2 Evidence Package ✅

- [x] Commits involved (SHA, message, author, timestamp, files changed)
- [x] Files affected (path, change type, origin commit)
- [x] Tests impacted (name, status before/now, since commit)
- [x] Dependencies changed (name, action, version)
- [x] Cross‑family timeline (chronological event merge from all families)

### 6.3 Presentation Formats ✅

- [x] Structured JSON (`advisory.json` + `evidence.json`)
- [x] Human summary (`summary.txt` — "normal vs now" with visual bars)
- [x] Chat format (`chat.txt` — compact for Telegram / Slack / Discord)
- [x] Investigation prompt (`investigation_prompt.txt` — for AI coding assistants)

### 6.4 Testing & Validation ✅

- [x] Advisory generation from fixture data (all 7 families)
- [x] Evidence package with commits, files, tests, deps, timeline
- [x] All 4 format renderers produce valid output
- [x] End‑to‑end: Phase 1 → 2 → 3 → 4 → 5

### Exit Criteria — All Met
- ✅ Advisories clearly show "normal vs now" for significant changes
- ✅ Evidence packages contain specific artifacts (commits, files, tests, deps)
- ✅ Investigation prompts are consumable by AI coding assistants
- ✅ Multiple output formats work (JSON, human, chat, investigation prompt)

---

## 7. Immediate Priorities — Calibration & Product Readiness

> **Status: 🔄 In Progress**
>
> Calibration runs (Feb 2026) validated that the pipeline works at scale,
> but revealed that **pattern discovery requires historical multi‑family data**.
> Git‑only runs produced 0 patterns (by design — Phase 4 finds cross‑family patterns).
> The priorities below unblock pattern discovery and prepare the product for users.

### 7.0 Calibration Findings (Feb 2026)

**What was validated:**
- ✅ Pipeline works end‑to‑end (Phases 1–5) on repos up to 6,713 commits
- ✅ Phase 3.1 LLM enhancement scales (26K explanations in ~2 minutes)
- ✅ Phase 5 advisory output is production‑quality (summary, chat, investigation prompt)
- ✅ Statistical baselines are stable on repos with 100+ commits
- ✅ **Cross-family pattern discovered** (git × ci, r=-0.59) with commit-SHA alignment
- ✅ **4-family pipeline validated** on fastapi: 11,593 events → 41,427 signals → 1 pattern → advisory
- ✅ **Parallel execution** working: concurrent API fetches + parallel Phase 2 families
- ✅ **LLM resilience**: both LLM clients (OpenRouter, Anthropic) have retry/backoff/429 handling; Phase 3.1 falls back to template on any LLM failure

**What was discovered:**
- ⚠️ Git‑only data → 0 cross‑family patterns (expected, by design)
- ⚠️ Pattern discovery requires **historical multi‑family data** (CI + test + deps over time)
- ⚠️ Synthetic/snapshot data doesn't work — need temporal correlations across 100+ commits
- ⚠️ Ordinal signal alignment was fundamentally broken for cross-family pairs — **fixed** to use commit-SHA alignment
- ⚠️ fastapi dependency metrics are degenerate: `direct_count == dependency_count` always (pip has no transitive resolution), `max_depth` constant
- ⚠️ Only 11 shared commits between git and CI (API returns max 500 recent runs vs 6,713 historical commits)

**Where historical multi‑family data exists in open‑source repos:**

| Family | Data Source | Publicly Available? |
|--------|-----------|---------------------|
| Git | Repo history | Always ✅ |
| Dependencies | Lockfiles in git history (`requirements.txt`, `go.sum`, `package-lock.json`) | Yes ✅ — `git show <commit>:<path>` |
| CI / Build | GitHub Actions API (`/actions/runs`) | Yes ✅ — public repos |
| Deployment | GitHub Releases API (`/releases`) | Yes ✅ |
| Schema / API | OpenAPI specs tracked in git | Yes ✅ (repos like fastapi) |
| Security | GitHub Security Advisories API | Partially |
| Config | Terraform/IaC files in git history | Yes ✅ (repos like terraform-provider-aws) |
| Testing | CI test artifacts (JUnit XML) | Sometimes — may expire after 90 days |

**Conclusion:** Multi‑family calibration is achievable from open‑source repos.
Two adapter extensions are needed first (see §7.1).

### 7.1 Priority 1: Git History Walker Adapter ✅

> **Status: ✅ Complete**

See §3.1 for full details. Supports 8 lockfile formats across 5 ecosystems (Go, npm, Cargo, Bundler, pip), plus OpenAPI and Terraform. Validated on fastapi (Python) and gin (Go).

### 7.2 Priority 2: GitHub API Adapters ✅

> **Status: ✅ Complete**

Three GitHub API adapters share a `GitHubClient` (`evolution/adapters/github_client.py`) with:
- Rate limiting (respects X-RateLimit headers, 1s delay between requests)
- Response caching (JSON cache in `api_cache/` directory)
- Auto-pagination (handles `Link: rel="next"` headers)

**Adapters:**
- ✅ `GitHubActionsAdapter` — CI workflow runs (max_runs configurable, default 500)
- ✅ `GitHubReleasesAdapter` — Deployment releases (tag, assets, pre-release flag)
- ✅ `GitHubSecurityAdapter` — Dependabot alerts (graceful 404 handling)

All three support fixture mode (pre-parsed data) and live API mode.

### 7.3 Priority 3: Calibration Repo Search & Selection ✅

> **Status: ✅ Complete — 120 repos found, top 20 ranked**

120 candidate repos found across 8 languages (`.calibration/repos_found.json`).
Top 20 ranked by family coverage score (max 8/8):

| # | Repository | Score | Language | Key Families |
|---|-----------|-------|----------|-------------|
| 1 | kubernetes | 8/8 | Go | All families including testing + security |
| 2 | grafana | 8/8 | Go+TS | Multi-language, broad coverage |
| 3 | prometheus | 7/8 | Go | CI, deps, releases, security |
| 4 | gin-gonic/gin | 7/8 | Go | CI, deps (go.sum), releases |
| 5 | fastapi | 7/8 | Python | CI, deps, schema (OpenAPI), releases |

**Tested:**
- ✅ fastapi — 11,593 events (4 families), 41K signals, 1 cross-family pattern, 7 significant changes
- ✅ gin — 1,000 events, 3,465 signals, 5 significant changes

### 7.4 Priority 4: Multi‑Family Calibration & Data Quality ✅

> **Status: ✅ Complete — 6-wave data quality fix, 2 patterns discovered on fastapi**
>
> Pipeline was producing unreliable output (8/13 metrics degenerate, absurd deviation scores).
> All 6 waves of fixes implemented. Reframed as "Seeding Universal Patterns" for the
> open-core product model (see §8).

**6-Wave Data Quality Fix (ALL COMPLETED):**

| Wave | Fix | Impact |
|------|-----|--------|
| 1 | MAD/IQR replaces z-score, degenerate flagging | Eliminated 775σ, 17,364σ nonsense |
| 2 | Removed 5 degenerate metrics, added 4 new ones | Clean metric set (see §7.4.1) |
| 3 | Phase 4 degenerate filter, confidence weighting | Honest pattern strength |
| 4 | Phase 5 compound-key lookup, event grouping | Correct advisory output |
| 5 | Temporal alignment (24h windows) supplements SHA | Cross-family overlap for sparse data |
| 6 | Phase 3 templates for new/removed metrics | Explanations match data |

**E2E Results (fastapi, post-fix):**
```
Pipeline:   6.6s total (Phase 2: 4.6s, Phase 3: 0.6s, Phase 4: 0.7s, Phase 5: 0.6s)
Events:     11,593 (git: 6713, dependency: 4126, ci: 500, deployment: 254)
Signals:    27,390 across 4 families
Deviating:  4,421 (16%)
Patterns:   2 discovered (git×dependency, git×ci)
Advisory:   6 significant changes
```

#### 7.4.1 Current Metrics (Post Data Quality Fix)

| Family | Metrics | Notes |
|--------|---------|-------|
| Git | `files_touched`, `dispersion`, `change_locality`, `cochange_novelty_ratio` | Core 4, stable |
| CI | `run_duration`, `run_failed` (binary) | Removed `job_count`, `failure_rate` |
| Deployment | `release_cadence_hours`, `is_prerelease`, `asset_count` | Replaced `deploy_duration`, `is_rollback` |
| Dependency | `dependency_count`, `max_depth` | Only npm/go/cargo/bundler for depth |

**Removed metrics:** `job_count`, `failure_rate`, `deploy_duration`, `is_rollback`, `direct_count` — all degenerate across repos.

### 7.4.2 Remaining: Batch Calibration → Seed Universal Patterns

> Reframed from "calibration runs" to "seeding universal patterns" for the open-core model.
> Output: `evolution/data/universal_patterns.json` bundled in the pip package.

- [ ] Run batch calibration across top 20 repos (from `.calibration/repos_found.json`)
- [ ] Aggregate patterns across repos: universal (50+ repos), ecosystem-specific (10+), local (<10)
- [ ] Output: `evolution/data/universal_patterns.json` bundled in pip package
- [ ] Phase 4 loads universal patterns at startup → instant recognition on new repos
- [ ] Target: 10+ universal patterns, 5+ per ecosystem (python, node, go)

### 7.5 Priority 5: Fix Verification Loop (Phase 5 Extension) ✅

> **Status: ✅ Complete**

Implemented in `evolution/phase5_engine.py`:
- ✅ `verify(scope, compare_to)` method — compares current vs previous advisory
- ✅ `_diff_advisories()` — classifies changes as resolved/persisting/new/regression
- ✅ `_format_verification_summary()` — human-readable verification report
- ✅ Advisory diff engine matches changes by `family:metric_name` key
- ✅ Outputs `verification.json` and `verification.txt`

**Known limitation:** Regression classification matches by family rather than family:metric pair. Functionally acceptable but could be tightened.

### 7.6 Priority 6: Report Generator (Product Feature) 🆕

> **Status: ⏳ Not Started | Effort: 2–3 days**

HTML report from `advisory.json` — a core product feature, not just a consulting deliverable.

**Implementation:**
- [ ] Jinja2 HTML template with CSS styling
- [ ] Cover page: repo name, date range, scope, executive summary
- [ ] "Normal vs Now" section with visual bars (SVG)
- [ ] Evidence section: commit table, affected files, pattern matches
- [ ] "Unlock more" section: detected vs. available adapters (upsell for Pro tier)
- [ ] CLI command: `evo report [path]`

### 7.7 Priority 7: Marketing & Product Launch 🆕

> **Status: ⏳ Not Started | Effort: Separate track**

Materials for product launch (not consulting outreach — see §8.1 for product vision).

- [ ] **Sample report:** From fastapi multi-family run, showing real patterns
- [ ] **Demo script:** `evo analyze .` → advisory → patterns → done
- [ ] **Landing page:** "Your development process, measured" (separate project)
- [ ] **README:** Clear value prop, install instructions, quick start

**Dependency:** Sample report needs batch calibration (§7.4.2) for pattern showcase.

### 7.8 Calibration Matrix

The system must be tested across multiple dimensions to produce reliable patterns:

| Dimension | Targets | Why |
|-----------|---------|-----|
| **Languages** | Python, TypeScript/JS, Go, Rust, Java, C# | Ensure patterns are structural, not language artifacts |
| **Project sizes** | Small (1–5 devs), Medium (5–20), Large (20+) | Baseline norms differ by team size |
| **Project ages** | Young (<6 months), Mature (1–3 years), Legacy (3+) | Signal stability varies with history length |
| **Dev patterns** | AI‑heavy, AI‑light, no‑AI | Core use case validation |
| **Source families** | All 8 families, each with real data | Per‑family metric ranges and correlations |
| **Vendor flavors** | GitHub Actions vs GitLab CI, JUnit vs pytest, pip vs npm, etc. | Adapter correctness with real‑world data |

### 7.9 Minimum Viable Seed KB Targets

- [ ] 10+ validated cross‑family patterns
- [ ] 5+ per‑family baseline norms
- [ ] 3+ language‑specific false positives documented and suppressed
- [ ] Universal parameter defaults validated
- [ ] Confidence thresholds tuned per project size tier

### 7.10 Consulting (Optional Enterprise Tier)

> **Deprioritized.** The primary delivery model is now the local-first CLI tool (§8).
> Consulting is available as an enterprise tier, not the primary revenue path.

Consulting may still serve as:
- Enterprise onboarding assistance
- Custom adapter development
- Pattern validation for regulated industries
- Revenue supplement while product scales

### 7.11 Product Readiness Criteria

The product is ready for beta when:

- [x] Pipeline produces correct results on real repos (fastapi validated)
- [x] `evo analyze .` works end-to-end without config
- [x] 148 tests pass with >80% coverage on core engines
- [x] KB security validates all imported patterns
- [ ] 10+ universal patterns bundled in pip package
- [ ] False positive rate <10% on unseen repos
- [ ] License key gates features correctly
- [ ] Compiled wheel installs and runs without source

---

## 8. Product Vision & Open‑Core Architecture

> **Pivot (February 2026):** The product direction has shifted from consulting-first → SaaS
> to a **local-first CLI tool** with an **open-core** business model.
> The user runs `evo analyze .` on their own machine. No data leaves by default.
> Community patterns are shared anonymously via opt-in.

### 8.1 What Is Evo?

**Evo is a doctor for your development process.**

Every code repository has a "normal" — a characteristic rhythm of how commits land, how
CI behaves, how dependencies change, and how releases ship. Evo learns this normal from
your git history and connected services, then tells you when something structural has changed.

This is **not** runtime monitoring (New Relic/Datadog), **not** code quality scoring
(SonarQube), and **not** project management analytics (LinearB/Jellyfish). Evo watches
the *development process itself* — the structural artifacts that engineers produce — and
detects when the process changes in ways that historically correlate with problems.

**The value chain:**
```
Git History + CI + Dependencies + Releases + Security
    ↓
Phase 1: Record immutable events
    ↓
Phase 2: Compute baselines per metric ("normal" for this repo)
    ↓
Phase 3: Explain each deviation in human language
    ↓
Phase 4: Discover cross-family patterns (KB learning)
    ↓
Phase 5: Advisory → Evidence Package → Investigation Prompt → Fix Verification
```

**Key insight:** The pipeline doesn't just flag problems — it **learns patterns** and
**tracks outcomes**. Over time, it builds a knowledge base of what structural changes
tend to precede what kinds of issues.

### 8.2 Competitive Positioning

| Dimension | Evo | APM (New Relic, Datadog) | Code Quality (SonarQube) | Dev Analytics (LinearB) |
|-----------|-----|--------------------------|--------------------------|--------------------------|
| **What it watches** | Development process artifacts | Runtime production systems | Code patterns | Developer activity metrics |
| **When it runs** | Pre-production (on every commit) | Post-deployment | During CI | Retroactively |
| **Data source** | Git + CI + deps + releases | Application telemetry | Source code | Jira + Git + CI |
| **What it finds** | Structural process changes | Performance anomalies | Code smells | Productivity metrics |
| **Key output** | "Your release pattern changed" | "p99 latency spiked" | "Complexity increased" | "Cycle time is 3 days" |
| **Moat** | Pattern Knowledge Base | Scale of telemetry | Rule database | Integrations |

**Why big players can't easily replicate this:**

1. **The Pattern Knowledge Base is the product, not the code.** New Relic could build a
   Phase 2 engine in weeks. They cannot build a KB with 10,000+ validated cross-family
   patterns without running the pipeline on thousands of repos over months.

2. **Network effects compound.** Every repo that runs evo and opts into community sharing
   makes the pattern KB better for everyone. This is a data flywheel that takes time to build.

3. **Different market position.** APM tools monitor *running software*. Evo monitors
   *the process of building software*. These are complementary, not competing — evo runs
   pre-production, APM runs post-deployment.

4. **Local-first model is hard for SaaS incumbents.** New Relic's entire business model
   requires your data on their servers. Evo runs on your machine.

### 8.3 Strategic Recommendations

1. **Don't publish algorithm details.** Open-source the adapters and CLI. Keep the phase
   engines (statistical models, pattern discovery, advisory logic) proprietary. Publish
   *what* evo finds, not *how* it finds it.

2. **Prioritize universal pattern seeding (§7.4.2).** The pattern KB is the moat.
   Run on 100+ repos across 5+ ecosystems. Bundle the results.

3. **Build community sharing early (§8.6).** Anonymous pattern digest sharing creates
   the network effect. The more repos that share, the better the KB.

4. **Charge for engines, not data.** Free tier: git-only, 5 metrics. Pro tier: all
   adapters, all metrics, pattern recognition. The value is in the analytical engine.

### 8.4 Open‑Core Split

| Open Source (MIT) | Proprietary (compiled .so) |
|-------------------|---------------------------|
| `evolution/adapters/*` | `evolution/phase2_engine.py` |
| `evolution/registry.py` | `evolution/phase3_engine.py` |
| `evolution/cli.py` | `evolution/phase4_engine.py` |
| `evolution/orchestrator.py` | `evolution/phase5_engine.py` |
| `evolution/phase1_engine.py` | `evolution/knowledge_store.py` |
| `evolution/kb_export.py` | |
| `evolution/kb_security.py` | |

The open-source layer lets anyone inspect adapters, contribute parsers, and understand
the data model. The proprietary layer (compiled via Cython) contains the statistical
engines, pattern discovery, and knowledge base — the intellectual property.

### 8.5 Adapter Ecosystem — Registry + Plugins + Validation ✅

> **Status: ✅ Complete — `evolution/registry.py` + `evolution/adapter_validator.py` with 37 tests**

Three-tier adapter detection. `evo analyze .` works without any configuration files.
Third-party adapters auto-discovered via Python entry_points.

**Tier 1 — File-based (built-in, always works offline):**

| File Pattern | Adapter | Family |
|-------------|---------|--------|
| `.git/` | git | version_control |
| `requirements.txt`, `pyproject.toml` | pip | dependency |
| `package-lock.json`, `yarn.lock` | npm | dependency |
| `go.mod` | go | dependency |
| `Cargo.lock` | cargo | dependency |
| `Gemfile.lock` | bundler | dependency |
| `.github/workflows/*.yml` | github_actions_local | ci |
| `*.tf` | terraform | config |
| `Dockerfile`, `docker-compose.yml` | docker | config |

**Tier 2 — API-enriched (optional tokens):**

| Token | Adapters Unlocked |
|-------|------------------|
| `GITHUB_TOKEN` | github_actions, github_releases, github_security |
| `GITLAB_TOKEN` | gitlab_pipelines |
| `JENKINS_URL` | jenkins |

**Tier 3 — Plugin adapters (community-contributed):**

Third-party pip packages register adapters via Python `entry_points`:

```toml
# In evo-adapter-jenkins/pyproject.toml
[project.entry-points."evo.adapters"]
jenkins = "evo_jenkins:register"
```

```python
# In evo_jenkins/__init__.py
def register():
    return [{
        "pattern": "Jenkinsfile",
        "adapter_name": "jenkins",
        "family": "ci",
        "adapter_class": "evo_jenkins.JenkinsAdapter",
    }]
```

Users install: `pip install evo-adapter-jenkins` → `evo analyze .` auto-discovers it.

**Adapter Certification (`evo adapter validate`):**

Plugin adapters must pass 13 validation checks before publishing:
- Required class attributes (`source_family`, `source_type`, `ordering_mode`, `attestation_tier`)
- `source_family` is a recognized family
- `iter_events()` yields valid SourceEvent dicts with correct structure
- Event `source_family` matches class attribute
- Events are strictly JSON-serializable

```
$ evo adapter validate evo_jenkins.JenkinsAdapter
Adapter: evo_jenkins.JenkinsAdapter
Result: PASSED (13/13 checks)
Adapter is certified. Ready to publish as a pip package.
```

**Adapter distribution model:**

| Path | Who Builds | How It Reaches Users |
|------|-----------|---------------------|
| Core (built-in) | Us | Shipped with `evolution-engine` pip package |
| Plugin (community) | Any developer | `pip install evo-adapter-X`, auto-discovered |
| Promoted | Community → Us | Popular plugin merged into core after quality proven |
| Requested | Us, based on demand | Users request via GitHub Issues, we build popular ones |

Missing tokens → advisory message, not error.

### 8.6 CLI Tool (`evo`) ✅

> **Status: ✅ Complete — `evolution/cli.py` + `evolution/orchestrator.py`**

Primary user interface. Zero-config entry point.

```
evo analyze [path]               # Detect adapters, run Phase 1-5
evo analyze . --token ghp_xxx    # Unlock Tier 2 API adapters
evo analyze . --families git,ci  # Override detection
evo status [path]                # Show detected adapters, last advisory
evo report [path]                # HTML report from last run
evo patterns list                # Show KB contents
evo patterns export              # Export anonymized digests
evo patterns import <file>       # Import community patterns
evo verify [previous]            # Fix verification loop
```

**Entry point:** `pyproject.toml` → `evo = "evolution.cli:main"` (click-based)

### 8.7 Pattern Export/Import & KB Security ✅

> **Status: ✅ Complete — `evolution/kb_export.py` + `evolution/kb_security.py` with 40 tests**

Anonymous pattern sharing without exposing raw data.

**Export:** Strips pattern_id, signal_refs, event_refs, repo path, author info.
Sets scope="community". Only exports confirmed knowledge + strong candidates.

**Import:** ALL patterns validated through `kb_security.validate_pattern()` before storage.
Blocks: XSS (`<script>`), template injection (`{{}}`), shell injection (``; rm``),
path traversal (`../`), SQL injection (`; DROP TABLE`), reference injection (signal_refs stripped).

**Pattern Scope Progression:**
```
local       → discovered on this repo
community   → imported from another repo or registry
confirmed   → discovered locally AND matches community
universal   → 50+ repos, bundled in pip package
```

### 8.8 Community KB Sync (Not Started)

> **Status: ⏳ Not Started | Next Priority**

Opt-in sync with community pattern registry.

**Three Sharing Levels:**

| Level | What's Shared | Default? |
|-------|--------------|----------|
| 0 | Nothing | Yes |
| 1 | Advisory metadata only | No |
| 2 | Anonymized pattern digests | No |

**New files needed:** `evolution/kb_sync.py`, `evolution/config.py`,
`evolution/data/universal_patterns.json`

### 8.9 Packaging & Distribution (Not Started)

> **Status: ⏳ Not Started**

Ship as pip package with proprietary engine compiled via Cython.

- Cython compiles phase engines to `.so` / `.pyd`
- CI builds wheels for Linux (x86_64, aarch64), macOS (arm64, x86_64), Windows
- Open-source repo has type stubs (`.pyi`) but not source for proprietary modules
- `pip install evolution-engine` → `evo analyze .` works

### 8.10 License & Monetization (Not Started)

> **Status: ⏳ Not Started**

| Tier | Price | Adapters | Metrics | Patterns | Report |
|------|-------|----------|---------|----------|--------|
| Free | $0 | git only | 5 | No | No |
| Pro | $29/mo | all | all | Yes | Yes |
| Team | $99/mo/10 | all | all | Yes (shared) | Yes |
| Enterprise | custom | all | all | Self-hosted sync | Yes |

Signed JWT license validated locally. Weekly online check, 30-day offline grace.

### 8.11 Future Enhancements

- PostgreSQL + pgvector migration (multi-tenant, when SaaS tier exists)
- Integrated AI Investigation (direct API call to coding assistant)
- Additional vendor adapters (GitLab CI, Jenkins, npm, Cargo, etc.)
- Real-time event streaming (webhooks vs batch polling)
- IDE extensions (VS Code, JetBrains) — surfaces advisories where code is written

---

## 9. Product Delivery — CLI‑First Strategy

> **Updated (February 2026):** Delivery priority inverted from the original plan.
> CLI is now **first**, not last. Local-first is the product identity.

### Delivery Channel Priority (Revised)

| Priority | Channel | Effort | Status |
|----------|---------|--------|--------|
| **1** | CLI Tool (`evo analyze .`) | Low | ✅ Complete |
| **2** | pip package (compiled wheels) | Medium | ⏳ Not started |
| **3** | GitHub Action (CI integration) | Medium | ⏳ Not started |
| **4** | API Service / SaaS | High | Deprioritized |
| **5** | Web Dashboard | High | Deprioritized |

### 9.1 CLI Tool ✅

**Already built.** See §8.6 for details.

`evo analyze .` → detects adapters → ingests data → Phase 2-5 → advisory.

### 9.2 pip Package (Next)

- `pip install evolution-engine`
- Compiled Cython wheels (phase engines as `.so`)
- Universal patterns bundled as `evolution/data/universal_patterns.json`
- Works offline, no account required for free tier

### 9.3 GitHub Action (After pip)

- `uses: evolution-engine/analyze@v1`
- PR comment with "normal vs now" summary
- Advisory annotation (never blocking — purely informational)
- Evidence package as downloadable artifact
- Uses existing CLI under the hood

### 9.4 API Service / SaaS (Future, If Demand)

Deprioritized. May build for Team/Enterprise tiers if demand exists.
The local-first model is the product identity — SaaS would be additive, not core.

### 9.5 Web Dashboard (Future, If Demand)

Deprioritized. The CLI + HTML report covers the core use case.
A dashboard adds value for teams managing multiple repos — enterprise tier feature.

---

## 10. Non‑Goals (Reconfirmed)

This plan explicitly excludes:
- Runtime telemetry
- Raw log ingestion
- Blocking enforcement (CI integration is **advisory**, never blocking)
- Global risk scoring
- Semantic intent inference
- Automated code fixes (the system provides evidence, not patches)

---

## 11. Execution Summary

| Component | Status | What It Does |
|-----------|--------|-------------|
| **Phase 1** | ✅ Complete | Record immutable events from all sources |
| **Phase 2** | ✅ Complete | Compute baselines (MAD/IQR), emit deviation signals |
| **Phase 3** | ✅ Complete | Explain signals in human language (+ LLM option) |
| **Phase 4** | ✅ Complete | Discover cross-family patterns, KB learning |
| **Phase 5** | ✅ Complete | Advisory reports + evidence + fix verification |
| **Data Quality (6 waves)** | ✅ **Complete** | Robust deviation math, clean metric set |
| **Git History Walker** | ✅ **Complete** | 8 lockfile formats, 3 families from git |
| **GitHub API Adapters** | ✅ **Complete** | CI, deployment, security from GitHub API |
| **Adapter Registry** | ✅ **Complete** | Zero-config detection (Tier 1 file, Tier 2 API) |
| **CLI Tool (`evo`)** | ✅ **Complete** | `evo analyze .` — primary user interface |
| **KB Security** | ✅ **Complete** | Validates all imported patterns (10+ attack vectors) |
| **KB Export/Import** | ✅ **Complete** | Anonymous pattern sharing with security gate |
| **Test Suite** | ✅ **Complete** | 148 tests, 0.68s, >80% core coverage |
| **Batch Calibration** | 🔄 **Next** | Seed universal patterns from 20+ repos |
| **Community KB Sync** | ⏳ Not started | Opt-in anonymous pattern sharing |
| **Report Generator** | ⏳ Not started | HTML report for `evo report` |
| **Packaging (Cython)** | ⏳ Not started | Compiled wheels for pip distribution |
| **License System** | ⏳ Not started | Free/Pro/Team/Enterprise tier gating |

### Execution Timeline

```
Engine (Done)         Open-Core Infrastructure (Done)    Product Readiness        Distribution
─────────────         ──────────────────────────────     ────────────────         ────────────
Phase 1-5 ✅          Adapter Registry ✅                 Batch Calibration
6-Wave Fix ✅         CLI (evo analyze .) ✅              (seed universal KB)
Adapters ✅           KB Security ✅                            │
Walker ✅             KB Export/Import ✅                       ├──▶ Report Generator
GitHub API ✅         148 Tests ✅                              │    (HTML for evo report)
                                                               │
                      ╔═══════════════════════════════╗        ├──▶ Community KB Sync
                      ║ Product infrastructure done.  ║        │    (evo patterns pull)
                      ║ evo analyze . works end-to-   ║        │
                      ║ end. Next: seed the KB and    ║        ├──▶ Packaging (Cython)
                      ║ build the community flywheel. ║        │    (pip install evo)
                      ╚═══════════════════════════════╝        │
                                                               ├──▶ License System
                                                               │    (Free/Pro/Team)
                                                               │
                                                               └──▶ GitHub Action
                                                                    (CI integration)
```

### Immediate Next Actions

1. ~~Build Git History Walker Adapter~~ ✅
2. ~~Build GitHub API Adapters~~ ✅
3. ~~6-Wave Data Quality Fix~~ ✅
4. ~~Adapter Auto-Detection Registry~~ ✅
5. ~~CLI Tool (evo analyze .)~~ ✅
6. ~~KB Security Validation~~ ✅
7. ~~KB Export/Import~~ ✅
8. ~~Test Suite (148 tests)~~ ✅
9. **Seed Universal Patterns** (§7.4.2) — next priority
   - Run on 20+ repos across 5+ ecosystems
   - Aggregate patterns → `evolution/data/universal_patterns.json`
   - Target: 10+ universal patterns bundled in pip package
10. **Community KB Sync** (§8.8)
    - `evo patterns pull` / push
    - 3 sharing levels, staleness check
11. **Report Generator** (§7.6)
    - `evo report` → HTML output
12. **Packaging** (§8.9)
    - Cython compilation, multi-platform wheels
13. **License System** (§8.10)
    - Feature gating by tier

---

## 12. Plan Maintenance

- This document is updated **only** when a phase is completed or reordered.
- Changes must reference Architecture Vision principles.
- Research documents inform changes but do not override this plan.

---

> **Summary (February 9, 2026):**
>
> **All 5 engine phases complete.** 6-wave data quality fix validated. 148 tests passing.
> The full pipeline runs end-to-end in 6.6 seconds on fastapi (27,390 signals, 2 patterns).
>
> **Open-core product infrastructure complete:**
> - `evo analyze .` — zero-config CLI (adapter auto-detection, click-based)
> - KB Security — validates all imported patterns (XSS, injection, traversal, etc.)
> - KB Export/Import — anonymous pattern sharing with security gate
> - Adapter Registry — Tier 1 (file-based) + Tier 2 (API tokens)
> - Orchestrator — importable pipeline module (detect → ingest → Phase 2-5)
>
> **Competitive position:** Development Process Intelligence — complementary to APM tools
> (New Relic/Datadog), not competing. Moat is the Pattern Knowledge Base, not the code.
> Local-first model is hard for SaaS incumbents to replicate.
>
> **Next:** Seed universal patterns from 20+ repos → bundle in pip package → community sync
> → compiled wheels → license system → GitHub Action → product launch.
>
> The engagement flow: **evo analyze . → Advisory → Investigation Prompt → Fix → evo verify → Repeat.**
