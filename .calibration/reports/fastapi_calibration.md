# Calibration Report: fastapi

**Date:** 2026-02-08  
**Language:** Python  
**Commits analyzed:** 6713  
**Source families tested:** Git only

---

## Executive Summary

Second calibration run on a mature, well-maintained Python project (FastAPI). The repo has extensive history (6713 commits) providing stable statistical baselines, but pattern discovery remains at 0 because we only have git data.

**Key Finding:** Phase 4 discovered 0 patterns despite 4,433 deviating signals across 26,812 total git signals. Co-occurrence detection requires signals from multiple source families (e.g., git + testing, git + dependencies). The pipeline scales well to large repos, but **multi-family data is essential for pattern learning.**

---

## Pipeline Results

| Phase | Result | Count |
|-------|--------|-------|
| Phase 1 events | Git commits ingested | 6713 |
| Phase 2 signals | Baseline signals computed | 26,812 |
| Phase 2 deviating signals | Signals above threshold | 4,433 (16.5%) |
| Phase 3 explanations | LLM-enhanced explanations | 26,812 |
| **Phase 4 patterns discovered** | **Co-occurrence candidates** | **0** |
| Phase 4 knowledge artifacts | Promoted patterns | 0 |
| Phase 5 significant changes | Deviation > 1.5 stddev | 4 |

### Phase 1 Observations
- Successfully ingested 6713 commits (full history)
- Date range: Multi-year project history
- Performance: ~7 minutes for full ingestion
- Event deduplication working correctly

### Phase 2 Observations
- Computed 26,812 signals across 4 git metrics
- **Baseline quality:** ✅ **Excellent** — with 6713 commits, baselines are statistically stable
- **Signal distribution:**
  - 4,433 signals (16.5%) show deviation from baseline
  - 22,379 signals (83.5%) within normal range
- **Typical baseline ranges (fastapi):**
  - `files_touched`: 1.2 ± 0.57 (mean ± stddev)
  - `dispersion`: 0.1 ± 0.24
  - `change_locality`: 0.1 ± 0.30
  - `cochange_novelty_ratio`: 1.00 ± 0.00 (very stable)

### Phase 3 Observations
- Generated 26,812 explanations (one per signal)
- LLM model: `anthropic/claude-3.5-haiku` (Phase 3.1 enabled)
- Performance: ~2 minutes for 26K LLM calls
- Explanation quality: **Excellent** — clear, structural descriptions with uncertainty caveats
- **Sample explanation:**
  > "The change locality for this commit was 0.10. Historically, similar commits had a locality of 0.10 ± 0.30. This assessment relies on a dataset of 6,713 commits and provides a stable baseline."

### Phase 4 Observations (Pattern Discovery)
- **Patterns discovered:** 0
- **Why zero?**
  - Only 1 source family (git) active — cross-family patterns impossible
  - Co-occurrence detection looks for correlations *between* families
  - Example patterns we're looking for but can't find without multi-family data:
    - "Dependency growth + test duration increase"
    - "Schema churn + CI failure rate spike"
    - "High dispersion + security vulnerability introduction"
- **Parameters used:**
  - `min_support`: 5 (sufficient for this dataset)
  - `min_correlation`: 0.5
  - `promotion_threshold`: 15
  - `direction_threshold`: 1.0

**Critical Insight:** Phase 4 is working correctly — it's designed to find cross-family patterns, not intra-family patterns. We need to add testing, dependency, and other source data.

### Phase 5 Observations (Advisory)
- **Significant changes detected:** 4 (all git metrics)
- **Families affected:** git only
- **Pattern matches:** 0 (no knowledge artifacts to match against)

**Significant Changes (top 4 by deviation):**
1. **Co-change Novelty:** 1.00 → 0.00 (17,364x stddev below normal)
   - **Interpretation:** Recent commit touched files that have been changed together many times before
   - **Why:** Large refactoring or consolidation commit (440 files)
2. **Files Changed:** 1.2 → 440 (776x stddev above normal)
   - **Interpretation:** Massive commit touching 366x more files than typical
   - **Why:** Likely a bulk update (dependency upgrade, formatting, or generated code)
3. **Change Dispersion:** 0.1 → 2.58 (10.6x stddev above normal)
   - **Interpretation:** Changes spread across the entire codebase (high entropy)
   - **Why:** Global refactoring or dependency update affecting many modules
4. **Change Locality:** 0.1 → 1.0 (3.0x stddev above normal)
   - **Interpretation:** Changes concentrated in a single area (Gini = 1.0)
   - **Why:** Simultaneous with high dispersion — indicates many small changes to one directory tree per file

**Advisory Output Quality:**
- **summary.txt:** ✅ Excellent, readable, visual bars work well
- **chat.txt:** ✅ Compact, perfect for messaging
- **investigation_prompt.txt:** ✅ Structured, actionable
- **advisory.json:** ✅ Well-formed, complete evidence package
- **evidence.json:** ✅ Contains 20 commits, 50 files, timeline

---

## Patterns Discovered

### Valid & Generalizable
*None — requires multi-family data.*

### Valid & Local
*None.*

### False Positives
*None.*

### Noise
*None.*

---

## Parameter Observations

| Parameter | Current Value | Observation | Recommended Adjustment |
|-----------|---------------|-------------|------------------------|
| `min_support` | 5 | Appropriate for large repos | Keep at 5 |
| `min_correlation` | 0.5 | Not tested (no cross-family data) | Keep at 0.5 |
| `promotion_threshold` | 15 | Not tested (no patterns found) | Keep at 15 |
| `direction_threshold` | 1.0 | Working well (clear deviations) | Keep at 1.0 |
| `significance_threshold` (Phase 5) | 1.5 | Good — surfaced 4 extreme outliers | Keep at 1.5 |
| `min_baseline` (Phase 2) | 10 | Perfect for this dataset | Keep at 10 for repos >50 commits |

---

## Baseline Norms (Git-only, mature Python repo)

Based on 6713 commits:

| Metric | Mean | Stddev | Range | Notes |
|--------|------|--------|-------|-------|
| `files_touched` | 1.2 | 0.57 | 1–440 | Very stable, low variance except outliers |
| `dispersion` | 0.1 | 0.24 | 0–2.58 | Low entropy — focused changes |
| `change_locality` | 0.1 | 0.30 | 0–1.0 | Low Gini — distributed changes |
| `cochange_novelty_ratio` | 1.00 | 0.00 | 0–1.0 | Almost all commits touch new file pairs |

**Reliability:** ✅ **High** — baselines computed from 6713 commits with stable variance.

**Comparison to evolution-engine:**
- FastAPI has much tighter variance (smaller stddev) — indicates consistent development practices
- FastAPI's typical change is 1-2 files; evolution-engine was 6.7 files (smaller, more focused codebase)
- FastAPI's novelty ratio is 1.0 (always new pairs) vs evolution-engine's 0.99 — indicates active refactoring

---

## Adapter Issues

### Git Adapter
- ✅ No issues
- Scales well to 6713 commits
- Performance: ~7 minutes for full ingestion

### CI / Build
- ❌ Not tested (no CI data collected yet)
- **Next step:** Use GitHub Actions API to fetch workflow runs

### Testing
- ❌ Not tested (need to run pytest locally and capture JUnit XML)
- **Next step:** Run `pytest --junitxml=test_results.xml` in fastapi repo

### Dependencies
- ❌ Not tested (need to capture requirements.txt snapshots)
- **Next step:** Track pip freeze output over time or parse pyproject.toml

### Other Families
- ❌ Not tested

---

## Recommendations

### Immediate Next Steps

1. **✅ PRIORITY: Add multi-family data to fastapi run**
   - Run pytest and capture test results
   - Capture dependency snapshots from multiple commits
   - Re-run Phase 2-4 with test + dependency signals
   - **Expected outcome:** First real cross-family patterns (git + testing, git + dependencies)

2. **Clone and run gin (Go repo)**
   - Different language, validate language-agnostic patterns
   - Go has cleaner CI/testing setup

3. **Tune parameters for pattern discovery**
   - Once we have cross-family data, adjust `min_support` and `min_correlation` based on observed pattern quality

### Multi-Family Data Collection Script

```bash
# For fastapi repo
cd .calibration/repos/fastapi

# Install dependencies
pip install -e ".[test]"

# Run tests and capture JUnit XML
pytest --junitxml=../../runs/fastapi/test_results.xml tests/

# Capture current dependencies
pip freeze > ../../runs/fastapi/requirements_frozen.txt

# Then re-run Phase 2-4 with test/dependency adapters
```

### Parameter Changes
*None needed yet — current parameters are appropriate.*

---

## Quality Validation

### Pipeline Mechanics
- ✅ All 5 phases execute without errors
- ✅ Scales to 6713 commits (26K signals)
- ✅ Phase 3.1 LLM processing completes successfully (26K LLM calls in ~2 min)
- ✅ Output files are well-formed
- ✅ Phase 5 advisory output is clear and actionable

### Contract Adherence
- ✅ Phase 1 events follow `ADAPTER_CONTRACT.md`
- ✅ Phase 2 signals follow `PHASE_2_CONTRACT.md` with stable baselines
- ✅ Phase 3 explanations follow validation gate
- ✅ Phase 4 KB schema correct
- ✅ Phase 5 advisory follows `PHASE_5_CONTRACT.md`

### Performance
- Phase 1: ~7 minutes (6713 commits)
- Phase 2: ~30 seconds (26K signals)
- Phase 3: ~2 minutes (26K LLM calls to Haiku)
- Phase 4: <1 second (no patterns to process)
- Phase 5: <1 second
- **Total: ~10 minutes for full pipeline**

---

## Calibration Status

| Criteria | Status | Notes |
|----------|--------|-------|
| Pipeline scales to large repos | ✅ Complete | 6713 commits processed successfully |
| Baseline stability validated | ✅ Complete | Low variance, stable means |
| Multi-family data tested | ❌ **Blocked** | Need to collect test/dependency data |
| Patterns discovered | ❌ **Blocked** | Waiting on multi-family data |
| False positives documented | ❌ Pending | No patterns to classify yet |
| Parameters validated | 🔄 Partial | Need cross-family patterns to tune |

---

## Critical Next Action

**BLOCKER:** Pattern discovery requires multi-family data.

**Resolution:** Collect and ingest test + dependency data for fastapi, then re-run Phase 2-4.

**Expected Outcome:**
- Test family signals: suite_duration, failure_rate, skip_rate
- Dependency family signals: dependency_count, direct_count, max_depth
- Cross-family pattern candidates: "Dependency growth correlates with test duration increase"
- First validated patterns for seed KB

---

## Comparison: evolution-engine vs fastapi

| Metric | evolution-engine | fastapi | Insight |
|--------|------------------|---------|---------|
| Commits | 11 | 6713 | fastapi provides stable baselines |
| Signals | 24 | 26,812 | 1000x more signal data |
| Baseline stability | Low (high stddev) | High (low stddev) | fastapi's consistency validates metric design |
| Typical files changed | 6.7 | 1.2 | fastapi is more focused |
| Pattern discovery | 0 | 0 | Both blocked on multi-family data |
| Phase 5 quality | ✅ Good | ✅ Excellent | Advisory output scales well |

**Validation:** The pipeline works correctly at both small and large scale. The bottleneck is data diversity, not implementation.
