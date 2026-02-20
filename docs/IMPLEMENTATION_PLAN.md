# Evolution Engine — Implementation Plan

> **Last updated:** February 19, 2026 | 1435 tests passing (6.52s) | v0.2.0 on PyPI
>
> This document tracks remaining work before public beta.
> For completed implementation history, see `IMPLEMENTATION_PLAN_v1.md`.

---

## What's Built (Complete)

All core engine work is done. Summary of shipped features:

| Area | Status | Key Files |
|------|--------|-----------|
| 5-phase pipeline (events → signals → explanations → patterns → advisory) | ✅ | `evolution/phase*.py` |
| CLI with 30+ commands (`evo analyze`, `verify`, `accept`, `investigate`, `fix`, etc.) | ✅ | `evolution/cli.py` |
| 3-tier adapter ecosystem (built-in, API, plugins) with scaffold/validate/security | ✅ | `evolution/adapter_*.py` |
| Source prescan (`evo sources`, `--what-if`) | ✅ | `evolution/prescan.py` |
| AI agents (`evo investigate`, `evo fix`) — RALF-style fix-verify loop | ✅ | `evolution/investigator.py`, `fixer.py` |
| GitHub Action — PR comments, verify, inline suggestions | ✅ | `action/action.yml` |
| Interactive HTML report with Accept buttons, evidence in prompts | ✅ | `evolution/report_generator.py`, `report_server.py` |
| Accept deviations — scoped (permanent, commits, dates, this-run) | ✅ | `evolution/accepted.py` |
| Run history — snapshot, compare, clean | ✅ | `evolution/history.py` |
| Pattern distribution — PyPI auto-fetch, KB sync, registry | ✅ | `evolution/pattern_registry.py`, `kb_sync.py` |
| 27 universal patterns from 43 repos | ✅ | `evolution/data/universal_patterns.json` |
| License system — free/pro tiers, HMAC-signed keys, Stripe checkout | ✅ | `evolution/license.py` |
| Cython compilation + CI wheels (Linux/macOS/Windows) | ✅ | `build_cython.py`, `.github/workflows/build-wheels.yml` |
| Website — codequal.dev on Vercel (landing, docs, privacy, Stripe, pattern registry) | ✅ | `website/` |
| SDLC integration — init wizard, git hooks, watcher daemon, setup UI | ✅ | `evolution/init.py`, `hooks.py`, `watcher.py`, `setup_ui.py` |
| PR acceptance flow — 3 options, scope, webhook persistence | ✅ | `evolution/pr_comment.py`, `website/api/accept.py` |
| GitLab compatibility | ✅ | Tested on gitlab-org/gitlab-styles |
| FP validation — 1.6% rate | ✅ | `evolution/fp_validation.py` |
| UX overhaul — 15 fixes (§13 of v1 plan) | ✅ | Multiple files |
| Historical trend detection — three-category classification | ✅ | `evolution/phase5_engine.py` |
| Pre-launch hardening — security fixes, signing key deployment | ✅ | Multiple files |

---

## Remaining Work

### Testing (In Progress)

| # | Task | Effort | Blocker? | Status |
|---|------|--------|----------|--------|
| 45b | **Acceptance persistence manual testing** — deploy webhook, test `/evo accept` + `/evo accept permanent` on real PR | Low | No | **Next** |
| 37 | **GitLab manual testing** — 7 scenarios on real GitLab repo (see v1 plan §12.2) | Low | Yes — verify before launch | Pending |

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

---

### UX & Polish

| # | Task | Effort | Blocker? |
|---|------|--------|----------|
| 46 | **`evo sources` UX fixes** — redundant token hints, irrelevant tool suggestions, unpublished adapter hints | Medium | Yes — users hit this early |
| 47 | **Config cleanup** — remove outdated LLM/theme settings, simplify privacy to binary, update setup UI | Medium | Yes — config is first impression |
| 48 | **Adapter discovery UX** — friendlier guidance, explain value of connecting detected tools, suppress irrelevant suggestions | Medium | No — polish |

**Details:**

**#46 — `evo sources` fixes:**
- Suppress Tier 2 hints when Tier 1 already active for same family
- Only suggest tokens for tools actually detected in repo
- Suppress adapter install hints for unpublished packages (or "Coming soon")

**#47 — Config cleanup:**
- Remove `llm.enabled/provider/model` — detect `ANTHROPIC_API_KEY` env var directly
- Remove `report.theme` — single theme
- Simplify `sync.privacy_level` — binary opt-in (share / don't share)
- Update setup UI (`setup_ui.py`) to match
- Add footer to `evo config list`: "Run `evo setup --ui` to edit in browser"

**#48 — Adapter discovery UX:**
- Reword when adapters not on PyPI ("Community adapters coming — or build your own")
- Explain what connecting each tool would unlock (e.g., "Sentry → error tracking signals")
- Suppress hints for tools not present in project

---

### External / Infrastructure

| # | Task | Effort | Blocker? |
|---|------|--------|----------|
| 36 | **Lawyer review** — ToS + Privacy sign-off → corrected docs → translator | Medium | Yes — must complete before accepting payments |
| 38b | **Stripe live-mode testing** — repeat all flows with real Stripe dashboard | Low | Yes — blocked by #36 |
| 49 | **Axiom dashboard & monitors** — API health, alerts, usage metrics from existing ingest | Medium | No — operational readiness |

**#38b — Stripe Live-Mode Testing (after #36):**
1. Pro purchase — complete checkout with real card, verify license key, `evo license status` shows Pro
2. Cancellation — cancel subscription, verify license revoked, CLI falls back to free tier
3. FOUNDING50 discount — apply coupon, verify 50% off for 3 months, Pro license still valid
4. Payment failure — simulate failed renewal, verify `past_due` flag, appropriate notification

**#49 — Axiom Dashboard:**
- API health dashboard (pattern registry, license webhook, accept webhook, website endpoints)
- Alert rules for errors, latency spikes, failed webhooks
- Usage metrics (analyses/day, patterns shared, licenses issued)

---

### Launch

| # | Task | Effort | Blocker? |
|---|------|--------|----------|
| 42 | **Community beta** — announce, gather feedback | Low | No — begins once above items verified |

See `docs/LAUNCH_PLAN.md` for detailed beta program, launch timeline, and go-to-market strategy.

---

## Future Enhancements (Post-Beta)

- PostgreSQL + pgvector migration (multi-tenant, when SaaS tier exists)
- Additional vendor adapters (GitLab CI, Jenkins, npm, Cargo, etc.)
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
- Phase 3.1 LLM retired — templates produce PM-friendly text
- Analysis is deterministic — Phase 1 uses payload timestamps, Phase 2 sorts chronologically

**Cost:**
- Phase 4b (sonnet): ~$0.003/pattern, total LLM cost ~$0.01/repo
- AI investigation/fix uses `ANTHROPIC_API_KEY` (user-provided)
