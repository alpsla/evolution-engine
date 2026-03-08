# Evolution Engine — Implementation Plan

> **Last updated:** March 8, 2026 | 1770 tests passing | v0.3.0 | 44 universal patterns | 7 signal families | 200+ repos calibrated
>
> This document tracks remaining work for launch and post-launch.
> For completed implementation history, see `IMPLEMENTATION_PLAN_v1.md`.

---

## What's Built (Complete)

All core engine work is done. Summary of shipped features:

| Area | Status | Key Files |
|------|--------|-----------|
| 5-phase pipeline (events → signals → explanations → patterns → advisory) | ✅ | `evolution/phase*.py` |
| 7 signal families (git, ci, deployment, dependency, testing, coverage, error_tracking) | ✅ | `evolution/adapters/`, `phase2_engine.py` |
| CLI with 30+ commands (`evo analyze`, `verify`, `accept`, `investigate`, `fix`, etc.) | ✅ | `evolution/cli.py` |
| 3-tier adapter ecosystem (built-in, API, plugins) with scaffold/validate/security | ✅ | `evolution/adapter_*.py` |
| Source prescan (`evo sources`, `--what-if`) | ✅ | `evolution/prescan.py` |
| AI agents (`evo investigate`, `evo fix`) — RALF-style fix-verify loop | ✅ | `evolution/investigator.py`, `fixer.py` |
| GitHub Action — PR comments, verify, inline suggestions | ✅ | `action/action.yml` |
| Interactive HTML report with Accept buttons, evidence in prompts | ✅ | `evolution/report_generator.py`, `report_server.py` |
| Accept deviations — scoped (permanent, commits, dates, this-run) | ✅ | `evolution/accepted.py` |
| Run history — snapshot, compare, clean | ✅ | `evolution/history.py` |
| Pattern distribution — PyPI auto-fetch, KB sync, registry | ✅ | `evolution/pattern_registry.py`, `kb_sync.py` |
| 44 universal patterns from 200+ repos (3 calibration rounds) | ✅ | `evolution/data/universal_patterns.json` |
| License system — free/pro tiers, HMAC-signed keys, Stripe checkout | ✅ | `evolution/license.py` |
| Cython compilation + CI wheels (Linux/macOS/Windows) | ✅ | `build_cython.py`, `.github/workflows/build-wheels.yml` |
| Website — codequal.dev on Vercel (landing, docs, privacy, Stripe, pattern registry) | ✅ | `website/` |
| SDLC integration — init wizard, git hooks, watcher daemon, setup UI | ✅ | `evolution/init.py`, `hooks.py`, `watcher.py`, `setup_ui.py` |
| PR acceptance flow — 3 options, scope, webhook persistence | ✅ | `evolution/pr_comment.py`, `website/api/accept.py` |
| GitLab CI integration — `.gitlab-ci.yml` template, MR comments, platform-aware accept | ✅ | `evolution/init.py`, `evolution/format_comment.py` |
| FP validation — 1.6% rate | ✅ | `evolution/fp_validation.py` |
| Sentry error tracking adapter — error_tracking family (#51b) | ✅ | `evolution/adapters/error_tracking/sentry_adapter.py` |
| Calibration v3 — 48/51 repos, 44 patterns, parallel runner | ✅ | `.calibration/`, `scripts/aggregate_calibration.py` |
| HTML report adapter cards — "Expand Your Coverage" section | ✅ | `evolution/report_generator.py` |
| Website Pro tier — pricing, adapter catalog, i18n (en/de/es) for all pages | ✅ | `website/` |
| UX overhaul — 15 fixes (§13 of v1 plan) + sources/config/adapter UX (#46-48) | ✅ | Multiple files |
| Historical trend detection — three-category classification | ✅ | `evolution/phase5_engine.py` |
| Pre-launch hardening — security fixes, signing key deployment | ✅ | Multiple files |
| Adapter diagnostics — source status cards, badges, integration hints across HTML/CLI/PR | ✅ | `report_generator.py`, `pr_comment.py`, `phase5_engine.py`, `cli.py` |
| Website integrations guide — troubleshooting, nav link on all pages | ✅ | `website/integrations.html`, all `website/*.html` |
| Website SEO — robots.txt, sitemap.xml, Schema.org JSON-LD, meta tags, canonical URLs, hreflang | ✅ | `website/robots.txt`, `sitemap.xml`, all `website/*.html` |

---

## Remaining Work

### Pre-Deployment Manual Testing (Blockers)

| # | Task | Platform | Effort | Status |
|---|------|----------|--------|--------|
| 45b | **Acceptance persistence** — deploy webhook, test `/evo accept` + `/evo accept permanent` on real PR | GitHub | Low | **Complete** ✅ |
| 45c | **Accept comment cache fix** — in-place comment modification instead of cache-dependent regeneration | GitHub | Low | **Complete** ✅ |
| GH-WF | **GitHub Action workflow** — trigger on real PR, verify PR comment, inline suggestions, accept flow, verify flow | GitHub | Low | **Complete** ✅ |
| 37 | **GitLab CLI manual testing** — 7 CLI scenarios on real GitLab repo (see v1 plan §12.2) | GitLab | Low | **Complete** ✅ |
| GL-WF | **GitLab CI workflow** — trigger on real MR, verify MR comment, accept flow, verify flow | GitLab | Low | **Complete** ✅ |
| 50 | **GitLab CI integration** — `.gitlab-ci.yml` template, MR comments, platform-aware accept | GitLab | Medium | **Complete** ✅ |

#### 45b — Acceptance Persistence Testing Plan

**Webhook endpoint (codequal.dev/api/accept):**

1. Push to deploy (auto-deploys from main)
2. Set `EVO_ACCEPT_SECRET` env var on Vercel project
3. Test POST:
   ```bash
   SECRET="<value>"
   REPO="alpsla/evolution-engine"
   SIG=$(echo -n "$REPO" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')
   curl -X POST https://codequal.dev/api/accept \
     -H "Content-Type: application/json" \
     -d "{\"repo\":\"$REPO\",\"signature\":\"$SIG\",\"entries\":[{\"key\":\"git:dispersion\",\"family\":\"git\",\"metric\":\"dispersion\",\"reason\":\"Test\",\"accepted_by\":\"manual\"}]}"
   ```
4. Test GET:
   ```bash
   curl "https://codequal.dev/api/accept?repo=alpsla/evolution-engine"
   ```
5. Verify Redis storage via Upstash console

**GitHub Action flow:**

1. Set `EVO_ACCEPT_SECRET` as repository secret
2. Open a PR that triggers EE findings
3. Verify PR comment shows 3 options (A: Fix, B: Accept for this PR, C: Accept permanently)
4. Comment `/evo accept` → verify comment updates to "Accepted for this PR"
5. Push again → verify findings reappear (PR-scoped, not permanent)
6. Comment `/evo accept permanent` → verify comment updates to "Accepted permanently"
7. Open new PR → verify permanently accepted findings are suppressed (pulled from webhook)

#### 45c — Accept Comment Cache Fix (Complete)

**Problem:** The `/evo accept` flow on GitHub Actions failed to update the PR comment because of cache branch scoping:
- Analysis runs on `pull_request` event → saves advisory cache on the PR branch
- Accept runs on `issue_comment` event → always runs on `main` → can't access PR branch cache
- Without the advisory, `format_comment.py` generated an empty accepted comment

**Fix:** In-place comment modification. Instead of regenerating from advisory JSON, the accept handler now fetches the existing comment body via `gh api` and transforms the markdown directly:
1. Inserts `✅ **Accepted for this PR**` banner after the header
2. Removes the "What To Do Next" section (or "Continue Fixing" for verification comments)
3. Strips old footer, adds `<sub>Accepted by @username</sub>`
4. For `/evo accept permanent`, parses `family:metric` pairs from the findings table for webhook push

**Removed steps (all depended on broken advisory cache):**
- Checkout for accept, Install Evolution Engine for accept
- Restore cached advisory, Persist acceptance to accepted.json, Cache accepted.json

**Files changed:** `action/action.yml`

#### 50 — GitLab CI Integration (Complete)

**Implemented:** Full GitLab CI parity with GitHub Action.

| Component | GitHub | GitLab |
|-----------|--------|--------|
| CI workflow template | ✅ `action/action.yml` | ✅ `.gitlab-ci.yml` (generated by `evo init`) |
| PR/MR comment posting | ✅ `gh api` | ✅ GitLab API v4 `/notes` |
| Accept on MR | ✅ `/evo accept` comment | ✅ `evo accept` locally + commit + push |
| Verification flow | ✅ re-analyze on push | ✅ re-analyze on push |
| Sources section | ✅ GITHUB_TOKEN hints | ✅ GITLAB_TOKEN hints |
| Webhook (accept.py) | ✅ | ✅ (repo-agnostic) |

**Key files:**
- `evolution/init.py` — detection (`has_gitlab`, `ci_provider`), `_GITLAB_CI_TEMPLATE`, `generate_gitlab_ci()`, `_write_gitlab_ci()`
- `evolution/format_comment.py` — canonical CLI module (`python -m evolution.format_comment`)
- `evolution/pr_comment.py` — `ci_provider` param on all format functions
- 30 new tests across `test_init.py` and `test_pr_comment.py`

**Design decision:** GitLab has no `issue_comment` event trigger, so acceptance uses local `evo accept` + commit + push instead of MR comment commands.

---

### UX & Polish

| # | Task | Effort | Blocker? | Status |
|---|------|--------|----------|--------|
| 46 | **`evo sources` UX fixes** — dynamic token hints, PyPI availability, scaffold hints | Medium | Yes — users hit this early | **Complete** ✅ |
| 47 | **Config cleanup** — fix `report.auto_open` → `hooks.auto_open` bug, binary privacy fallback | Medium | Yes — config is first impression | **Complete** ✅ |
| 48 | **Adapter discovery UX** — friendlier messages, `evo sources` hint in setup wizard | Medium | No — polish | **Complete** ✅ |

**What was done:**

**#46 — `evo sources` fixes:**
- Dynamic token hints from `TIER2_DETECTORS` — only shows tokens not already set in env
- Per-service PyPI availability check — shows `pip install` for published adapters, scaffold hint for unpublished
- Removed hardcoded `GITHUB_TOKEN` hint

**#47 — Config cleanup:**
- Fixed `report.auto_open` → `hooks.auto_open` (was reading/writing phantom key)
- Fixed privacy fallback from `[0, 1, 2]` → `[0, 1]` (binary, matches `_METADATA`)

**#48 — Adapter discovery UX:**
- "Not yet on PyPI" → "Community adapters — request or build your own"
- Notification message: "coming soon" → "community adapter in development. Scaffold your own: evo adapter new"
- Added "Run 'evo sources' to see how connecting these tools enriches analysis" hint in setup wizard

**Tests:** 11 new tests in `test_setup_cli.py`, `test_sources_cli.py` (new), `test_notifications.py`

---

### Adapter Expansion (New Families & Metrics)

Calibration across 200+ repos (3 rounds) showed pattern discovery has saturated with the current 4 families (git, ci, deployment, dependency). Adding new adapters unlocks new cross-family pattern combinations. Now at 6 families (+ testing, coverage).

**Sorted by priority (severity of impact on pattern discovery):**

| # | Task | Effort | Unlocks | Priority |
|---|------|--------|---------|----------|
| 55 | **Missing walker parsers** — pnpm-lock.yaml, pyproject.toml, composer.lock | **Low** | dependency for repos already cloned but missed | **Complete** ✅ |
| 51 | **Gradle/Maven lockfile support** — `build.gradle`, `build.gradle.kts`, `pom.xml` | Medium | dependency for Java ecosystem (5+ repos) | **Complete** ✅ |
| 52 | **GitLab CI API adapter** — pipelines + releases API | Medium | ci + deployment for all GitLab repos | **Complete** ✅ |
| 56 | **CircleCI API adapter** — mirror GitHub Actions adapter | Medium | ci for CircleCI repos (4 repos in calibration set) | **Complete** ✅ |
| 53 | **Test results parsing** — JUnit XML → testing family | Medium | Entirely new testing family | **Complete** ✅ |
| 57 | **CMake dependency extraction** — parse `CMakeLists.txt` for find_package/FetchContent | Low | dependency for C/C++ (5 repos) | **Complete** ✅ |
| 54 | **Code coverage metric** — Cobertura XML → coverage family | Low | New coverage family: line_rate, branch_rate | **Complete** ✅ |
| 58 | **Swift Package Manager** — `Package.resolved` | Low | dependency for Swift/iOS | **Complete** ✅ |
| 51b | **Sentry adapter** — error tracking → new error_tracking family | Medium | error×git, error×deployment patterns | **Complete** ✅ |

#### 55 — Missing Walker Parsers (Critical — Quick Win)

**Problem:** The prescan detects pnpm-lock.yaml and composer.lock, but the `GitHistoryWalker` has NO parser for them. pyproject.toml is detected but not walked. This means 21+ repos in our calibration set silently lost dependency signals.

| File | In prescan? | In walker? | Repos affected |
|------|------------|------------|----------------|
| `pnpm-lock.yaml` | ✅ | ❌ | **13 repos** |
| `pyproject.toml` | ✅ | ❌ | **8 repos** |
| `composer.lock` | ✅ | ❌ | unknown |

**Files to modify:**
- `evolution/adapters/git/git_history_walker.py`:
  - Add `pnpm-lock.yaml` to `dependency_parsers` + `_parse_pnpm_lock_content()` — YAML format, count packages
  - Add `pyproject.toml` to `dependency_parsers` + `_parse_pyproject_content()` — TOML, count `[project.dependencies]` + `[project.optional-dependencies]`
  - Add `composer.lock` to `dependency_parsers` + `_parse_composer_lock_content()` — JSON, count `packages` array
- Tests for each parser

**This is the highest-ROI task** — fixing 3 parsers immediately gives dependency signals to 21+ repos that are already cloned and calibrated. Re-running calibration after this fix should yield new patterns.

#### 51 — Gradle/Maven Lockfile Support

**Problem:** Java repos (kafka, elasticsearch, spring-boot, fdroidclient) get git-only signals. 5 repos in calibration have `build.gradle`, 1 has `pom.xml`.

**Files to modify:**
- `evolution/adapters/git/git_history_walker.py` — add parsers:
  - `_parse_gradle_content()` — regex for `implementation`, `api`, `compile` declarations
  - `_parse_pom_content()` — XML parse `<dependency>` blocks, count artifacts
  - Add `build.gradle`, `build.gradle.kts`, `pom.xml` to walker file lists
- `evolution/prescan.py` — add `build.gradle`, `pom.xml` to config file detection
- Tests for each parser

**Test repos:** apache/kafka, elastic/elasticsearch, spring-projects/spring-boot, fdroid/fdroidclient (GitLab)

#### 52 — GitLab CI API Adapter

**Problem:** GitLab repos get no CI or deployment signals. Need API adapters mirroring the GitHub ones.

**Files to create:**
- `evolution/adapters/gitlab_client.py` — API client
  - Uses `$CI_API_V4_URL` (works on self-hosted) or defaults to `https://gitlab.com/api/v4`
  - Rate limit: 300 req/min (authenticated), auto-backoff
  - Auth: `GITLAB_TOKEN` env var
- `evolution/adapters/ci/gitlab_ci_adapter.py` — pipelines + jobs
  - `GET /projects/:id/pipelines` → list pipeline runs
  - `GET /projects/:id/pipelines/:id/jobs` → job details, timing
  - Same event format as GitHub Actions adapter: `run_duration`, `run_failed`
- `evolution/adapters/deployment/gitlab_releases_adapter.py` — releases
  - `GET /projects/:id/releases` → release metadata
  - Same metrics: `release_cadence_hours`, `is_prerelease`, `asset_count`
- `evolution/prescan.py` — route to GitLab adapters when `.gitlab-ci.yml` detected or remote is gitlab
- `evolution/orchestrator.py` — integrate GitLab adapters into pipeline

**Test repos:** gitlab-org/gitlab-runner, inkscape/inkscape, gnome/gnome-shell

#### 56 — CircleCI API Adapter

**Problem:** 4 repos in calibration set use CircleCI. No CI signals for them.

**Files to create:**
- `evolution/adapters/ci/circleci_adapter.py`
  - CircleCI API v2: `GET /project/{vcs}/{org}/{repo}/pipeline` → pipelines
  - `GET /pipeline/{id}/workflow` → workflows + jobs
  - Same metrics: `run_duration`, `run_failed`
  - Auth: `CIRCLECI_TOKEN` env var
- `evolution/prescan.py` — detect `.circleci/config.yml`

#### 53 — Test Results Parsing (Complete ✅)

**Implemented:** JUnit XML → testing family. Full pipeline wiring: detection → walker → Phase 1-5.

| Component | What was done |
|-----------|--------------|
| `evolution/registry.py` | 4 JUnit XML patterns in TIER1_DETECTORS |
| `evolution/adapters/git/git_history_walker.py` | `_parse_junit_xml_content()`, testing blocks in both commit processors |
| `evolution/orchestrator.py` | `testing` in walker_families routing |
| Phase 2-5 | Already existed — just needed wiring |
| Tests | 8 new tests (parser, walker integration, Phase 2 signals) + 2 registry tests |

**Phase 2 metrics:** `total_tests`, `failure_rate`, `skip_rate`, `suite_duration`

#### 57 — CMake Dependency Extraction

**Problem:** 5 repos in calibration use CMake. C/C++ projects get no dependency signals.

**Files to modify:**
- `evolution/adapters/git/git_history_walker.py`:
  - `_parse_cmake_content()` — extract `find_package()`, `FetchContent_Declare()`, `target_link_libraries()`
  - Count unique external dependencies per commit
  - Add `CMakeLists.txt` to walker file lists
- `evolution/prescan.py` — add CMake detection

#### 54 — Code Coverage Metric (Complete ✅)

**Implemented:** Cobertura XML → coverage family. New 6th signal family with own Phase 2 engine, signal file, and Phase 5 labels.

| Component | What was done |
|-----------|--------------|
| `evolution/registry.py` | 3 Cobertura XML patterns in TIER1_DETECTORS |
| `evolution/adapters/testing/coverage_adapter.py` | **NEW** — `CoberturaAdapter` class |
| `evolution/adapters/git/git_history_walker.py` | `_parse_cobertura_xml_content()`, coverage blocks |
| `evolution/phase2_engine.py` | `run_coverage()` method, wired into `run_all()` + `run_all_parallel()` |
| `evolution/phase3_engine.py` | `coverage_signals.json` mapping |
| `evolution/phase5_engine.py` | `coverage_signals.json`, "Code Coverage" label, metric labels |
| `evolution/orchestrator.py` | `coverage` in walker_families routing |
| Tests | 9 new tests + 1 registry test |

**Phase 2 metrics:** `line_rate`, `branch_rate`

#### 58 — Swift Package Manager

**Files to modify:**
- `evolution/adapters/git/git_history_walker.py` — `_parse_package_resolved_content()`
  - JSON format, count `pins` array
- Add `Package.resolved` to walker + prescan

#### Post-Adapter Calibration Plan

All adapter expansion tasks (#51-58) are now **complete**. EE has 7 signal families: git, ci, deployment, dependency, testing, coverage, error_tracking.

**Calibration v3 — Complete:**
- 48/51 repos successful (3 failed: elasticsearch, spring-boot, nixpkgs — memory/timeout)
- 2.17M events, 6.18M signals
- 44 universal patterns (net +2 from v2)
- Testing/coverage families produced no new universal patterns — JUnit XML and Cobertura XML are CI artifacts not committed to git history, so the walker can't find them. These adapters are still valuable for users who generate reports locally.
- Error tracking (Sentry) is API-based — requires auth tokens, can't calibrate from open-source repos

---

### Legal Documentation (#36)

**Status:** Implemented based on lawyer-reviewed language (2026-02-20 memo).

See `memory/transition-2026-02-20-legal.md` for exact lawyer language and implementation details.

| # | Sub-Task | Effort | Status |
|---|----------|--------|--------|
| 36.1 | **Create BSL 1.1 license file** — `LICENSE` in repo root (core analysis engine Phases 2-5) | Low | Complete ✅ |
| 36.2 | **Update Privacy Policy** — remove DRAFT, set dates, fix §2.4 email→hash language, 30-day retention, SCC language, add address | Medium | Complete ✅ |
| 36.3 | **Update Terms of Service** — remove DRAFT, dual licensing §4, CC0-1.0 patterns §6.3, Delaware law, AAA arbitration + EU carve-out | Medium | Complete ✅ |
| 36.4 | **EU AI Act Article 50 disclosures** — CLI notice on `evo investigate`/`evo fix`, report footer, help text | Low | Complete ✅ |
| 36.5 | **Update website/privacy.html** — email→hash correction, add Terms link to footer | Low | Complete ✅ |
| 36.6 | **Update plan & memory** — mark #36 complete, unblock #38b | Low | Complete ✅ |

**Key decisions (all confirmed):**
- **BSL 1.1** with 3-year Change Date (2029-02-20), converts to MIT
- **Entity:** CodeQual LLC, 30 N Gould St Ste R, Sheridan, WY 82801
- **Governing law:** Delaware | **Arbitration:** AAA, remote/virtual, with EU carve-out
- **Community patterns:** CC0-1.0 (public domain dedication)
- **Axiom retention:** 30 days for all datasets
- **Privacy §2.4 fix:** "email" → "truncated SHA-256 hash, irreversible"

---

### External / Infrastructure

| # | Task | Effort | Blocker? | Status |
|---|------|--------|----------|--------|
| 36 | **Lawyer review implementation** — 6 sub-tasks above | Medium | No | **Complete** ✅ |
| 36.7 | **Webhook signing key** — confirm `EVO_LICENSE_SIGNING_KEY` env var in Vercel production (hard-fail if missing) | Low | Yes — webhook returns 500 without it | **Complete** ✅ |
| 36.8 | **Axiom 30-day retention** — configure in Axiom dashboard for all datasets | Low | No | **Complete** ✅ |
| 36.9 | **Verify Axiom/Vercel DPAs** — confirm SCCs in their Data Processing Agreements | Low | No | **Complete** ✅ (both auto-effective, EU 2021/914 SCCs) |
| 36.10 | **Verify Vercel Pro plan** — confirm project is on Pro tier | Low | No | **Complete** ✅ ($20/mo Premium) |
| 36.11 | **Terms page + routing** — `website/terms.html` created, `/terms` route added | Low | No | **Complete** ✅ |
| 36.12 | **BSL licensing in README** — dual-license table added | Low | No | **Complete** ✅ |
| 36.13 | **GDPR deletion runbook** — internal ops procedure | Low | No | **Complete** ✅ |
| 36.14 | **Lawyer confirmation packet** — `codequal.dev/lawyer-review-packet-2026-02-22` | Low | No | **Complete** ✅ |
| 38b | **Stripe live-mode testing** — repeat all flows with real Stripe dashboard | Low | Yes — required before launch payments | **Complete** ✅ |
| 49 | **Axiom dashboard & monitors** — 10 typed telemetry helpers, enriched CLI + Vercel events, 5 dashboards, 3 alerts, 1749 tests | Medium | No — operational readiness | **Complete** ✅ |

**#38b — Stripe Live-Mode Testing (after #36):**
1. Pro purchase — complete checkout with real card, verify license key, `evo license status` shows Pro
2. Cancellation — cancel subscription, verify license revoked, CLI falls back to free tier
3. FOUNDING50 discount — apply coupon, verify 50% off for 3 months, Pro license still valid
4. Payment failure — simulate failed renewal, verify `past_due` flag, appropriate notification

**#49 — Axiom Observability (Complete):**
- 10 typed telemetry helpers in `evolution/telemetry.py` (analyze, investigate, fix, verify, accept, sources, license_check, adapter_execution, pattern_sync, error)
- Enriched CLI events with duration, license_tier, gated_families, diagnostics; global error hook via sys.excepthook
- Per-adapter timing + adapter_diagnostic events for 0-data monitoring
- Vercel handler enrichment: geo (country), revenue data, user_agent, pattern quorum/families
- 5 Axiom dashboards (Usage Analytics, Financial/Revenue, Business Overview, Service Health, Adapter & Pattern Ecosystem)
- 3 alerts (webhook failures, CLI error spike, payment failures)
- 13 new tests (1716 total), APL query reference at `docs/axiom-dashboards.md`
- Usage metrics (analyses/day, patterns shared, licenses issued)

---

### Pre-Launch Testing

| # | Task | Effort | Blocker? | Status |
|---|------|--------|----------|--------|
| CAL3 | **Calibration v3** — 48/51 repos, 44 patterns, 7 families | Medium | Yes | **Complete** ✅ |
| FULL | **Full automated test suite** — 1703 tests passing | Low | Yes | **Complete** ✅ |
| CLI-COV | **CLI command test coverage — core commands** (analyze, report, status, investigate, fix) | Medium | Yes | **Complete** ✅ |
| CLI-COV2 | **CLI command test coverage — integration + secondary commands** | Medium | No | **Complete** ✅ |

### CLI Command Test Coverage Audit (Feb 23, 2026)

**60 commands in README. 83 CLI runner tests across 3 files + existing module tests.**

120 `runner.invoke()` calls across test suite. Key test files: `test_adapter_cli.py` (39), `test_core_cli.py` (34), `test_integration_cli.py` (27), `test_secondary_cli.py` (22), `test_setup_cli.py` (16), `test_pattern_cli.py` (16), `test_accepted.py` (7), `test_sources_cli.py` (5).

#### Priority 1 — Core Commands (Complete ✅)

34 tests in `tests/unit/test_core_cli.py` covering all 5 core commands:

| Command | Tests | Coverage |
|---------|-------|----------|
| `evo analyze` | 8 | happy path, no_events exit, --json, --quiet, --no-report, --show-prompt, --families, --token |
| `evo report` | 6 | happy path, no advisory exit, --output, --title, --serve, --verify |
| `evo status` | 5 | happy path, missing tokens shown/hidden, last advisory, --token |
| `evo investigate` | 7 | happy path, Pro gate, --show-prompt, no advisory exit, failed report, --agent, AI disclosure |
| `evo fix` | 8 | --dry-run, Pro gate, all_clear/partial/max_iterations statuses, --yes, --dry-run --residual, branch+iteration reporting |

#### Priority 2 — Integration Commands (Complete ✅)

27 tests in `tests/unit/test_integration_cli.py`:

| Command Group | Tests | Coverage |
|---------------|-------|----------|
| `evo init` | 5 | --path cli, hooks Pro gate, action Pro gate, setup failure, --families |
| `evo hooks install/uninstall/status` | 7 | happy path, Pro gate, install failure, uninstall success/not-found, status installed/not-installed |
| `evo config list/get/set/reset` | 5 | grouped list, get found/unknown, set, reset |
| `evo history list/show/diff/clean` | 8 | list happy/empty/json, show happy/not-found, diff happy/too-few-runs, clean no-args |
| `evo verify` | 2 | happy path (all resolved), --quiet with persisting issues |

#### Priority 3 — Secondary Commands (Complete ✅)

22 tests in `tests/unit/test_secondary_cli.py`:

| Command Group | Tests | Coverage |
|---------------|-------|----------|
| `evo watch` | 4 | Pro gate, --status running/not-running, --stop |
| `evo license status/activate` | 4 | free tier, pro tier, activate valid/invalid |
| `evo notifications list/dismiss` | 3 | list empty/has-items, dismiss all |
| `evo patterns list/pull/push/new` | 5 | no-kb, pull success/failure, push success/disabled, scaffold |
| `evo patterns add/remove/block/unblock/packages` | 5 | add, remove, block, unblock, packages-none |
| `evo adapter guide` | — | Only remaining uncovered adapter CLI command |

#### Well-Covered (No Action Needed)

- **Adapter CLI** — 12/14 subcommands covered (85.7%) in `test_adapter_cli.py`
- **Acceptance CLI** — 4/4 covered (100%) in `test_accepted.py`
- **Sources CLI** — covered in `test_sources_cli.py`
- **Setup CLI** — covered in `test_setup_cli.py`
- **Pattern CLI** — 7/13 subcommands covered in `test_pattern_cli.py`

### Legal & Compliance (Remaining)

From data-flow audit and lawyer review — items not yet resolved:

| # | Task | Effort | Blocker? | Status |
|---|------|--------|----------|--------|
| L1 | **DSAR process** — document procedure for GDPR Article 15-17 access/deletion requests | Low | Yes — legally required | **Complete** ✅ (runbook at `docs/legal/gdpr-deletion-runbook.md`) |
| L2 | **Privacy policy link on adapter request form** — server-side form must link to privacy policy before data submission | Low | Yes — GDPR consent | **Complete** ✅ |
| L3 | **Cookie/analytics disclosure** — codequal.dev may use Vercel analytics; disclose in privacy policy or add consent banner | Low | No | **Complete** ✅ (consent banner on all pages, no third-party analytics) |
| L4 | **Webhook error sanitization** — `webhook.py` logs `str(exc)` to Axiom; Stripe exceptions could contain PII | Low | No | **Complete** ✅ (logs `type(exc).__name__` only) |
| L5 | **Stripe customer_id in Axiom** — indirect PII; assess if logging is necessary or can be further anonymized | Low | No | **Complete** ✅ (hashed to `customer_id_hash`, 12-char SHA-256 prefix) |
| L6 | **Anthropic API terms review** — confirm data processing terms for investigation/fix prompts | Low | No | Pending |

**Already addressed:**
- [x] License key email → SHA-256 hash (Feb 20)
- [x] Axiom 30-day retention documented in privacy policy (Feb 20)
- [x] EU AI Act Article 50 disclosures (Feb 20)
- [x] GDPR deletion runbook (Feb 22)
- [x] `pro-trial` backdoor removed (Feb 22)
- [x] DSAR procedure — L1 (Feb 22, runbook covers Art 15-17 + CCPA)
- [x] Privacy policy link on adapter request form — L2 (Feb 23)
- [x] Cookie/analytics disclosure — L3 (consent banner on all pages, no third-party analytics)
- [x] Webhook error sanitization — L4 (Feb 23, `type(exc).__name__` only)
- [x] Stripe customer_id anonymized — L5 (Feb 23, hashed to 12-char SHA-256 prefix)

---

### Consolidated Priority List (Feb 27, updated)

All pre-launch work complete. **1770 tests passing**, v0.3.0 on PyPI. Launch day: **Tuesday Mar 10, 2026**.

#### Blockers (Must Complete Before Beta Launch)

**All 4 blockers complete.** No remaining blockers for beta launch.

| Priority | Task | Effort | Section | Status |
|----------|------|--------|---------|--------|
| **B1** | **GitHub Action workflow** — trigger on real PR, verify PR comment, inline suggestions, accept flow, verify flow (GH-WF) | Low | Manual Testing | **Complete** ✅ |
| **B2** | **Acceptance persistence** — deploy webhook, set `EVO_ACCEPT_SECRET`, test `/evo accept` + `/evo accept permanent` on real PR (#45b) | Low | Manual Testing | **Complete** ✅ |
| **B3** | **GitLab CI workflow** — trigger on real MR, verify MR comment, accept flow, verify flow (GL-WF) | Low | Manual Testing | **Complete** ✅ |
| **B4** | **GitLab CLI manual testing** — 7 scenarios on real GitLab repo (#37) | Low | Manual Testing | **Complete** ✅ |

#### Should Have (Before Scaling Past Beta)

All complete.

| Priority | Task | Effort | Section | Status |
|----------|------|--------|---------|--------|
| **S1** | **Axiom dashboard & monitors** — 10 typed helpers, enriched events, 5 dashboards (20 panels), 3 alerts (#49) | Medium | External | **Complete** ✅ |
| **S2** | **Axiom 30-day retention** — configure in dashboard (#36.8) | Low | External | **Complete** ✅ |
| **S3** | **Verify Axiom/Vercel DPAs** — confirm SCCs (#36.9) | Low | External | **Complete** ✅ (both have EU 2021/914 SCCs) |
| **S4** | **Verify Vercel Pro plan** (#36.10) | Low | External | **Complete** ✅ (Pro not needed for beta — Hobby plan sufficient, cancelling after billing cycle) |
| **S5** | **Google Search Console** — verify codequal.dev, submit sitemap | Low | External | **Complete** ✅ (verified + sitemap submitted) |
| **S6** | **Deploy SEO changes** — robots.txt/sitemap.xml/meta tags live on all pages | Low | External | **Complete** ✅ |

#### Launch Phase (Current — Launch Day: Tuesday Mar 10)

| Priority | Task | Effort | Status |
|----------|------|--------|--------|
| **L1** | **Record terminal demo** — 6-scene VHS recording (install→sources→analyze→prompt→verify→closing) | Low | **Complete** ✅ |
| **L2** | **Create accounts** (alias) — Dev.to, Product Hunt, Bluesky, Mastodon, IndieHackers, Discord, Reddit, LinkedIn, Cursor Forum | Low | **Complete** ✅ |
| **L3** | **Update README + website** — demo GIF/video, sample reports, fix `evo investigate` → `--show-prompt` flow | Low | **Complete** ✅ |
| **L4** | **Review & personalize channel drafts** — `docs/marketing/day-01-tue-mar-10/` (9 drafts) | Low | **Complete** ✅ |
| **L5** | **Pre-launch listings** — AlternativeTo, StackShare, FutureTools, console.dev, 5 GitHub Awesome List PRs | Low | **Complete** ✅ |
| **L6** | **GitHub repo polish** — 13 topics, Discussions enabled, test badge updated to 1770 | Low | **Complete** ✅ |
| **L7** | **Axiom dashboards** — 6 dashboards verified, Alerts & Failures dashboard created, queries fixed (flat fields, no `in`) | Low | **Complete** ✅ |
| **L8** | **Vercel verification** — site, docs, i18n, API, pattern registry, checkout flow all verified working | Low | **Complete** ✅ |
| **L9** | **Day 1 (Mar 10): Simultaneous launch** — PH + HN + Dev.to + LinkedIn + Cursor + r/vibecoding + r/devops + Discord + Bluesky + Mastodon | Medium | Ready — drafts in `docs/marketing/day-01-tue-mar-10/` |
| **L10** | **Days 2-10: Staggered rollout** — r/programming, r/git, r/ChatGPT, r/opensource, r/selfhosted, AI communities | Medium | Pending — see `docs/marketing/LAUNCH_TRACKER.md` |
| **L11** | **Week 3+: International** — German (r/de_EDV, LinkedIn DE, Mastodon), Spanish (Platzi, Dev.to ES) | Medium | Pending |

**L2 — Accounts Created (Mar 6-8):**
- Dev.to: `codequal` via GitHub OAuth
- Product Hunt: CodeQual, listing scheduled for Mar 10
- Bluesky: @codequal.bsky.social, banner + bio
- Mastodon: @codequal@mastodon.social, banner + bio + extra fields
- IndieHackers: codequal account
- Discord: CodeQual server with 5 channels
- Reddit: account created, 3 subreddit drafts
- LinkedIn: CodeQual company page
- Cursor Forum: registered

**L5 — Pre-launch Listings (Mar 6-8):**
- AlternativeTo: listed, pricing corrected to Subscription
- StackShare: #208 in Monitoring, 2 followers
- FutureTools: submitted
- console.dev: email pitch sent
- GitHub Awesome Lists: 5 PRs open (jamesmurdza, mahseema, ai-for-developers, ColinEberhardt, ikaijua)
- GitHub Marketplace: action.yml at repo root, v0.3.0 release

**L6 — GitHub Repo Polish (Mar 8):**
- Topics: ai, ci-cd, cli, code-quality, developer-tools, devops, drift-detection, open-source, python, github-actions, gitlab-ci, monitoring, static-analysis
- Discussions enabled for launch day Q&A
- Test badge updated: 1749 → 1770

**L7 — Axiom Dashboards (Mar 8):**
- Fixed chart-level time overrides (7d hardcoded → inherit from dashboard)
- Fixed query field names: `properties.*` → flat top-level fields (Axiom flattens on ingest)
- Fixed `in (...)` syntax → `or` chains (Axiom doesn't support `in`)
- Created "Alerts & Failures" dashboard (9 charts: payment, webhook, CLI errors, checkout drop-off, adapter failures, pattern rejections, error timeline, error log)
- Deleted sample "HTTP logs" dashboard (Axiom default, not our data)
- Query reference docs updated: `docs/axiom-dashboards.md`, `docs/axiom-alerts-dashboard.md`

**L4 review notes (Mar 1):** Fixed 3 issues across all 15+ channel drafts:
1. Repo count: "48 repos" → "100+ repos across 3 calibration rounds" (was undercounting v1+v2+v3)
2. Investigation flow: removed `evo investigate .` as main path; replaced with actual UX (HTML report → copy prompt → paste into user's AI tool)
3. Added detect→fix→verify loop messaging to every channel — EE is not just a detector, it proposes a complete fix process
4. Fixed stale stats: 1716→1749 tests, confirmed v0.3.0

**L1 — Demo Recording (Complete, Mar 2):**
- 6-scene VHS tape: install → sources → analyze → show-prompt → verify → closing
- Assets: `docs/images/demo.gif` (README), `website/assets/demo.mp4` (website)
- VHS tape: `scripts/demo.tape` (reproducible recording)

**L3 — README + Website (Complete, Mar 2):**
- README: demo GIF at top, sample report screenshots, updated detect→fix→verify loop
- Website: demo video replaces static terminal mockup, "Sample Reports" section with live HTML report links
- CLI: `evo investigate .` removed from all user-facing output → replaced with `evo analyze . --show-prompt` + "Paste into Claude Code, Cursor, or Copilot"
- Fixed `evo investigate` references in README, website step 3, CLI footer, i18n

**Launch content ready at:**
- `docs/marketing/LAUNCH_TRACKER.md` — channels, timing, UTM links, status tracking
- `docs/marketing/CHANNEL_DRAFTS.md` — ready-to-post drafts for 15+ channels (reviewed ✅)
- `docs/marketing/VIDEO_SCRIPT.md` — 7-scene terminal demo script
- `website/sample-report.html` + `sample-report-verify.html` — live sample reports on codequal.dev

**UTM tracking implemented:** `script.js` reads `utm_source` from URL, persists in localStorage, sends to checkout handler → Axiom + Stripe metadata.

#### Nice to Have

| Priority | Task | Effort | Status |
|----------|------|--------|--------|
| **N1** | ~~Anthropic API terms review~~ | — | **Dropped** (users bring own API key) |
| **N2** | **Blog setup** — scaffold `/blog/` on codequal.dev | Low | Pending (hold until first post ready) |

#### Post-Beta Month 2+

| Priority | Task | Section |
|----------|------|---------|
| **P1** | License activation tracking (silent phone-home) | License Hardening §Phase 1 |
| **P2** | License activation limit (3 machines) | License Hardening §Phase 2 |
| **P3** | License periodic validation (weekly) | License Hardening §Phase 3 |
| **P4** | Datadog adapter | Future |
| **P5** | IDE extensions (VS Code, JetBrains) | Future |

#### Completed (Since Last Update)

| Task | Date |
|------|------|
| CLI test coverage — core commands (B1, 34 tests) | Feb 22 |
| CLI test coverage — integration commands (S1, 27 tests) | Feb 23 |
| CLI test coverage — secondary commands (S2, 22 tests) | Feb 23 |
| Webhook signing key (#36.7) | Feb 22 |
| Stripe live-mode testing (#38b) | Feb 22 |
| DSAR process (L1) | Feb 22 |
| Privacy policy link on forms (L2) | Feb 23 |
| Cookie/analytics disclosure (L3) | Feb 23 |
| Webhook error sanitization (L4) | Feb 23 |
| Stripe customer_id anonymization (L5) | Feb 23 |
| HTML Report UX — "What EE Can See" sources section, 1-2-3 Next Steps, accepted deviations banner | Feb 25 |
| Manual Testing B5 — HTML report manual testing (8 bugs found/fixed) | Feb 25 |
| Adapter diagnostics — source status cards, 6 statuses, pattern filtering, 36 new tests (PR #7) | Feb 26 |
| Integrations guide — troubleshooting section, family-specific no-data hints | Feb 26 |
| Website nav — Integrations link added to all pages | Feb 26 |
| Diagnostic card messages — no_license → "Available with Pro", active → family-specific hints | Feb 26 |
| Website i18n — DE/ES translations for Data Sources (113 elements) and Docs (199 elements) pages | Feb 26 |
| Website nav — unified nav across all 6 pages, lang switcher removed from legal pages | Feb 26 |
| i18n.js fix — textContent for pre>code blocks to preserve diagram whitespace | Feb 26 |
| Website SEO — robots.txt, sitemap.xml, Schema.org JSON-LD, unique titles/descriptions, canonical URLs, hreflang | Feb 27 |
| Axiom observability (#49) — 10 typed telemetry helpers, enriched CLI + Vercel events, 5 dashboards, 3 alerts, 13 new tests | Feb 26 |
| Manual Testing B1-B4 — all blockers verified (GitHub Action, webhook, GitLab CI, GitLab CLI) | Feb 24-25 |
| PyPI v0.2.2 published — all 6 flows tested (3 GitHub + 3 GitLab) | Feb 25 |
| Axiom 30-day retention configured (S2) | Feb 27 |
| Axiom/Vercel DPAs verified — both have EU 2021/914 SCCs (S3) | Feb 27 |
| Vercel Pro plan activated — $20/mo Premium (S4) | Feb 27 |
| Google Search Console — codequal.dev verified, sitemap submitted (S5) | Feb 27 |
| SEO fully deployed — robots.txt, sitemap.xml, meta tags, canonical URLs, hreflang live (S6) | Feb 27 |
| Version bump to 0.3.0 — published to PyPI, CI built all wheels | Feb 27 |
| UTM source tracking — localStorage persistence, Axiom + Stripe attribution | Feb 27 |
| Launch content — LAUNCH_TRACKER.md, CHANNEL_DRAFTS.md (15+ channels), VIDEO_SCRIPT.md | Feb 27 |
| N1 (Anthropic API terms) dropped — users bring own API key | Feb 27 |
| Deep-dive audit + E2E testing — heartbeat, API auth, input sanitization, 1749 tests | Mar 1 |
| E2E test plan — 15/16 passed, live Stripe checkout verified, `docs/E2E_TEST_PLAN.md` | Mar 1 |
| Channel drafts review (L4) — 100+ repos, detect→fix→verify loop, investigation flow fix | Mar 1 |

---

### HTML Report UX Improvements (Feb 25, 2026)

**Status: Complete**

Major UX overhaul of the HTML report (`evolution/report_generator.py`) based on manual testing. Automated tests (100 report tests passing) did not catch several issues that were immediately visible during hands-on usage.

#### What Was Done

1. **"What EE Can See" section** (after Executive Summary)
   - Shows all connected families with status badges: Active (green), Connected/No Deviations (blue), Config Detected (amber), Not Connected (gray), Pro (purple)
   - License-aware: Free users see Pro badge + pricing link for Tier 2 families; Pro users see "Connected" with CI setup guidance
   - Loads `.env` via `load_dotenv()` so tokens are detected during report generation
   - All hints include "Setup guide" link to `docs/guides/INTEGRATIONS.md`
   - Signal counts shown for connected families

2. **1-2-3 Next Steps flow** (replaced "Investigate with AI" section)
   - Step 1: Investigate (copy prompt, paste in AI)
   - Step 2: Fix (apply changes or Accept if intentional)
   - Step 3: Verify (run `evo analyze . --verify`, check verification banner)
   - 3-column responsive grid layout

3. **Accepted deviations visibility**
   - Green banner in "What Changed" section showing accepted deviations not displayed
   - Uses `summary.accepted_metrics` from Phase 5 advisory
   - Shows family/metric labels and management hint (`evo accept --list`)

4. **Adapter section cleanup**
   - Removed "Currently Active" from "Expand Your Coverage" (avoids duplication with Sources)
   - Added Pro badges to Tier 2 adapter cards
   - Filtered sources families out of adapters section

#### Bugs Found During Manual Testing (Not Caught by Automated Tests)

1. `source_file` could be `None` causing `.lower()` crash in `_get_ci_hint`
2. `.env` not loaded during report generation so tokens were not detected
3. Tier 2 families showed "set your token" even when token was present — needed tier-aware logic
4. Pro features incorrectly described as "runs in CI" — needed license check
5. Adapter cards in "Expand Your Coverage" didn't show Pro badge for Tier 2 adapters
6. Doc links missing from all hints (plan specified them, implementation forgot)
7. Accepted deviations silently filtered — user saw no trace of them
8. "Next Steps" section described what AI would do but didn't tell user HOW to verify

#### What's Next

- **Manual Testing B5: GitLab CI webhook verify flow** — test full GitLab CI pipeline with report changes
- Verify MR comments still work correctly with new report format
- Test report in GitLab CI context (Pro tier, with pipeline data)

---

### Launch

| # | Task | Effort | Blocker? |
|---|------|--------|----------|
| 42 | **Public launch** — simultaneous blast across 10 channels, staggered rollout days 2-10 | Medium | Ready — Mar 10 |

See `docs/LAUNCH_PLAN.md` for launch timeline and go-to-market strategy.
See `docs/marketing/LAUNCH_TRACKER.md` for daily calendar, UTM links, and post metrics.

---

## Post-Beta Month 2: License Hardening

License system currently validates offline via HMAC-signed keys. No protection against key sharing across machines. Acceptable for early users (trust-based) but must be hardened before scaling past ~200 users.

**Completed (Feb 22, 2026):**
- [x] Remove `pro-trial` backdoor from production code (test-only via `_is_test_environment()`)

### Phase 1: Activation Tracking (Month 2, Low Effort)

Silent phone-home on first `evo analyze` with a Pro key. Does NOT block — just logs.

| Data Sent | Purpose |
|-----------|---------|
| `email_hash` (already in key) | Identify the subscriber |
| `machine_id` (hash of hostname + username) | Count unique installations |
| `evo_version` | Track version adoption |
| `timestamp` | Activation timing |

**Implementation:**
- POST to `codequal.dev/api/activate` on first Pro `evo analyze` per machine
- Store activation in Upstash Redis: `activation:{email_hash}` → set of `machine_id`s
- Axiom dashboard shows activations per key (alert if >5 machines)
- No user interaction — no prompts, no data collection beyond what's in the key
- Graceful failure — if API is unreachable, analysis continues normally
- Cache activation locally in `~/.evo/activation.json` so it only phones home once per machine

**Files to create/modify:**
- `evolution/activation.py` — activation logic (POST, cache, graceful failure)
- `evolution/orchestrator.py` — call `check_activation()` on Pro analyze
- `website/api/activate.py` — Vercel handler, Redis storage
- Tests

### Phase 2: Activation Limit (Month 2-3, Medium Effort)

After tracking shows the actual usage pattern, add a soft limit.

- Allow 3 machines per license key (personal laptop, work machine, CI)
- 4th machine shows warning: "This key is active on 3 machines. Contact support@codequal.dev to add more."
- 7-day grace period on new machines (don't block immediately)
- `evo license devices` command to list active machines
- Deactivation: `evo license deactivate` removes current machine from the list

### Phase 3: Periodic Validation (Month 3+, Medium Effort)

Once-per-week phone home to verify subscription is still active.

- On `evo analyze`, check if last validation is >7 days old
- POST to `codequal.dev/api/validate` with `email_hash`
- Server checks Stripe subscription status → returns `{valid: true/false, expires: "..."}`
- Cache result for 7 days (offline grace period)
- If subscription cancelled: degrade to free tier after cache expires
- Handles the "cancelled but key still works forever" gap

### What NOT to Do

- No aggressive DRM — devs will choose alternatives
- No blocking offline use — local-first is the selling point
- No obfuscation games — determined pirates always win, focus on honest users
- No phone/email collection — `email_hash` and auto-generated `machine_id` are sufficient

---

## Post-Release: Audit-Driven Backlog (Feb 28, 2026)

Two comprehensive audits (5 deep audits each: security, business logic, architecture, performance, dependencies) identified these items as post-release work — best addressed with real usage data.

### Trigger: First Paying Customer

| # | Task | Why Wait | Effort |
|---|------|----------|--------|
| A1 | **License periodic re-validation** — weekly server check on `evo analyze`; cancelled users currently keep Pro locally forever (C1) | No paying customers to protect yet; revocation is theoretical | Medium |
| A2 | **Machine fingerprint binding** — limit key to N machines | Need activation data first to set the right limit | Medium |
| A3 | **Activation token with server nonce** — current SHA-256 token is forgeable without a secret (H1); add server-derived component at activation time | Requires A1 infrastructure | Medium |
| A4 | **Accept GET endpoint authentication** — currently returns accepted deviations for any repo without auth (C3) | Low-value data pre-launch; add signature param matching POST pattern | Low |
| A5 | **Duplicate checkout prevention** — check for existing active subscription before creating Stripe session (M3) | No customers yet to double-charge | Low |

### Trigger: First Failed Payment

| # | Task | Why Wait | Effort |
|---|------|----------|--------|
| A6 | **Revoke license after N failed payments** — currently `payment_failed` only sets metadata flag, CLI ignores it (M1) | Need real dunning data to set correct threshold | Low |

### Trigger: Pattern Count > 200

| # | Task | Why Wait | Effort |
|---|------|----------|--------|
| A7 | **SQLite index on KB fingerprint column** | 44 patterns today; O(n) lookup is <1ms | Low |
| A8 | **Redis failover for pattern registry** — PyPI as fallback when Upstash is down | 28 patterns; loss recoverable from PyPI cache | Medium |
| A9 | **Pattern pagination on GET /api/patterns** | Response is ~5KB today; only matters at 1000+ patterns | Low |

### Trigger: Repo with 5K+ Commits Analyzed

| # | Task | Why Wait | Effort |
|---|------|----------|--------|
| A10 | **Event streaming in Phase 2** — sliding window, reduce 1-2GB peak to ~200MB (H9) | Current repos are <2K commits | High |
| A11 | **Batch git subprocess calls** — single `git log --numstat` instead of per-commit diff (H10); walker spawns up to 17K subprocesses for 1K commits | Perf is 10-16s for typical repos | High |
| A12 | **Phase 1 JSONL batching** — one file per family instead of per-event JSON files (H11); Phase 2 reads all events 10x (M6) | 2500 files tolerable on modern FS | Medium |
| A13 | **`--max-commits` CLI flag** — default 500, user-configurable | Need real usage data on what "large" means | Low |
| A14 | **Phase 1 index: write once** — currently rewritten per ingest call, 1000s of JSON serializations (M7) | Adds 2-10s only at scale | Low |

### Trigger: Wheel Download Count > 1000/month

| # | Task | Why Wait | Effort |
|---|------|----------|--------|
| A15 | **Sign wheels with Sigstore** — post-publish binary attestation | Supply chain risk scales with adoption | Medium |
| A16 | **Publish SHA256 checksums** alongside releases | Same rationale as A15 | Low |
| A17 | **Pin all GitHub Actions to commit SHAs** — currently pinned to major version tags (H5) | Low likelihood but high impact if compromised | Medium |

### Trigger: First Security Report / Abuse Complaint

| # | Task | Why Wait | Effort |
|---|------|----------|--------|
| A18 | **Rate limits in Redis** — persistent across Vercel cold starts (M4); in-memory limits reset on every cold start | Vercel has platform DDoS protection | Medium |
| A19 | **Restrict CORS on patterns/telemetry/accept endpoints** — currently `Access-Control-Allow-Origin: *` (M10); CLI uses `requests` not browser fetch | Need to verify no browser consumers first | Low |

### Trigger: API Cache Staleness Reported

| # | Task | Why Wait | Effort |
|---|------|----------|--------|
| A20 | **API cache TTL** — GitHub/GitLab cached responses never expire (M5) | No reports of stale data yet | Low |
| A21 | **HTTP retry with backoff** — single failure = 24h stale pattern data (M8) | Transient failures are rare | Low |

### Trigger: Revenue > $500/month (License Hardening)

| # | Task | Why Wait | Effort |
|---|------|----------|--------|
| A22 | **Track activation count per key in Redis** — enforce limit (e.g., 3 machines per key) | Premature for early users; heartbeat already catches cancelled | Medium |
| A23 | **One-time-use session_id retrieval** — mark session consumed after first GET /api/get-license | Low risk (Stripe session IDs are random); matters at scale | Low |
| A24 | **Admin key recovery tool** — manual endpoint to regenerate key from Stripe customer_id | Edge case (webhook failure + Stripe retry failure); add if support tickets appear | Medium |
| A25 | **PyPI pattern package hash pinning** — pin SHA256 of trusted .whl files in pattern_index.json | Supply chain risk scales with pattern package count (currently 0 external) | Medium |

### Code Quality (No External Trigger — Do When Convenient)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| A26 | **Replace `except Exception: pass` with `logger.debug()`** — 60+ silent blocks (H12) | Medium | Debuggability |
| A27 | **Add Phase 1 and Phase 3 engine tests** — critical pipeline phases with zero dedicated coverage (H14) | Medium | Correctness |
| A28 | **Phase 2 `run_git()` → `_emit_signals()` refactor** — 80 lines of duplicated signal logic (M16) | Medium | Consistency |
| A29 | **Extract signal-loading utility** — duplicated across Phase 3, 4, 5 (M13) | Low | Maintenance |
| A30 | **Extract `_hash` / `_content_hash` utility** — duplicated across 4 modules | Low | Maintenance |
| A31 | **`evo_path` helper extraction** — 13 duplicate expressions in cli.py | Low | Maintenance |
| A32 | **`phase3_1_renderer.py` removal** — dead code, Phase 3.1 LLM retired | Low | Cleanup |
| A33 | **Remove `_prescan_hint()` dead code** — replaced by `_prescan_hint_collect()` | Low | Cleanup |
| A34 | **`_axiom_send()` template generation** — script to emit Vercel handlers from template | Low | Maintenance (8 copies) |
| A35 | **Replace `print()` with `logging`** — watcher, adapters, phase2_engine (M18) | Low | Debug experience |
| A36 | **Move `load_dotenv()` from module-level** — phase4_engine import-time env pollution (M17) | Low | Test stability |
| A37 | **Decouple `fixer.py` from `click`** — domain module imports CLI framework (M14) | Low | Library usability |
| A38 | **SQLite batch commits** — knowledge store commits per pattern operation (M9) | Low | Import speed |
| A39 | **Watcher daemon log rotation** | Low | Long-running daemon |
| A40 | **Config TOML special character escaping** — `#`, `=`, newlines corrupt file | Low | Edge case |
| A41 | **Connection pooling for GitHub/GitLab clients** — use `requests.Session` | Low | API latency |

---

## Future Enhancements (Post-Beta)

- **Datadog adapter** — monitoring family, high effort, deferred to post-deployment
- PostgreSQL + pgvector migration (multi-tenant, when SaaS tier exists)
- Vendor adapters requiring external services (PagerDuty, New Relic — needs partner access)
- Real-time event streaming (webhooks vs batch polling)
- IDE extensions (VS Code, JetBrains) — surfaces advisories where code is written
- Trend dashboard — multi-run advisory comparison over time
- API Service / SaaS tier
- Web Dashboard

---

## Architecture Reference

See `architecture.md` for detailed module documentation.

**Key constraints:**
- `_CatFileContentStream` is NOT thread-safe — keep git walker sequential
- `load_dotenv()` in phase4 engine pollutes env — tests must clear GITHUB_TOKEN
- GitHub free tier: 5,000 req/hr — max ~8 parallel agents safely
- Phase 3.1 LLM retired — templates produce PM-friendly text (`friendly.py`)
- `llm_openrouter.py`, `llm_anthropic.py`, `phase3_1_renderer.py` — dormant legacy code, only used if Phase 4b explicitly enabled
- `validation_gate.py` — still live, used by Phase 4b pattern validation
- Analysis is deterministic — Phase 1 uses payload timestamps, Phase 2 sorts chronologically
- `pro-trial` license key only works in test environments (pytest / `EVO_TEST_MODE=1`)

**Cost:**
- Phase 4b (sonnet): ~$0.003/pattern, total LLM cost ~$0.01/repo (off by default)
- AI investigation/fix uses `ANTHROPIC_API_KEY` (user-provided, Pro only)
