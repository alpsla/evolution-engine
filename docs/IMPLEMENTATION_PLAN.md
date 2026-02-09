# Evolution Engine — Implementation Plan

> **Authoritative Execution Roadmap**
>
> This document translates the Architecture Vision and research findings into an explicit, ordered implementation plan.
> It answers *what we build*, *in what order*, and *why that order exists*.
>
> The plan is intentionally conservative: each step validates an architectural assumption before expanding scope.
>
> **Last updated:** February 8, 2026 (LLM resilience complete, batch calibration infrastructure ready for 120 repos)

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

### 7.4 Priority 4: Multi‑Family Calibration Runs

> **Status: 🔄 In Progress — first multi-family pattern discovered, need more repos**
>
> Phase 4's cross-family alignment fixed to use commit SHA instead of ordinal position.
> First calibration with GitHub API families (CI + deployment) completed on fastapi.
> Pipeline parallelized (concurrent API fetches, parallel Phase 2 families).

**Completed:**
- ✅ **Phase 4 alignment fix**: `_build_commit_index()` maps event_id → commit_sha; `_discover_cooccurrences()` aligns by shared commits
- ✅ **fastapi 4-family run**: 11,593 events (git: 6713, dependency: 4126, ci: 500, deployment: 254)
- ✅ **First pattern**: `git.change_locality ↔ ci.run_duration` (r=-0.59, 3 co-deviations across 11 shared commits)
- ✅ **Pipeline parallelized**: API fetches concurrent with walker, Phase 2 families in parallel (198s total)

**fastapi results (4 families):**
```
Events:     11,593 (git: 6713, dependency: 4126, ci: 500, deployment: 254)
Signals:    41,427 (git: 26832, dependency: 12363, ci: 1485, deployment: 747)
Patterns:   1 (git × ci, change_locality ↔ run_duration, r=-0.59)
Advisory:   7 significant changes across 3 families
Time:       198s
```

**Remaining — Batch Calibration (120 repos):**
- [ ] Run batch calibration across all 120 candidate repos (see `.calibration/BATCH_CALIBRATION_PLAN.md`)
- [ ] Parallel Sonnet 4.5 agents via `claude --dangerously-skip-permissions --model sonnet`
- [ ] Repos with OpenAPI specs (schema family) and Terraform (config family) for 6+ family coverage
- [ ] Aggregate patterns across all repos, classify: generalizable, local-only, false positive
- [ ] Parameter tuning across profiles (conservative, moderate, aggressive)

**Process per repo:**
```
1. Git History Walker → extract dependency/schema/config snapshots from past commits
2. GitHub API Adapter → fetch CI runs, releases, security advisories
3. Phase 1 → ingest all families
4. Phase 2 → compute baselines for all families (parallel)
5. Phase 3 → generate explanations (LLM‑enhanced)
6. Phase 4 → discover cross-family patterns (commit-SHA aligned)
7. Phase 5 → generate advisory with pattern context
8. Classify patterns: generalizable, local-only, false positive, noise
9. Write calibration report
```

**Parameter tuning:**

| Profile | min_support | min_correlation | promotion_threshold | Use Case |
|---------|-------------|-----------------|---------------------|----------|
| Conservative | 10 | 0.7 | 25 | Fewer patterns, higher quality |
| Moderate | 5 | 0.5 | 15 | Balanced |
| Aggressive | 3 | 0.3 | 10 | More patterns, more noise |

Run each repo with all three profiles, compare pattern quality.

### 7.5 Priority 5: Fix Verification Loop (Phase 5 Extension) ✅

> **Status: ✅ Complete**

Implemented in `evolution/phase5_engine.py`:
- ✅ `verify(scope, compare_to)` method — compares current vs previous advisory
- ✅ `_diff_advisories()` — classifies changes as resolved/persisting/new/regression
- ✅ `_format_verification_summary()` — human-readable verification report
- ✅ Advisory diff engine matches changes by `family:metric_name` key
- ✅ Outputs `verification.json` and `verification.txt`

**Known limitation:** Regression classification matches by family rather than family:metric pair. Functionally acceptable but could be tightened.

### 7.6 Priority 6: Report Generator (Consulting Deliverable) 🆕

> **Status: ⏳ Not Started | Effort: 2–3 days**

Professional HTML/PDF report from `advisory.json` for consulting engagements.

**Current state:** Phase 5 produces text files (`summary.txt`, `chat.txt`).
**Needed for consulting:** Branded, presentable document suitable for client delivery.

**Implementation:**
- [ ] Jinja2 HTML template with CSS styling
- [ ] Cover page: repo name, date range, scope, executive summary
- [ ] "Normal vs Now" section with proper bar charts (SVG or Chart.js)
- [ ] Evidence section: commit table, affected files, test results
- [ ] Pattern matches section (when KB has patterns)
- [ ] Investigation prompt as appendix
- [ ] Fix Verification section (when comparing advisories)
- [ ] PDF export via `weasyprint` or browser print
- [ ] CLI command: `evolution report --format html --output report.html`

**Why before web dashboard:** A static report is simpler than a full web app,
delivers immediate consulting value, and validates the visual format before building a dashboard.

### 7.7 Priority 7: Marketing Materials 🆕

> **Status: ⏳ Not Started | Effort: Separate track**

Materials needed to begin consulting outreach.

- [ ] **One‑pager:** What the system does, who it's for, how it works (1 page)
- [ ] **Sample report:** Generated from a real open‑source repo (fastapi) with multi‑family data
- [ ] **Demo script:** Walk‑through of running the pipeline and reviewing the advisory
- [ ] **Pricing structure:** Consulting tiers (Audit, Baseline, Ongoing Advisory)
- [ ] **Landing page:** Simple website explaining the product (separate project)

**Dependency:** Sample report requires multi‑family calibration (§7.4) to be complete first,
so the report shows actual patterns and pattern matching — not just git‑only metrics.

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

### 7.10 Consulting (Parallel Track — Revenue + Beta Testing)

> Consulting runs **in parallel** with open‑source calibration, not instead of it.
> It serves three purposes simultaneously: **revenue** to fund the project,
> **real‑world calibration data** from production environments,
> and **beta testing experience** that shapes the product before self‑service launch.

**Consulting offering (updated with Fix Verification):**

| Phase | What We Deliver | What We Learn |
|-------|----------------|---------------|
| **Environment Assessment** | Inventory of client's source families, vendors, data access | Which adapters need extending |
| **Data Collection** | Run full pipeline against client repos | Real‑world adapter edge cases |
| **Calibration** | Tune baselines and thresholds for client's environment | Pattern discovery in new contexts |
| **Baseline Report** | Branded HTML/PDF: "Here's how your systems normally evolve" | Client‑specific normal ranges |
| **Investigation Prompt** | Pre‑built prompt for client's AI to investigate flagged issues | What users actually do with our output |
| **Fix Verification** 🆕 | Re‑run pipeline after fixes, verify what resolved | Fix effectiveness patterns |
| **Ongoing Advisory** | Periodic reports, pattern reviews, fix verification | Long‑horizon drift patterns |

**Engagement pipeline (updated):**
```
Discovery → Assessment → Baseline Report → Investigation Prompt → Fix Verification
    │                          │                    │                     │
    └── can stop here          └── seed KB          └── user's AI        └── verify & repeat
                                                         investigates       (monthly retainer)
```

### 7.11 Self‑Service Readiness Criteria

The system is ready to transition from calibration + consulting to self‑service when **both tracks** have contributed enough:

- [ ] Seed KB contains 50+ validated patterns across 3+ languages
- [ ] Universal parameters produce <10% false positive rate on new repos
- [ ] Cold‑start experience is useful (global KB provides meaningful priors)
- [ ] At least 3 consulting clients have validated the advisory output
- [ ] Fix Verification Loop tested on 3+ engagements
- [ ] HTML/PDF report quality approved by clients
- [ ] GitHub Action integration is tested in 5+ real CI environments

---

## 8. Future Enhancements (Post Calibration)

### 8.1 PostgreSQL + pgvector Migration
- Migrate KB from SQLite to PostgreSQL for multi‑tenant deployment
- Add vector similarity search for fuzzy pattern matching
- Enable cross‑account global knowledge

### 8.2 Integrated AI Investigation (Level 3)
- Direct API call to AI coding assistant with evidence package
- Response validation (does the AI cite real artifacts?)
- In‑product investigation results

### 8.3 Additional Vendor Adapters
Each family can expand with new vendor implementations:
- GitLab CI, Jenkins, CircleCI (CI family)
- pytest, Jest, Go test (Testing family)
- npm, Cargo, Go modules (Dependency family)
- GraphQL, Protobuf (Schema family)
- ArgoCD, Kubernetes (Deployment family)
- Kubernetes manifests, Helm (Config family)
- Snyk, Dependabot (Security family)

### 8.4 Application Flow Shape Source
- Highest‑risk, highest‑value source (Source 4 from Engine Abstract Base)
- Static analysis of code structure (call graphs, module dependencies)
- Requires mature adapter infrastructure before attempting

### 8.5 Real‑Time Event Streaming
- Webhook‑based event ingestion (vs batch polling)
- Near‑real‑time advisory updates

---

## 9. Product Delivery — Go‑to‑Market Strategy

> The Evolution Engine is a **product**, not just an engine.
> This section defines how the core capability reaches users,
> in iterative delivery channels ordered by impact and feasibility.

### Delivery Channel Priority

| Priority | Channel | Effort | User Value | Reach |
|----------|---------|--------|-----------|-------|
| **1** | GitHub / GitLab CI Integration | Medium | Highest | Broadest |
| **2** | API Service (SaaS) | Medium | High | Broad |
| **3** | Web Dashboard | High | High | Broad |
| **4** | IDE Extension (VS Code / JetBrains) | High | Medium | Developer‑focused |
| **5** | CLI Tool (standalone) | Low | Medium | Power users |

### 9.1 GitHub / GitLab CI Integration (Priority 1) 🎯

**Why first:** This is where the data already lives and where developers already work.
A GitHub Action or GitLab CI component that runs in the pipeline gives immediate value
with zero workflow change.

**Delivery model:**
- GitHub Action (`uses: evolution-engine/analyze@v1`)
- GitLab CI template (include from registry)
- Runs after push / on schedule / on PR

**What it produces:**
- PR comment with "normal vs now" summary
- Advisory annotation on the PR (if significant changes detected)
- Evidence package as a downloadable artifact
- Slack / Telegram notification (optional webhook)

**Why high value:**
- Zero installation for the user — just add a workflow file
- Accesses Git, CI, test, and dependency data natively
- PR context is where developers make decisions
- GitHub Actions marketplace provides organic discovery

**Implementation scope:**
- [ ] Package engine as a Docker container / GitHub Action
- [ ] GitHub PR comment renderer (Phase 5 format)
- [ ] GitHub check annotation (pass-through, never blocking)
- [ ] Webhook notification support (Slack, Telegram, Discord)
- [ ] GitLab CI equivalent

### 9.2 API Service / SaaS (Priority 2)

**Why second:** Enables the web dashboard, IDE extensions, and third‑party integrations.
All other channels consume this API.

**Delivery model:**
- REST API (hosted or self‑hosted)
- Accepts webhook events from GitHub / GitLab / CI systems
- Returns advisories and evidence packages on demand
- Stores knowledge base for pattern learning (PostgreSQL)

**Key endpoints:**
- `POST /events` — ingest events from adapters
- `GET /advisory/{repo}` — current advisory for a repo
- `GET /evidence/{advisory_id}` — evidence package
- `GET /patterns/{repo}` — known patterns for a repo
- `POST /investigate` — generate investigation prompt (Level 2)

**Implementation scope:**
- [ ] FastAPI or Flask REST API
- [ ] PostgreSQL + pgvector backend
- [ ] Webhook receiver (GitHub / GitLab events)
- [ ] Authentication and multi‑tenancy
- [ ] Rate limiting and usage tracking

### 9.3 Web Dashboard (Priority 3)

**Why third:** Visual "normal vs now" comparisons, pattern history,
and evidence browsing are most impactful in a dedicated UI.

**Delivery model:**
- Web application (React or similar)
- Consumes the API service
- Repository overview with family health bars
- Timeline view of structural changes
- Pattern library (what has the system learned?)

**Key views:**
- Repository dashboard ("3 things look different")
- Change timeline (cross‑family event stream)
- Pattern catalog (known patterns with statistics)
- Evidence browser (drill into specific commits, tests, deps)
- Investigation launcher ("Export to AI" button)

### 9.4 IDE Extension (Priority 4)

**Why fourth:** Surfaces advisories where code is written,
but requires the API service to be running first.

**Delivery model:**
- VS Code extension
- JetBrains plugin (IntelliJ, PyCharm, WebStorm)
- Shows inline annotations on files flagged in advisories
- Status bar indicator ("2 structural changes detected")
- Quick action: "View evidence" / "Export for AI investigation"

### 9.5 CLI Tool (Priority 5)

**Why fifth:** Already partially exists. Useful for power users
and CI environments that don't support GitHub Actions.

**Delivery model:**
- `evolution init` — initialize monitoring
- `evolution ingest` — run all adapters
- `evolution analyze` — Phase 1 → 2 → 3 → 4 → 5
- `evolution report` — generate advisory
- `evolution export` — export evidence package

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

| Phase | Status | What It Does |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Record immutable events from all sources |
| **Phase 2** | ✅ Complete | Compute baselines, emit deviation signals (parallel families) |
| **Phase 3** | ✅ Complete | Explain signals in human language (+ LLM) |
| **Phase 3.1** | ✅ Complete | LLM-enhanced explanations with validation gate |
| **Phase 4** | ✅ Complete | Discover, interpret, and remember patterns |
| **Phase 5** | ✅ Complete | Advisory reports + evidence packages |
| **Git History Walker** | ✅ **Complete** | 8 lockfile formats, 3 families from git |
| **GitHub API Adapters** | ✅ **Complete** | CI, deployment, security from GitHub API |
| **Repo Search** | ✅ **Complete** | 120 repos found, top 20 ranked |
| **LLM Resilience** | ✅ **Complete** | Retry/backoff/rate-limit handling + graceful fallback |
| **Batch Calibration** | 🔄 **In Progress** | 120 repos queued, parallel Sonnet agents, fastapi validated |
| **Fix Verification Loop** | ✅ **Complete** | Advisory diff engine in Phase 5 |
| **Report Generator** | ⏳ **Priority 6** | HTML/PDF reports for consulting delivery |
| **Marketing Materials** | ⏳ **Priority 7** | One‑pager, sample report, demo script |
| **Consulting** | ⏳ **After P6** | Revenue + beta testing + real‑world calibration |
| **Delivery 1** | ⏳ After readiness | GitHub / GitLab CI integration |
| **Delivery 2** | ⏳ After D1 | API Service (SaaS) |
| **Delivery 3** | ⏳ After D2 | Web Dashboard |

### Full Execution Timeline

```
Engine (Done)         Calibration Infrastructure    Calibration + Product     Delivery
─────────────         ──────────────────────────    ──────────────────────    ──────────
Phase 1-5 ✅
     │
     ├──▶ P1: Git History Walker ─────┐
     │    (extract lockfiles from     │
     │     past commits)              │
     │                                ├──▶ P4: Multi-Family Calibration
     ├──▶ P2: GitHub API Adapter ─────┘    (first real patterns!)
     │    (CI runs, releases,              │
     │     security advisories)            ├──▶ P5: Fix Verification Loop
     │                                     │
     ├──▶ P3: Repo Search                  ├──▶ P6: Report Generator
     │    (find repos with 4+              │    (HTML/PDF for consulting)
     │     family coverage)                │
     │                                     ├──▶ P7: Marketing Materials
     │                                     │    (one-pager, sample report)
     │                                     │
     │    ╔═════════════════════════════╗   │
     │    ║ Pattern discovery unlocked  ║   ├──▶ Consulting Outreach
     │    ║ by P1+P2. Calibration runs ║   │    (revenue + KB seeding)
     │    ║ use real multi-family data. ║   │
     │    ╚═════════════════════════════╝   │
     │                                     │    Self-service        CLI (exists)
     │                                     └──▶ readiness ────────▶ GitHub Action
     │                                          (50+ patterns,      API Service
     │                                           3+ clients,        Web Dashboard
     │                                           fix verification   IDE Extension
     │                                           validated)
     └──▶ Consulting continues as premium tier
```

### Immediate Next Actions

1. ~~Build Git History Walker Adapter~~ ✅
2. ~~Build GitHub API Adapters~~ ✅
3. ~~Search and validate calibration repos~~ ✅
4. ~~Fix Phase 4 cross-family alignment (commit-SHA based)~~ ✅
5. ~~Implement Fix Verification Loop~~ ✅
6. ~~Parallelize calibration pipeline~~ ✅
7. **Batch calibration of 120 repos** (§7.4) — in progress
   - ✅ fastapi: 4 families, 1 cross-family pattern (git × ci)
   - ✅ LLM resilience: retry/backoff/rate-limit handling, graceful fallback (no more crashes)
   - ✅ Batch runner: `examples/batch_calibrate.py` with parallel agent support
   - ✅ Transition document: `.calibration/BATCH_CALIBRATION_PLAN.md`
   - [ ] Run all 120 repos via parallel Sonnet 4.5 agents
   - [ ] Aggregate and classify discovered patterns
   - [ ] Tune parameters across profiles
8. **Build Report Generator** (§7.6) — next after calibration confidence
   - HTML/PDF from advisory.json
   - Consulting-ready deliverable
9. **Prepare marketing materials** (§7.7) — separate track
   - One‑pager, sample report from calibrated repo, demo script

---

## 12. Plan Maintenance

- This document is updated **only** when a phase is completed or reordered.
- Changes must reference Architecture Vision principles.
- Research documents inform changes but do not override this plan.

---

> **Summary:**
> **All 5 engine phases are complete** and validated across all 8 source families.
> The full pipeline (observe → measure → explain → learn → inform) runs end‑to‑end.
>
> **Wave 1 complete:** Git History Walker (8 lockfile formats), GitHub API Adapters
> (CI, deployment, security), Repo Search (120 repos ranked), Fix Verification Loop,
> Phase 4 cross-family alignment fix (commit-SHA based), pipeline parallelization,
> LLM resilience (retry/backoff/rate-limit/fallback).
>
> **First cross-family pattern discovered:** `git.change_locality ↔ ci.run_duration` (r=-0.59)
> on fastapi with 4 families (git, dependency, ci, deployment), 11,593 events, 41,427 signals.
>
> **Next:** Batch calibration of all 120 repos via parallel Sonnet 4.5 agents
> (`examples/batch_calibrate.py`, `.calibration/BATCH_CALIBRATION_PLAN.md`).
> Target: 10+ validated cross-family patterns from 5+ languages to seed the Knowledge Base.
> Then build Report Generator for consulting delivery.
>
> The engagement flow: **Advisory → Investigation Prompt → User's AI Fixes → Verify Fix Worked → Repeat.**
> The system doesn't just flag problems — it tracks outcomes.
