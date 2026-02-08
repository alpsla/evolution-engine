# Calibration Summary — Key Findings

**Date:** 2026-02-08  
**Runs Completed:** 2 (evolution-engine, fastapi)

---

## What We Validated ✅

1. **Pipeline Works End-to-End**
   - All 5 phases execute correctly
   - Scales from 11 commits (evolution-engine) to 6,713 commits (fastapi)
   - Phase 3.1 LLM enhancement handles 26K explanations in ~2 minutes
   - Phase 5 advisory output (summary.txt, chat.txt, investigation prompts) is excellent

2. **Statistical Baseline Quality**
   - Small repos (<50 commits): High variance, unstable baselines
   - Large repos (1000+ commits): Low variance, stable baselines
   - Git metrics (files_touched, dispersion, locality, novelty) work correctly

3. **Performance**
   - Phase 1: ~1 minute per 1000 commits
   - Phase 2: Fast (<1 minute for 26K signals)
   - Phase 3: ~0.5 seconds per LLM call (Haiku)
   - Total: ~10 minutes for 6713 commits

4. **Contract Adherence**
   - All phases follow their contracts (ADAPTER_CONTRACT, PHASE_X_CONTRACT)
   - Validation gates work (no recommendations, no judgment)
   - Evidence collection traces signals → commits → files correctly

---

## Critical Discovery: The Multi-Family Data Problem 🚨

### What We Learned

**Pattern discovery requires HISTORICAL multi-family data, not snapshots.**

Phase 4 co-occurrence detection looks for correlations like:
- "Dependency growth + test duration increase" (git + dependency + testing families)
- "High dispersion + CI failure spike" (git + ci families)
- "Schema churn + security vulnerability introduction" (schema + security families)

### Why Git-Only Doesn't Work

- Both runs (evolution-engine, fastapi) had **0 patterns discovered**
- Not a bug — Phase 4 is designed to find **cross-family** patterns
- Git-only data = intra-family patterns only (not useful)
- Example: "Files changed correlates with dispersion" is trivial and not actionable

### Why Synthetic/Snapshot Data Doesn't Work

Running `pytest` once on fastapi gives:
- ✅ Current test count
- ✅ Current pass/fail status
- ❌ No historical test duration trends
- ❌ No correlation with git commits over time

**We need:**
- Test results from 100+ commits (how did suite duration change?)
- Dependency snapshots from 100+ commits (how did dep count evolve?)
- CI runs correlated with git history (how did failure rate correlate with code changes?)

### The Real Data Source

**Historical multi-family data only exists in:**
1. **Production CI systems** (GitHub Actions, GitLab CI, Jenkins)
   - Each workflow run is timestamped and linked to a commit
   - Test results, duration, failure rate over time
   - Example: GitHub Actions API provides full run history

2. **Dependency management lockfiles in git history**
   - `requirements.txt`, `package-lock.json`, `go.sum` tracked over time
   - Can be extracted from git history: `git show <commit>:requirements.txt`
   - Reconstruct dependency evolution by walking commits

3. **Real client repositories (consulting model)**
   - Already have months/years of CI data
   - Already have dependency history in git
   - Already have security scan history (if using Trivy, Snyk, etc.)

---

## What Calibration Actually Validated

| Goal | Status | Finding |
|------|--------|---------|
| Pipeline works end-to-end | ✅ Validated | All phases execute correctly at scale |
| Baselines are stable | ✅ Validated | Large repos produce low-variance baselines |
| Phase 5 output is useful | ✅ Validated | Advisory format is clear and actionable |
| LLM integration works | ✅ Validated | Phase 3.1 and 4b scale well |
| Pattern discovery works | ⚠️ Blocked | **Requires historical multi-family data** |
| Seed KB can be built | ⚠️ Blocked | **Requires pattern discovery first** |

---

## Action Plan (Revised)

**Key insight:** Multi‑family data IS available from open‑source repos — we just need
two adapter extensions to access it.

### Priority Order

| # | Task | Effort | What It Unlocks |
|---|------|--------|-----------------|
| **1** | **Git History Walker Adapter** | 1 day | Dependencies, Schema, Config families from git history |
| **2** | **GitHub API Adapter** | 1–2 days | CI, Deployment, Security families via API |
| **3** | **Repo search & selection** | 0.5 day | Validated repos with 4+ family coverage |
| **4** | **Multi‑family calibration runs** | 2–3 days | First real cross‑family patterns |
| **5** | **Fix Verification Loop** | 1–2 days | Verify user fixes resolved issues |
| **6** | **Report Generator (HTML/PDF)** | 2–3 days | Consulting‑ready deliverable |
| **7** | **Marketing materials** | Separate | One‑pager, sample report, demo script |

### Where Historical Multi‑Family Data Exists

| Family | Data Source | How to Extract |
|--------|-----------|----------------|
| Git | Repo history | Already working ✅ |
| Dependencies | Lockfiles in git history | `git show <commit>:requirements.txt` |
| CI / Build | GitHub Actions API | `GET /repos/{owner}/{repo}/actions/runs` |
| Schema / API | OpenAPI specs in git history | `git show <commit>:openapi.json` |
| Deployment | GitHub Releases API | `GET /repos/{owner}/{repo}/releases` |
| Config | IaC files in git history | `git show <commit>:main.tf` |
| Security | GitHub Security API | `GET /repos/{owner}/{repo}/security-advisories` |
| Testing | CI artifacts (JUnit XML) | Download from CI run artifacts (if public) |

### Consulting Strategy (Updated)

Consulting runs **in parallel** with open‑source calibration:

```
Advisory Report → Investigation Prompt → User's AI → Fix Applied → Verify Fix → Repeat
    │                                                                  │
    └── Phase 5 output                                    Fix Verification Loop (new)
```

**Updated engagement flow:**
1. **Baseline Report** — HTML/PDF showing "normal vs now"
2. **Investigation Prompt** — pre‑built for user's AI assistant
3. **Fix Verification** — re‑run pipeline, show what resolved
4. **Ongoing Advisory** — periodic reports with fix tracking (monthly retainer)

---

## Files Generated During Calibration

1. ✅ `.calibration/` directory structure
2. ✅ `docs/CALIBRATION_GUIDE.md` — comprehensive operator manual
3. ✅ `.calibration/run_calibration.py` — pipeline runner script
4. ✅ `.calibration/reports/evolution-engine_calibration.md` — detailed analysis
5. ✅ `.calibration/reports/fastapi_calibration.md` — detailed analysis
6. ✅ `.calibration/calibration_log.md` — running log
7. ✅ `.calibration/README.md` — quick reference
8. ✅ Full pipeline outputs for 2 repos (Phases 1-5, all artifacts)

---

## Bottom Line

**The system works.** Calibration validated pipeline mechanics at scale (6,713 commits).

**Pattern discovery is within reach.** Two adapter extensions (Git History Walker + GitHub API)
unlock 5+ additional source families from open‑source repos.

**The engagement flow is clear:** Advisory → Investigation → Fix → Verify → Repeat.
This turns the product from a "flag raiser" into an "outcomes tracker."

**See `docs/IMPLEMENTATION_PLAN.md` §7 for detailed priorities and implementation scope.**
