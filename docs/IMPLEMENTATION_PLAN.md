# Evolution Engine — Implementation Plan

> **Authoritative Execution Roadmap**
>
> This document translates the Architecture Vision and research findings into an explicit, ordered implementation plan.
> It answers *what we build*, *in what order*, and *why that order exists*.
>
> The plan is intentionally conservative: each step validates an architectural assumption before expanding scope.
>
> **Last updated:** February 10, 2026 (Axiom observability, product launch: website, Stripe, telemetry, PyPI prep; 542 tests)

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

### Phase 3 (Deterministic, PM-Friendly) ✅
- ✅ Template‑based explanation engine with plain-English output
- ✅ Templates for all 23 metrics across all 8 families
- ✅ `evolution/friendly.py` — centralized formatting helpers (risk levels, relative change, metric insights)
- ✅ Relative comparisons ("about 3x more than usual") instead of statistical jargon
- ✅ Per-metric practical insights ("Larger changes carry more review risk")
- ✅ Confidence annotations
- ✅ Content‑addressable explanation IDs

### Phase 3.1 (LLM Enhanced) — Retired
- ~~Validation‑gated LLM renderer~~ — **retired** after PM-friendly template rewrite
- Templates now produce the same quality as LLM-rewritten text
- Phase 3.1 code remains in `evolution/phase3_1_renderer.py` but is no longer called
- **Cost savings:** ~$12/repo eliminated (was 27K LLM calls per fastapi-sized repo)
- Phase 4b LLM remains active (~$0.01/repo) for unique pattern descriptions

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

### 6.3 Presentation Formats ✅ (PM-Friendly Rewrite)

- [x] Structured JSON (`advisory.json` + `evidence.json`) — data unchanged
- [x] Human summary (`summary.txt` — risk labels, relative comparisons, practical insights)
- [x] Chat format (`chat.txt` — per-metric risk levels and insights for Slack / Discord)
- [x] Investigation prompt (`investigation_prompt.txt` — stays technical for AI assistants)
- [x] Verification summary — plain English ("still notably different, improving")
- [x] All display text uses `evolution/friendly.py` helpers (no jargon in user-facing output)

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

> **Status: ✅ Complete**
>
> Calibration runs (Feb 2026) validated that the pipeline works at scale.
> Pattern discovery required historical multi‑family data — now resolved
> via Git History Walker + GitHub API adapters. All priorities below are complete.

### 7.0 Calibration Findings (Feb 2026)

**What was validated:**
- ✅ Pipeline works end‑to‑end (Phases 1–5) on repos up to 6,713 commits
- ✅ Phase 3.1 LLM enhancement scaled (26K explanations in ~2 minutes) — *later retired, see §4*
- ✅ Phase 5 advisory output is production‑quality (summary, chat, investigation prompt)
- ✅ Statistical baselines are stable on repos with 100+ commits
- ✅ **Cross-family pattern discovered** (git × ci, r=-0.59) with commit-SHA alignment
- ✅ **4-family pipeline validated** on fastapi: 11,593 events → 41,427 signals → 1 pattern → advisory
- ✅ **Parallel execution** working: concurrent API fetches + parallel Phase 2 families
- ✅ **LLM resilience**: both LLM clients (OpenRouter, Anthropic) have retry/backoff/429 handling

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

### 7.4.2 Batch Calibration → Seed Universal Patterns ✅

> **Status: ✅ Complete — 43 repos with patterns, 27 universal patterns bundled**
>
> Reframed from "calibration runs" to "seeding universal patterns" for the open-core model.
> Output: `evolution/data/universal_patterns.json` bundled in the pip package.

- [x] Run batch calibration across 92 candidate repos (from `.calibration/repos_found.json`)
- [x] Aggregate patterns across repos: `scripts/aggregate_calibration.py` with dedup
- [x] Output: `evolution/data/universal_patterns.json` bundled in pip package
- [x] Auto-import universal patterns during `evo analyze` and `evo patterns sync`
- [x] Target: 10+ universal patterns (**27 bundled** from 43 repos with patterns)

**Calibration Waves:**

| Wave | Repos | Method | Patterns |
|------|-------|--------|----------|
| Wave 1 (initial) | 25 repos | 18 API-calibrated + 7 git-only | 19 universal |
| Wave 2 (enrichment) | +21 new repos | 6 parallel Sonnet 4.5 agents, full API | +8 new universal |
| **Total** | **43 repos with patterns** | **40 unique fingerprints** | **27 universal** |

**Results:**
- 43 repos with discovered patterns across 8 languages (Go, Python, TypeScript, JavaScript, Rust, Ruby, Java, C++)
- 27 universal patterns (seen in 2+ repos) across 5 cross-family combinations
- 8 "confirmed" patterns seen in 5+ repos (highest confidence tier)
- Top: ci→dispersion↑ (9 repos), deploy→dispersion↑ (7 repos), dep→dispersion↑ (6 repos), ci→files_touched↑ (6 repos)
- Three discovery methods: Pearson correlation, lift-based co-occurrence, presence-based (Cohen's d)
- Wave 2 calibrated 495K events across 21 repos (3 timed out: angular, discourse, ladybird — >40K events)
- Pattern-richest repos: guava (7), devise (7), huginn (5), bat-api (7), excalidraw-api (7)

### 7.5 Priority 5: Fix Verification Loop (Phase 5 Extension) ✅

> **Status: ✅ Complete**

Implemented in `evolution/phase5_engine.py`:
- ✅ `verify(scope, compare_to)` method — compares current vs previous advisory
- ✅ `_diff_advisories()` — classifies changes as resolved/persisting/new/regression
- ✅ `_format_verification_summary()` — human-readable verification report
- ✅ Advisory diff engine matches changes by `family:metric_name` key
- ✅ Outputs `verification.json` and `verification.txt`

**Known limitation:** Regression classification matches by family rather than family:metric pair. Functionally acceptable but could be tightened.

### 7.6 Priority 6: Report Generator (Product Feature) ✅

> **Status: ✅ Complete — `evolution/report_generator.py` with 15 tests**

Standalone HTML report from Phase 5 advisory data.

**Implementation:**
- [x] CSS-only dark-theme HTML (no Jinja2 dependency — pure Python string rendering)
- [x] Header: repo name, date range, scope, generated timestamp
- [x] Summary stat cards: unusual changes, areas affected, known patterns, event groups
- [x] Change cards with risk-level badges (Low/Medium/High/Critical with color coding)
- [x] Table headers: "What Changed | Usual | Now | Risk" (PM-friendly)
- [x] Insight rows under each metric ("Larger changes carry more review risk")
- [x] Recurring Patterns section (Known Pattern / Emerging Pattern badges, friendly descriptions)
- [x] Evidence section: commit table, affected files, dependency changes, timeline
- [x] Responsive layout, print-friendly CSS
- [x] CLI command: `evo report [path]` with `--output`, `--title`, `--open` flags
- [x] 29 sample reports generated across all calibrated repos

### 7.7 Priority 7: Marketing & Product Launch ✅

> **Status: ✅ Complete**

Materials for product launch (not consulting outreach — see §8.1 for product vision).

- [x] **Sample reports:** 29 HTML reports from calibrated repos (hugo, rails, fastapi, etc.)
- [x] **Demo script:** `scripts/demo.sh` — full EE demo flow
- [x] **Landing page:** `website/` — Ocean Depth dark theme, deployed on Vercel (see §8.14)
- [x] **Docs page:** `website/docs.html` — Quickstart, CLI commands, adapter building guide
- [x] **Privacy page:** `website/privacy.html` — Telemetry transparency, what we collect/never collect
- [x] **README:** Updated with CLI docs, install instructions, quick start
- [x] **Quickstart guide:** `QUICKSTART.md`

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

- [x] 10+ validated cross‑family patterns (**27 universal from 43 repos**)
- [ ] 5+ per‑family baseline norms — *deferred to post-beta; baselines are per-repo by design*
- [ ] 3+ language‑specific false positives documented and suppressed — *deferred; 1.6% FP rate acceptable for launch*
- [x] Universal parameter defaults validated (min_correlation=0.3, min_support=3, Cohen's d>=0.2)
- [x] Confidence thresholds tuned per project size tier (min_control=30 for presence-based)

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

- [x] Pipeline produces correct results on real repos (fastapi validated, 43 repos with patterns)
- [x] `evo analyze .` works end-to-end without config
- [x] 534 tests pass with >80% coverage on core engines
- [x] KB security validates all imported patterns
- [x] 10+ universal patterns bundled in pip package (**27 bundled from 43 repos**)
- [x] False positive rate <10% on unseen repos (**1.6% on production-format repos**)
- [x] License key gates features correctly (free/pro tiers, HMAC-signed keys)
- [x] pip wheel installs and runs (`pip install -e .` → `evo analyze .` works)
- [x] Cython build infrastructure (`build_cython.py`) for proprietary engine protection
- [x] Landing page deployed (Vercel)
- [x] Stripe integration for Pro tier ($19/dev/month)
- [x] Opt-in telemetry with privacy transparency

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

### 8.5 Adapter Ecosystem — Registry + Plugins + Scaffold + Validation ✅

> **Status: ✅ Complete — `evolution/registry.py` + `evolution/adapter_validator.py` + `evolution/adapter_scaffold.py` with 56 tests**

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

**Adapter Scaffold (`evo adapter new`):**

Generates a complete pip-installable adapter package with boilerplate code, pyproject.toml,
tests, and README. Example:

```
$ evo adapter new jenkins --family ci
Created adapter package: ./evo-adapter-jenkins/
Next steps:
  1. cd evo-adapter-jenkins
  2. Edit evo_jenkins/adapter.py with your adapter logic
  3. pip install -e .
  4. evo adapter validate evo_jenkins.JenkinsAdapter
  5. pip install build && python -m build
  6. pip install twine && twine upload dist/*
```

Additional commands:
- `evo adapter guide` — prints the full plugin development guide
- `evo adapter request <desc>` — records an adapter request locally

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
evo patterns sync                # Import bundled universal patterns
evo adapter list                 # Show detected adapters + plugins
evo adapter validate <path>      # Certify a plugin adapter (13 checks)
evo adapter new <name> -f <fam>  # Scaffold a plugin adapter package
evo adapter guide                # Show plugin development guide
evo adapter request <desc>       # Request an adapter from the community
evo license status               # Show license tier and features
evo license activate <key>       # Save Pro license key
evo verify [previous]            # Compare against previous advisory
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

### 8.8 Community KB Sync ✅

> **Status: ✅ Complete — local auto-import + cloud sync module implemented**

**Completed:**
- [x] `evolution/data/universal_patterns.json` — bundled patterns shipped with package
- [x] Auto-import during `evo analyze` via `Orchestrator._import_universal_patterns()`
- [x] Manual sync via `evo patterns sync` CLI command
- [x] Idempotent import (fingerprint dedup, safe to run repeatedly)
- [x] Security validation on all imported patterns
- [x] `evolution/kb_sync.py` — opt-in push/pull with remote registry
- [x] `evolution/config.py` — persistent user preferences (~/.evo/config.toml)
- [x] `evo patterns pull` — fetch community patterns from registry
- [x] `evo patterns push` — share patterns (requires privacy_level >= 1)
- [x] `evo config list/get/set/reset` — manage user settings
- [x] 3 privacy levels: 0 (nothing), 1 (metadata only), 2 (anonymized digests)
- [x] 23 tests (16 in test_config.py, 16 in test_kb_sync.py)

### 8.9 Packaging & Distribution ✅

> **Status: ✅ Complete — pip package + Cython build + CI wheel builds**

**Completed:**
- [x] `pyproject.toml` with all dependencies, classifiers, package-data, project URLs
- [x] `pip install -e .` → `evo` CLI works
- [x] `python -m build` → wheel builds successfully
- [x] `evolution/data/*.json` included in wheel (universal patterns + adapter catalog)
- [x] Optional `[llm]` and `[dev]` dependency groups
- [x] `build_cython.py` — Cython build script with `--check`, `--clean`, `--package`
- [x] Compiles phase2-5 engines + knowledge_store to `.so` / `.pyd`
- [x] Open-source modules (CLI, adapters, registry) remain as Python
- [x] `MANIFEST.in` — includes LICENSE, README.md, data files for sdist
- [x] PyPI metadata: keywords, classifiers (Console, QA, Python 3.12, OS Independent)
- [x] CI wheel builds: `.github/workflows/build-wheels.yml` (cibuildwheel, Linux/macOS/Windows + PyPI publish)

### 8.10 License & Monetization ✅

> **Status: ✅ Complete — `evolution/license.py` with 27 tests + Stripe integration**

**Implemented:**
- [x] `License` dataclass with tier, features, validity, multi-source detection
- [x] `get_license()` — checks env var → `~/.evo/license.json` → repo `.evo/license.json`
- [x] HMAC-SHA256 signed keys with expiration support
- [x] Configurable signing key via `EVO_LICENSE_SIGNING_KEY` env var (production-ready)
- [x] `pro-trial` built-in trial key for development
- [x] Soft gating: clear upgrade messages, analysis continues on free tier
- [x] `evo license status` and `evo license activate <key>` CLI commands
- [x] Orchestrator gates LLM features and Tier 2 adapters behind Pro tier
- [x] Stripe Checkout integration (`website/api/create-checkout.py`) — $19/dev/month subscription
- [x] Stripe webhook (`website/api/webhook.py`) — auto-generates HMAC license key on purchase
- [x] License key retrieval (`website/api/get-license.py`) — post-checkout success page
- [x] Success page (`website/success.html`) — shows key with copy button + activation instructions

| Tier | Price | Adapters | Features |
|------|-------|----------|----------|
| Free | $0 | git + dependency + config | Local KB, template explanations, reports |
| Pro | $19/mo | all (CI, deploy, security) | AI investigation & fix, cross-signal patterns |
| Team | $99/mo/10 | all | Shared patterns (future) |
| Enterprise | custom | all | Self-hosted sync (future) |

### 8.11 Source Prescan — SDK Fingerprint Detection ✅

> **Status: ✅ Complete — `evolution/prescan.py` + `evolution/data/sdk_fingerprints.json` with 34 tests**
>
> Auto-detect external tools (Datadog, Sentry, New Relic, etc.) by scanning
> dependency lockfiles, config files, and import statements. Suggests adapters
> the user can optionally connect to enrich analysis.

**Three detection layers:**

| Layer | What it scans | Cost | Examples |
|-------|-------------|------|---------|
| Config files | Filenames in repo | ~0ms (Glob) | `sonar-project.properties`, `.snyk`, `datadog.yaml` |
| SDK packages | Already-parsed lockfiles | ~0ms (in-memory) | `dd-trace`, `@sentry/node`, `newrelic` |
| Import statements | Quick grep of source | ~1-2s | `import sentry_sdk`, `from datadog import` |

**Fingerprint database:** `evolution/data/sdk_fingerprints.json` — maps 20 services across 8 families:
- Monitoring: Datadog, New Relic, Grafana, Prometheus, OpenTelemetry, Elastic APM, Azure Monitor
- Error tracking: Sentry
- Incidents: PagerDuty, OpsGenie, Statuspage
- Security: Snyk, Semgrep
- Quality: SonarQube, Codecov
- Code review: Qodo, CodeRabbit
- Work items: Jira, Linear
- Feature flags: LaunchDarkly, Unleash

**CLI integration:**
- `evo sources` — shows connected + detected (hints, not pushes)
- `evo adapter list` — full catalog with detection status
- `evo sources --what-if <adapters>` — estimates cross-family impact without installing

**Key principle:** Soft sell. "We noticed `dd-trace` in your dependencies — here's what connecting Datadog would add." Always optional, user decides based on data.

**Tasks:**
1. [x] Implement `SourcePrescan` class — scans configs, lockfiles, imports against fingerprint DB
2. [x] Wire prescan into `evo sources` CLI command
3. [x] Wire prescan into `evo adapter list` (show detected status)
4. [x] Implement `--what-if` estimator (cross-family combination math + pattern type descriptions)
5. [x] Add prescan summary to `evo analyze` output (non-intrusive hint at bottom)

**Files:** `evolution/prescan.py`, `evolution/data/sdk_fingerprints.json`, 34 tests in `tests/unit/test_prescan.py`

### 8.12 AI Agent Integration — Detect → Investigate → Fix → Validate ✅

> **Status: ✅ Complete — all commands implemented and tested**
>
> The advisory's investigation prompt is already designed for AI agents.
> This section adds explicit CLI commands and a GitHub Action workflow
> that closes the loop: EE detects → AI investigates → AI fixes → EE validates.

**The feedback loop (iterates until EE confirms all clear):**
```
1. evo analyze .       → EE detects anomalies, drift, patterns
2. evo investigate .   → AI agent reads advisory, investigates root causes
3. evo fix .           → AI agent proposes fixes on branch
4. evo verify .        → EE re-analyzes: is the advisory resolved?
       │
   ┌───┴────────┐
   ALL CLEAR    RESIDUAL ISSUES
   Advisory     EE feeds remaining
   resolved →   findings back to
   ready for    AI agent → step 2
   human        (automatic iteration
   review       up to --max-iterations)
```

The loop is not one-shot — it iterates like a RALF (Review-Analyze-Loop-Fix) cycle.
The AI agent gets EE's residual findings as context for each iteration, so it
doesn't repeat failed fixes. The loop terminates when:
- **All advisory items resolved** (ideal outcome), or
- **Max iterations reached** (default 3) — human reviews remaining items, or
- **No progress** — same advisory after fix attempt → stops to avoid infinite loop

**Phase 1 — `evo investigate` (AI reads EE output):**
- Takes Phase 5 advisory JSON + investigation prompt
- Feeds into AI coding agent (Claude Code, Cursor, or any tool via `--agent` flag)
- Produces structured investigation report: root cause per finding, suggested fix, confidence
- Output: `investigation.json` + `investigation.txt`
- Fallback: `--show-prompt` prints the prompt for manual paste into any AI tool

**Phase 2 — `evo fix` (AI writes code, EE validates):**
- Reads investigation report
- AI agent creates branch, applies minimal targeted fixes
- Runs `evo verify` on the fix branch automatically
- If advisory clears: reports success, PR ready for human review
- If issues remain: reports residual findings, can iterate (`--max-iterations 3`)
- `--dry-run` previews changes without committing

**Phase 3 — GitHub Action (continuous loop on every PR):**
```yaml
- uses: evolution-engine/analyze@v1
  with:
    comment: true           # Risk summary on PR
    investigate: true       # AI investigation on High/Critical
    suggest-fixes: true     # Inline fix suggestions as review comments
    validate-on-push: true  # Re-run and compare on subsequent pushes
```
- On each push: EE compares current vs previous advisory
- PR comment updates: "3 of 6 issues resolved, 2 improving, 1 new regression"
- Loop continues until clear or team accepts residual risk

**Key design decisions:**
- **EE never auto-merges** — human always has final say
- **EE validates its own AI** — the fix loop prevents AI from introducing new drift
- **Agent-agnostic** — works with Claude Code, Cursor, Copilot, or custom scripts
- **Investigation prompt stays technical** — designed for machines, not PMs
- **PM report stays friendly** — designed for humans, not machines
- Two audiences, two outputs, one pipeline

**Tasks:**
1. [x] Implement `evo investigate` — feed advisory into AI agent, produce investigation report
2. [x] Implement `evo analyze . --show-prompt` — print investigation prompt to stdout
3. [x] Implement `evo fix . --dry-run` — AI agent proposes fixes, preview mode
4. [x] Implement `evo fix .` — create branch, apply fixes, run `evo verify` automatically
5. [x] Implement `--max-iterations` for fix loop (default 3)
6. [x] GitHub Action: `action/action.yml` with comment + investigate + validate
7. [x] GitHub Action: PR comment update on subsequent pushes (diff vs previous advisory)
8. [x] Agent abstraction layer — pluggable backends (Anthropic API, CLI, ShowPrompt)

**Files:** `evolution/investigator.py`, `evolution/fixer.py`, `evolution/agents/base.py`, `evolution/agents/anthropic_agent.py`, `evolution/agents/cli_agent.py`, `evolution/pr_comment.py`, `action/action.yml`, `action/format_comment.py`, `action/evo-monitor.yml` — 89 tests across test_agents.py, test_investigator.py, test_fixer.py, test_pr_comment.py

### 8.13 Opt-in Product Telemetry ✅

> **Status: ✅ Complete — `evolution/telemetry.py` + 12 tests**

Anonymous, opt-in usage telemetry to understand which commands/adapters are used.

**Implemented:**
- [x] `track_event(event_name, properties)` — fire-and-forget POST to telemetry endpoint
- [x] `prompt_consent()` — asks once on first `evo analyze`, default is No (opt-in only)
- [x] `_is_enabled()` — checks `DO_NOT_TRACK=1` env var, then config
- [x] `_get_anon_id()` — generates/persists UUID4 in `~/.evo/anon_id` (no PII)
- [x] Non-blocking: background thread with 2s timeout, never raises
- [x] Respects `DO_NOT_TRACK=1` standard env var (overrides config)
- [x] `evo telemetry on/off/status` CLI subcommand
- [x] Server-side: `website/api/telemetry.py` (Vercel serverless, rate limit 100/hr/anon_id)
- [x] Privacy page: `website/privacy.html` — full transparency on what is/isn't collected

**What we collect (when opted in):**
command name, adapter count, family list, signal count, pattern count, error type (if any), EE version, anonymous UUID

**What we NEVER collect:**
source code, file paths, repo names, git hashes, usernames, emails, IP addresses, advisory content, dependency names, stack traces

**Observability — Axiom Direct Ingest:**

Vercel Hobby plan does not support log drains (Pro-only feature). Instead, all API
endpoints POST structured events directly to Axiom's HTTP ingest API via a shared
helper (`website/api/_axiom.py`). Fire-and-forget with 2s timeout — never blocks
the response. No-op when `AXIOM_TOKEN` is not set (safe for local dev).

- [x] `website/api/_axiom.py` — shared `send(event)` helper
- [x] All 4 logging endpoints forward events: telemetry, webhook (license_generated, license_revoked), adapter-request
- [x] Consistent `"type"` field across all events for unified querying
- [x] Vercel env vars: `AXIOM_TOKEN` (API token) + `AXIOM_DATASET` (default: `evo`)
- [x] Axiom free tier: 500 GB/month ingest, 30-day retention (vs Vercel's 3-day)

**Files:** `evolution/telemetry.py`, `evolution/config.py` (defaults), `evolution/cli.py` (integration), `website/api/telemetry.py`, `website/api/_axiom.py`, `website/privacy.html` — 12 tests in `tests/unit/test_telemetry.py`

### 8.14 Website & Landing Page ✅

> **Status: ✅ Complete — deployed on Vercel**

Single-page dark-themed marketing site using CodeQual's "Ocean Depth" design system.

**Pages:**
- [x] `website/index.html` — Landing page (hero, features, how-it-works, signal families, adapter catalog, pricing)
- [x] `website/docs.html` — Documentation (quickstart, CLI commands, adapter building guide, adapter contract)
- [x] `website/privacy.html` — Privacy & telemetry transparency
- [x] `website/success.html` — Post-checkout license key display
- [x] `website/style.css` — Ocean Depth CSS (responsive, mobile/tablet/desktop)
- [x] `website/script.js` — Stripe checkout, mobile menu, copy-to-clipboard, adapter request modal

**Serverless API (Vercel):**
- [x] `website/api/create-checkout.py` — Stripe Checkout session creation
- [x] `website/api/webhook.py` — Stripe webhook (license key generation)
- [x] `website/api/get-license.py` — License key retrieval post-checkout
- [x] `website/api/telemetry.py` — Telemetry event ingestion
- [x] `website/api/adapter-request.py` — Adapter request → GitHub Issue creation
- [x] `website/api/_axiom.py` — Shared Axiom direct ingest helper (all endpoints forward events)

**Adapter Catalog:**
- [x] `evolution/data/adapter_catalog.json` — 26 adapters (9 available, 17 planned)
- [x] Grid display on landing page organized by family
- [x] "Build Your Own" card linking to docs
- [x] "Request an Adapter" modal → creates GitHub Issue

**Deployment:**
- [x] `website/vercel.json` — Routes for API, static, SPA fallback
- [x] `website/requirements.txt` — Stripe dependency for serverless functions
- [x] Env vars configured: STRIPE_SECRET_KEY, STRIPE_PRICE_ID, STRIPE_WEBHOOK_SECRET, BASE_URL, EVO_LICENSE_SIGNING_KEY, AXIOM_TOKEN, AXIOM_DATASET

### 8.15 Future Enhancements

- PostgreSQL + pgvector migration (multi-tenant, when SaaS tier exists)
- Additional vendor adapters (GitLab CI, Jenkins, npm, Cargo, etc.)
- Real-time event streaming (webhooks vs batch polling)
- IDE extensions (VS Code, JetBrains) — surfaces advisories where code is written
- Trend dashboard — multi-run advisory comparison over time

---

## 9. Product Delivery — CLI‑First Strategy

> **Updated (February 2026):** Delivery priority inverted from the original plan.
> CLI is now **first**, not last. Local-first is the product identity.

### Delivery Channel Priority (Revised)

| Priority | Channel | Effort | Status |
|----------|---------|--------|--------|
| **1** | CLI Tool (`evo analyze .`) | Low | ✅ Complete (25+ commands) |
| **2** | pip package (pure Python) | Low | ✅ Complete (`pip install -e .`) |
| **2b** | pip package (Cython compiled) | Medium | 🔄 Build script done, CI wheels pending |
| **3** | GitHub Action (CI integration) | Medium | ✅ Complete (`action/action.yml`) |
| **4** | API Service / SaaS | High | Deprioritized |
| **5** | Web Dashboard | High | Deprioritized |

### 9.1 CLI Tool ✅

**Already built.** See §8.6 for details.

`evo analyze .` → detects adapters → ingests data → Phase 2-5 → advisory.

### 9.2 pip Package ✅

**Pure Python — Complete:**
- `pip install -e .` → `evo analyze .` works
- Universal patterns bundled as `evolution/data/universal_patterns.json`
- Works offline, no account required for free tier

**Cython Compilation — Complete:**
- [x] `build_cython.py` compiles phase engines to `.so` / `.pyd`
- [x] CI builds wheels for Linux (x86_64, aarch64), macOS (arm64, x86_64), Windows (`.github/workflows/build-wheels.yml`)

### 9.3 GitHub Action ✅

- [x] `action/action.yml` — composite action: setup → analyze → investigate → comment → verify
- [x] `action/format_comment.py` — standalone script for CI comment formatting
- [x] `action/evo-monitor.yml` — sample workflow template
- [x] `evolution/pr_comment.py` — PR comment formatting with risk badges
- [x] PR comment with "normal vs now" summary
- [x] Advisory annotation (never blocking — purely informational)
- [x] AI investigation on High/Critical findings
- [x] Verify on subsequent pushes (resolved/persisting/new/regressions)
- [x] Uses existing CLI under the hood

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

---

## 11. Execution Summary

| Component | Status | What It Does |
|-----------|--------|-------------|
| **Phase 1** | ✅ Complete | Record immutable events from all sources |
| **Phase 2** | ✅ Complete | Compute baselines (MAD/IQR), emit deviation signals |
| **Phase 3** | ✅ Complete | Explain signals in PM-friendly language (LLM retired) |
| **Phase 4** | ✅ Complete | Discover cross-family patterns, KB learning |
| **Phase 5** | ✅ Complete | Advisory reports + evidence + fix verification |
| **Data Quality (6 waves)** | ✅ Complete | Robust deviation math, clean metric set |
| **Git History Walker** | ✅ Complete | 8 lockfile formats, 3 families from git |
| **GitHub API Adapters** | ✅ Complete | CI, deployment, security from GitHub API |
| **Adapter Registry** | ✅ Complete | Zero-config detection (Tier 1 file, Tier 2 API, Tier 3 plugins) |
| **Adapter Scaffold** | ✅ Complete | `evo adapter new` generates pip-installable plugin packages |
| **CLI Tool (`evo`)** | ✅ Complete | 25+ commands — primary user interface |
| **KB Security** | ✅ Complete | Validates all imported patterns (10+ attack vectors) |
| **KB Export/Import** | ✅ Complete | Anonymous pattern sharing with security gate |
| **Batch Calibration** | ✅ Complete | 43 repos with patterns, 27 universal patterns bundled |
| **Universal Pattern Sync** | ✅ Complete | Auto-import bundled patterns + `evo patterns sync` |
| **Report Generator** | ✅ Complete | PM-friendly HTML report with risk badges and insights |
| **License System** | ✅ Complete | Free/Pro tier gating with HMAC-signed keys |
| **Packaging (pip)** | ✅ Complete | `pip install -e .` → `evo analyze .` works |
| **Test Suite** | ✅ Complete | 542 tests, 1.5s, >80% core coverage |
| **Source Prescan** | ✅ Complete | SDK fingerprint detection (Datadog, Sentry, etc.) |
| **AI Agent: investigate** | ✅ Complete | Feed advisory into AI agent for root cause analysis |
| **AI Agent: fix + validate** | ✅ Complete | AI proposes fixes, EE validates until clear |
| **GitHub Action** | ✅ Complete | CI integration (PR comments + investigate + validate loop) |
| **Community KB Cloud Sync** | ✅ Complete | Opt-in pattern sharing to registry |
| **Packaging (Cython)** | 🔄 Build script done | Compiled wheels — CI builds pending |
| **Configurable License Key** | ✅ Complete | `EVO_LICENSE_SIGNING_KEY` env var for production |
| **Opt-in Telemetry** | ✅ Complete | Anonymous usage stats, `DO_NOT_TRACK` support, 12 tests |
| **Axiom Observability** | ✅ Complete | Direct ingest from all API endpoints, 30-day retention (free tier) |
| **Website & Landing Page** | ✅ Complete | Ocean Depth theme, Vercel deployed, docs + privacy pages |
| **Stripe Integration** | ✅ Complete | Checkout, webhook, license generation, success page |
| **Adapter Catalog** | ✅ Complete | 26 adapters, request system → GitHub Issues |

### Execution Timeline

```
Engine (Done)         Open-Core (Done)              Product (Done)
─────────────         ────────────────              ──────────────
Phase 1-5 ✅          Adapter Registry ✅            Batch Calibration ✅
6-Wave Fix ✅         CLI (25+ commands) ✅          Report Generator ✅
Adapters ✅           KB Security ✅                 Universal Sync ✅ (27 patterns)
Walker ✅             KB Export/Import ✅            License System ✅
GitHub API ✅         Adapter Scaffold ✅            pip Package ✅
                      534 Tests ✅                   PM-Friendly UX ✅
                                                     Integrations Doc ✅
                                                     Market Research ✅

Priority 1 ✅         Priority 2 ✅                  Priority 3 ✅         Priority 4 ✅
──────────            ──────────                    ──────────            ──────────
Source Prescan ✅      evo investigate ✅             GitHub Action ✅       Enrich Patterns ✅
                      evo fix ✅                     Inline suggestions ✅  Cython Wheels ✅
                                                                           Cloud KB Sync ✅

Priority 5 ✅ (Product Launch)
──────────
Configurable signing key ✅     Website (Vercel) ✅
Opt-in telemetry ✅             Stripe Pro checkout ✅
PyPI metadata ✅                Adapter catalog ✅
Docs page ✅                    Privacy page ✅
```

### Immediate Next Actions

**Completed (1–30):**
1. ~~Build Git History Walker Adapter~~ ✅
2. ~~Build GitHub API Adapters~~ ✅
3. ~~6-Wave Data Quality Fix~~ ✅
4. ~~Adapter Auto-Detection Registry~~ ✅
5. ~~CLI Tool (evo analyze .)~~ ✅
6. ~~KB Security Validation~~ ✅
7. ~~KB Export/Import~~ ✅
8. ~~Test Suite (534 tests)~~ ✅
9. ~~Seed Universal Patterns~~ ✅ (27 patterns from 43 repos)
10. ~~Community KB Local Sync~~ ✅ (auto-import + `evo patterns sync`)
11. ~~Report Generator~~ ✅ (`evo report` → standalone HTML)
12. ~~pip Packaging~~ ✅ (wheel builds, `evo` CLI works)
13. ~~License System~~ ✅ (free/pro gating, HMAC keys)
14. ~~PM-Friendly UX Rewrite~~ ✅ (all display layers use plain English, Phase 3.1 LLM retired)
15. ~~SDK Fingerprint Prescan~~ ✅ (`evo sources`, `--what-if`)
16. ~~evo investigate~~ ✅ (AI agent root cause analysis)
17. ~~evo fix + validate loop~~ ✅ (RALF-style fix-verify)
18. ~~GitHub Action~~ ✅ (PR comments + investigate + validate + inline suggestions)
19. ~~Enrich Universal Patterns~~ ✅ (27 from 43 repos)
20. ~~Cython Compilation~~ ✅ (`build_cython.py`)
21. ~~Cloud KB Sync~~ ✅ (`evolution/kb_sync.py`)
22. ~~Marketing materials~~ ✅ (demo script, quickstart, integrations doc)
23. ~~FP Validation~~ ✅ (1.6% FP rate)
24. ~~CI Wheel Builds~~ ✅ (cibuildwheel, Linux/macOS/Windows)
25. ~~Inline Fix Suggestions~~ ✅ (`evolution/inline_suggestions.py`)
26. ~~Configurable License Signing Key~~ ✅ (`EVO_LICENSE_SIGNING_KEY` env var)
27. ~~Opt-in Product Telemetry~~ ✅ (`evolution/telemetry.py`, 12 tests)
28. ~~Website & Landing Page~~ ✅ (Ocean Depth theme, Vercel deployed)
29. ~~Stripe Pro Integration~~ ✅ (checkout, webhook, license generation)
30. ~~Adapter Catalog & Requests~~ ✅ (26 adapters, GitHub Issue creation)

**Completed (31):**
31. ~~Axiom observability~~ ✅ — direct ingest from all API endpoints (bypasses Vercel Pro log drain requirement)

**Next — PyPI & Beta:**
32. **PyPI publication** — `python -m build && twine upload dist/*`
33. **Stripe end-to-end test** — test purchase in sandbox, verify license key
34. **Custom domain** — configure codequal.dev for Vercel
35. **Community beta** — announce, gather feedback

**See `docs/LAUNCH_PLAN.md`** for detailed beta program, launch timeline, and go-to-market strategy.

---

## 12. Launch Checklist

The remaining items before public beta:

| # | Task | Effort | Blocker? |
|---|------|--------|----------|
| 31 | ~~Axiom observability~~ ✅ — direct ingest, 30-day retention | Done | — |
| 32 | **PyPI publication** — `python -m build && twine upload dist/*` | Low | Yes — users can't `pip install` without it |
| 33 | **Stripe end-to-end test** — sandbox purchase, verify license key generation | Low | Yes — must work before accepting payments |
| 34 | **Custom domain** — configure codequal.dev for Vercel | Low | No — vanity URL, current `.vercel.app` works |
| 35 | **Community beta** — announce, gather feedback | Low | No — can begin once 32+33 are verified |

---

## 13. Plan Maintenance

- This document is updated **only** when a phase is completed or reordered.
- Changes must reference Architecture Vision principles.
- Research documents inform changes but do not override this plan.

---

> **Summary (February 11, 2026):**
>
> **All priorities complete. Product launch infrastructure deployed.** All 5 engine phases,
> open-core infrastructure, AI agent integration, GitHub Action, source prescan, cloud sync,
> Cython build, FP validation, inline suggestions, CI wheel builds, website, Stripe integration,
> and opt-in telemetry are implemented. **534 tests passing (1.53s).** The full pipeline runs
> end-to-end in 6.6 seconds on fastapi (27,390 signals, 6 significant changes).
>
> **What's built:**
> - `evo analyze .` — zero-config CLI with 25+ commands
> - PM-friendly output across all display layers (risk labels, relative comparisons, practical insights)
> - `evolution/friendly.py` — centralized formatting helpers (no jargon in user-facing text)
> - Phase 3.1 LLM retired (~$12/repo savings) — templates now produce equivalent quality
> - 3-tier adapter ecosystem (built-in, API, plugins) with scaffold and validation
> - License system (free/pro tiers, HMAC-signed keys, configurable signing key, Stripe checkout)
> - HTML report generator (`evo report`) with risk badges, insight rows, friendly patterns
> - **27 universal patterns bundled** from 43 repos across 8 languages (Go, Python, TS, JS, Rust, Ruby, Java, C++)
> - 8 "confirmed" patterns seen in 5+ repos — top: ci→dispersion↑ (9 repos), deploy→dispersion↑ (7 repos)
> - Universal pattern sync (auto-import during analyze + manual `evo patterns sync`)
> - KB security (validates all imported patterns against 10+ attack vectors)
> - SDK fingerprint database for 20 external services (Datadog, Sentry, etc.)
> - Source prescan (`evo sources`) — 3-layer detection (config, lockfiles, imports)
> - AI agent integration (`evo investigate`, `evo fix`) — RALF-style fix-verify loop
> - GitHub Action (`action/action.yml`) — PR comments with risk + investigation + verify + inline suggestions
> - Cloud KB sync (`evo patterns pull/push`) — opt-in anonymous pattern sharing
> - User config (`evo config`) — persistent preferences in ~/.evo/config.toml
> - Cython build script (`build_cython.py`) — IP protection for phase engines
> - CI wheel builds (`.github/workflows/build-wheels.yml`) — cibuildwheel for Linux/macOS/Windows + PyPI publish
> - FP validation (`evolution/fp_validation.py`) — 1.6% FP rate on production-format repos
> - Inline fix suggestions (`evolution/inline_suggestions.py`) — GitHub PR review comments from AI investigation
> - Demo script (`scripts/demo.sh`) + quickstart guide (`QUICKSTART.md`)
> - **Website** (`website/`) — Ocean Depth dark theme on Vercel (landing, docs, privacy, success pages)
> - **Stripe integration** — Pro subscription checkout, webhook license generation, success page
> - **Opt-in telemetry** (`evolution/telemetry.py`) — anonymous usage stats, DO_NOT_TRACK support
> - **Adapter catalog** (`evolution/data/adapter_catalog.json`) — 26 adapters with request system
> - **Axiom observability** (`website/api/_axiom.py`) — direct ingest from all API endpoints (30-day retention, bypasses Vercel Pro log drain)
>
> **Remaining:**
> - PyPI package publication
> - Stripe checkout end-to-end test (+ `allow_promotion_codes=True` for beta discounts)
> - Custom domain (codequal.dev) for Vercel
> - Community beta launch (see `docs/LAUNCH_PLAN.md` for full timeline)
>
> **New (February 11, 2026):**
> - Report: severity badges, risk banners, pattern grouping, IP sanitization
> - `friendly.py`: pattern descriptions generated from structured fields, statistical internals stripped
> - Website: language switcher fix (i18n routes + absolute paths)
> - Launch plan: `docs/LAUNCH_PLAN.md` — beta program, Stripe discounts, Show HN timeline, EU AI Act compliance
> - 545 tests passing (1.54s)
>
> **The engagement flow:**
> ```
> evo analyze → Advisory → AI investigates → AI fixes → evo verify
>                                                          │
>                                                    PASS? ─┤
>                                                    Yes: done
>                                                    No: loop back ↑
> ```
