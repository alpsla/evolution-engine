# Calibration Directory — Complete Index

**Purpose:** Seed the Evolution Engine's Knowledge Base with validated patterns from real-world repositories before production use.

**Last updated:** 2026-02-08

---

## Quick Navigation

| I want to... | Go to |
|-------------|-------|
| **Run a quick validation test** | `./quick_test_validation.sh` |
| **Validate a specific repo** | `./validate_repo.sh OWNER REPO` |
| **Validate all 8 candidates** | `./validate_all_candidates.sh` |
| **Understand the validation process** | [`P3_REPO_SEARCH.md`](P3_REPO_SEARCH.md) |
| **See validation criteria** | [`P3_REPO_SEARCH.md`](P3_REPO_SEARCH.md#3-validation-procedure-per-repository) |
| **Record validation results** | [`repo_validation.md`](repo_validation.md) |
| **Run full calibration pipeline** | [`run_calibration.py`](run_calibration.py) |
| **Understand calibration workflow** | [`CALIBRATION_GUIDE.md`](../docs/CALIBRATION_GUIDE.md) |
| **See calibration progress** | [`calibration_log.md`](calibration_log.md) |
| **Review completed runs** | [`reports/`](reports/) |
| **Understand the findings** | [`CALIBRATION_SUMMARY.md`](CALIBRATION_SUMMARY.md) |

---

## Documentation Files

### Core Guides

1. **[`P3_REPO_SEARCH.md`](P3_REPO_SEARCH.md)** (716 lines) — **START HERE**
   - Step-by-step repository validation procedure
   - GitHub API commands for all 8 source families
   - 8 pre-selected candidate repositories
   - Output template and acceptance criteria
   - Troubleshooting guide

2. **[`CALIBRATION_GUIDE.md`](../docs/CALIBRATION_GUIDE.md)** (570 lines) — Operator Manual
   - Complete calibration workflow (Phases 1-5)
   - Parameter tuning guidance
   - Pattern classification (valid/local/false-positive)
   - Seed KB curation process
   - Common issues and fixes

3. **[`CALIBRATION_SUMMARY.md`](CALIBRATION_SUMMARY.md)** (170 lines) — Key Findings
   - What was validated (2 completed runs)
   - Critical discovery: multi-family data requirement
   - Action plan and priorities
   - Consulting strategy

### Results & Progress

4. **[`repo_validation.md`](repo_validation.md)** (353 lines) — Validation Results Template
   - 8 candidate repos with coverage matrices
   - Git History Walker config outputs
   - Priority rankings
   - **Status:** Template ready, awaiting validation runs

5. **[`calibration_log.md`](calibration_log.md)** (176 lines) — Running Log
   - Run 1: evolution-engine (2026-02-06) ✅
   - Run 2: fastapi (2026-02-07) ✅
   - Phase 3: Repo search toolkit (2026-02-08) ✅
   - Next: Multi-family validations

6. **[`reports/`](reports/)** — Detailed Calibration Reports
   - `evolution-engine_calibration.md` — First run (11 commits, git-only)
   - `fastapi_calibration.md` — Second run (6,713 commits, git-only)
   - Future: Multi-family reports (5+ more repos)

### Quick Reference

7. **[`README.md`](README.md)** (90 lines) — Quick Reference
   - Directory structure
   - Completed runs summary
   - Common commands
   - Next steps

8. **[`REVIEW_CHECKLIST.md`](REVIEW_CHECKLIST.md)** — Quality Gate
   - Pre-commit checklist
   - Pattern validation criteria
   - Report quality standards

---

## Automation Scripts

### Validation Scripts

1. **[`validate_repo.sh`](validate_repo.sh)** (280 lines) ⭐ **Core Validation**
   - Validates single repository across all 8 families
   - GitHub API queries (commits, CI, releases, security)
   - Shallow clone for file inspection
   - Lockfile discovery and commit count
   - Schema, IaC, and test file detection
   - Visual output with ✅/⚠️/❌ indicators
   - **Usage:** `./validate_repo.sh OWNER REPO`

2. **[`quick_test_validation.sh`](quick_test_validation.sh)** (65 lines) 🚀 **Quick Test**
   - Tests validation toolkit on fastapi/fastapi
   - Verifies prerequisites (gh CLI, auth)
   - Validates one known-good repo
   - **Usage:** `./quick_test_validation.sh`

3. **[`validate_all_candidates.sh`](validate_all_candidates.sh)** (120 lines) 📊 **Batch Runner**
   - Validates all 8 candidate repos
   - Generates timestamped output file
   - Rate-limit handling (3s pause between repos)
   - Summary statistics
   - **Usage:** `./validate_all_candidates.sh`

### Calibration Scripts

4. **[`run_calibration.py`](run_calibration.py)** — Full Pipeline Runner
   - Runs Phases 1-5 on a repository
   - Configurable parameters
   - Generates all outputs (events, signals, patterns, advisory)
   - **Usage:** `python run_calibration.py`

---

## Data Directories

### Input Repositories (not tracked in git)

```
repos/                          # Cloned candidate repositories
├── fastapi/                    # ✅ Cloned
├── gin/                        # ⏳ Pending
├── strapi/                     # ⏳ Pending
├── terraform/                  # ⏳ Pending
├── kubernetes/                 # ⏳ Pending
├── rails/                      # ⏳ Pending
├── spring-boot/                # ⏳ Pending
└── next.js/                    # ⏳ Pending
```

### Pipeline Outputs (not tracked in git)

```
runs/                           # Pipeline output per repo
├── evolution-engine/           # ✅ Run 1 (2026-02-06)
│   ├── events/                 # Phase 1: 11 git events
│   ├── phase2/                 # Phase 2: 24 signals
│   ├── phase3/                 # Phase 3: 24 explanations
│   ├── phase4/                 # Phase 4: knowledge.db (0 patterns)
│   └── phase5/                 # Phase 5: advisory reports
│       ├── advisory.json
│       ├── summary.txt
│       ├── chat.txt
│       ├── investigation_prompt.txt
│       └── evidence.json
├── fastapi/                    # ✅ Run 2 (2026-02-07)
│   └── ... (same structure)
└── [future repos]/             # ⏳ Pending multi-family runs
```

### Temporary Data

```
repo_candidates/                # Shallow clones for validation (depth=50)
├── fastapi/                    # Created by validate_repo.sh
├── gin/                        # Created on first validation
└── ...

validation_results_*.txt        # Timestamped validation outputs
```

---

## Workflow Summary

### Phase 1: Repository Discovery & Validation (Current)

```bash
# 1. Quick test (verify toolkit works)
./quick_test_validation.sh

# 2. Validate all candidates
./validate_all_candidates.sh

# 3. Review results
cat validation_results_*.txt

# 4. Update repo_validation.md with findings
# (manually fill in coverage matrices)

# 5. Rank by family coverage
# (select top 5 with 4+/8 families)
```

### Phase 2: Adapter Implementation (Next)

```
1. Implement Git History Walker
   └─ Use lockfile paths from validation
   
2. Implement GitHub API Adapter
   └─ Use CI run counts from validation
   
3. Test adapters on fastapi
   └─ Validate multi-family data extraction
```

### Phase 3: Multi-Family Calibration (Future)

```bash
# For each top-5 repo:
python run_calibration.py --repo REPO_NAME

# Review patterns
cat runs/REPO_NAME/phase5/summary.txt

# Classify patterns
# → Add to seed_patterns.json (if valid & generalizable)
# → Document in reports/REPO_NAME_calibration.md
```

### Phase 4: Seed KB Creation (Future)

```json
// seed_patterns.json
{
  "seed_version": "1.0",
  "calibrated_from": ["evolution-engine", "fastapi", "gin", "next.js", "spring-boot"],
  "patterns": [
    {
      "name": "Dependency Growth + Test Duration Increase",
      "sources": ["dependency", "testing"],
      "metrics": ["dependency_count", "suite_duration"],
      "typical_correlation": 0.72,
      "seen_in_repos": 5,
      "generalizable": true
    }
  ]
}
```

---

## Key Metrics

### Calibration Progress

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Repos validated | 8 | 0 | 🟡 Toolkit ready |
| Repos with 4+ families | 5 | 0 | 🟡 Awaiting validation |
| Calibration runs completed | 5 | 2 | 🟢 40% (git-only) |
| Validated patterns | 10+ | 0 | 🔴 Blocked (need multi-family) |
| Seed KB created | 1 | 0 | 🔴 Blocked (need patterns) |

### Code Statistics

| Item | Count | Lines |
|------|-------|-------|
| Documentation files | 8 | 2,248 |
| Automation scripts | 4 | 745 |
| Pipeline outputs | 2 repos | N/A |
| Validation reports | 2 | ~400 each |

---

## 8 Candidate Repositories

| # | Repo | Language | Expected Families | Priority |
|---|------|----------|------------------|----------|
| 1 | `fastapi/fastapi` | Python | Git, CI, Deps, Testing, Schema | ⭐⭐⭐ High |
| 2 | `gin-gonic/gin` | Go | Git, CI, Deps, Testing | ⭐⭐⭐ High |
| 3 | `strapi/strapi` | TypeScript | Git, CI, Deps, Testing, Schema | ⭐⭐⭐ High |
| 4 | `hashicorp/terraform` | Go | Git, CI, Deps, Config | ⭐⭐ Medium |
| 5 | `kubernetes/kubernetes` | Go | Git, CI, Deps, Security, Deployment | ⭐⭐⭐ High |
| 6 | `rails/rails` | Ruby | Git, CI, Deps, Testing, Schema | ⭐⭐ Medium |
| 7 | `spring-projects/spring-boot` | Java | Git, CI, Deps, Testing | ⭐⭐ Medium |
| 8 | `vercel/next.js` | TypeScript | Git, CI, Deps, Testing, Deployment | ⭐⭐⭐ High |

---

## Source Family Coverage

| Family | Validation Check | Acceptance Criteria |
|--------|-----------------|---------------------|
| Git | Commit count | 500+ commits |
| CI/Build | GitHub Actions API | 100+ workflow runs |
| Dependencies | Lockfile + git log | 20+ commits in lockfile |
| Testing | File count | 50+ test files |
| Schema/API | OpenAPI/GraphQL + git log | 10+ commits in schema |
| Deployment | GitHub Releases | 10+ releases OR 50+ tags |
| Config | Terraform/K8s + git log | 5+ commits in IaC |
| Security | GitHub API | Advisories OR Dependabot |

---

## Next Steps

### Immediate (This Week)

1. ✅ Create validation toolkit (COMPLETE)
2. ⏳ Run `./quick_test_validation.sh` to verify setup
3. ⏳ Run `./validate_all_candidates.sh` for batch validation
4. ⏳ Update `repo_validation.md` with results
5. ⏳ Select top 5 repos by family coverage

### Short-Term (Next 2 Weeks)

1. ⏳ Implement Git History Walker adapter
2. ⏳ Implement GitHub API adapter
3. ⏳ Run multi-family calibration on top 5 repos
4. ⏳ Classify and document discovered patterns
5. ⏳ Create `seed_patterns.json`

### Medium-Term (Next Month)

1. ⏳ Implement Fix Verification Loop (Phase 5b)
2. ⏳ Create HTML/PDF report generator
3. ⏳ Build consulting engagement materials
4. ⏳ First consulting pilot (real client repo)

---

## Key Insights from Calibration

### Discovery #1: Multi-Family Data Is Essential

**Problem:** Git-only runs discovered 0 patterns (both repos)

**Why:** Phase 4 detects **cross-family** patterns:
- "Dependency growth + test duration increase"
- "High dispersion + CI failure spike"
- "Schema churn + security vulnerability introduction"

**Solution:** Git History Walker + GitHub API adapters unlock 5+ additional families from any repo.

### Discovery #2: Historical Data > Snapshots

**Problem:** Running `pytest` once gives current test count, not trends

**Solution:** Extract lockfiles from git history:
```bash
git show HEAD~100:requirements.txt  # Dependencies 100 commits ago
git show HEAD~50:openapi.json       # API schema 50 commits ago
```

**Where it exists:**
- CI/CD: GitHub Actions API (full run history)
- Dependencies: Lockfiles in git history
- Schema: OpenAPI specs in git history
- Config: Terraform files in git history

### Discovery #3: Open-Source Data Is Abundant

Large open-source projects have **years** of multi-family data:
- 500+ commits (stable baselines)
- 100+ CI runs (correlation analysis)
- 20+ dependency lockfile commits (evolution tracking)
- Public APIs, security advisories, releases

**Calibration doesn't need synthetic data — just better adapters.**

---

## Files Created This Session (2026-02-08)

1. ✅ `P3_REPO_SEARCH.md` — Validation guide (716 lines)
2. ✅ `repo_validation.md` — Results template (353 lines)
3. ✅ `validate_repo.sh` — Core validation script (280 lines)
4. ✅ `quick_test_validation.sh` — Quick test script (65 lines)
5. ✅ `validate_all_candidates.sh` — Batch runner (120 lines)
6. ✅ `INDEX.md` — This file (you are here)
7. ✅ Updated `README.md` — Added calibration section
8. ✅ Updated `calibration_log.md` — Session entry
9. ✅ Updated `../README.md` — Added calibration to main README

**Total new content:** ~1,600 lines of documentation + automation

---

## Contact & Support

For questions about calibration workflow, see:
- [`CALIBRATION_GUIDE.md`](../docs/CALIBRATION_GUIDE.md) — Comprehensive operator manual
- [`CALIBRATION_SUMMARY.md`](CALIBRATION_SUMMARY.md) — Key findings and strategy
- [`calibration_log.md`](calibration_log.md) — Historical context

For technical issues:
- Check [`P3_REPO_SEARCH.md#9-troubleshooting`](P3_REPO_SEARCH.md#9-troubleshooting)
- Verify prerequisites: `gh auth status`
- Check API rate limits: `gh api rate_limit`

---

**This index will be updated as calibration progresses.**
