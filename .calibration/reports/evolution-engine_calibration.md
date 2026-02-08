# Calibration Report: evolution-engine (Meta-Calibration)

**Date:** 2026-02-06  
**Language:** Python  
**Commits analyzed:** 11  
**Source families tested:** Git only

---

## Executive Summary

This is the first calibration run (meta-calibration) on the Evolution Engine repository itself. The repo has limited history (11 commits), making it suitable for validating pipeline mechanics but insufficient for meaningful pattern discovery.

**Key Finding:** Phase 4 discovered 0 patterns due to insufficient data. Cross-family patterns require multiple source families, and co-occurrence detection needs more signal accumulation. This validates the need for running the pipeline multiple times and/or on repos with more history.

---

## Pipeline Results

| Phase | Result | Count |
|-------|--------|-------|
| Phase 1 events | Git commits ingested | 11 |
| Phase 2 signals | Baseline signals computed | 24 |
| Phase 3 explanations | LLM-generated explanations | 24 |
| **Phase 4 patterns discovered** | **Co-occurrence candidates** | **0** |
| Phase 4 knowledge artifacts | Promoted patterns | 0 |
| Phase 5 significant changes | Deviation > 1.5 stddev | 4 |

### Phase 1 Observations
- Successfully ingested 11 git commits
- Date range: Recent development (2026-02-08)
- Event deduplication working correctly (0 duplicates on re-run)

### Phase 2 Observations
- Computed 24 signals across 4 git metrics:
  - `files_touched`: files changed per commit
  - `dispersion`: Shannon entropy of directory distribution
  - `change_locality`: Gini coefficient of file change concentration
  - `cochange_novelty_ratio`: fraction of file pairs never seen together before
- **Baseline quality:** With only 11 commits, baselines have high uncertainty (large stddev)
- **Signal quality:** All signals show large deviations because the dataset is too small

### Phase 3 Observations
- Generated 24 explanations (one per signal)
- LLM model: `anthropic/claude-3.5-haiku` (Phase 3.1 enabled)
- Explanation quality: **Good** — correctly describes the structural metrics and includes uncertainty caveats
- Example explanation (for `cochange_novelty_ratio` = 0.62):
  > "The co-change novelty ratio for this change was 0.62. Historically, similar changes had a novelty ratio of 0.99 ± 0.03. The comparison relies on a limited historical dataset and could shift with additional information."

### Phase 4 Observations (Pattern Discovery)
- **Patterns discovered:** 0
- **Why zero?**
  - Only 1 source family (git) active — cross-family patterns impossible
  - Insufficient signal accumulation (only 24 signals from 11 commits)
  - Co-occurrence detection requires `min_support=3` concurrent deviations
  - Small dataset doesn't produce stable correlations
- **Parameters used:**
  - `min_support`: 3
  - `min_correlation`: 0.5
  - `promotion_threshold`: 10
  - `direction_threshold`: 1.0

**Implication:** This repo needs to be run multiple times as development continues, OR we need to test on repos with 100+ commits and multiple source families.

### Phase 5 Observations (Advisory)
- **Significant changes detected:** 4 (all git metrics)
- **Families affected:** git only
- **Pattern matches:** 0 (no knowledge artifacts to match against)

**Significant Changes (top 4 by deviation):**
1. **Co-change Novelty:** 0.99 → 0.62 (11.4 stddev below normal)
   - **Interpretation:** Recent commits touched files that have never been changed together before
   - **Why:** Large merge commit with 51 files across diverse directories (synthetic_wide, docs, evolution)
2. **Files Changed:** 6.7 → 51 (5.2 stddev above normal)
   - **Interpretation:** One commit touched 51 files, far more than the typical 6.7 ± 8.5
   - **Why:** Merge commit consolidating branch work
3. **Change Dispersion:** 0.3 → 1.5 (2.9 stddev above normal)
   - **Interpretation:** Changes spread across multiple directories (high entropy)
   - **Why:** Merge touched `docs/`, `evolution/`, `synthetic_wide/` simultaneously
4. **Change Locality:** 0.2 → 1.0 (2.5 stddev above normal)
   - **Interpretation:** Changes concentrated in a single area (Gini = 1.0)
   - **Why:** Merge commit affected one large directory tree

**Advisory Output Quality:**
- **summary.txt:** ✅ Clean, readable, visual bars work
- **chat.txt:** ✅ Compact, suitable for Telegram/Slack
- **investigation_prompt.txt:** ✅ Structured, ready for AI assistant
- **advisory.json:** ✅ Well-formed JSON with all contract fields
- **evidence.json:** ✅ Contains commit list, files, timeline

---

## Patterns Discovered

### Valid & Generalizable
*None discovered (insufficient data).*

### Valid & Local
*None discovered.*

### False Positives
*None discovered.*

### Noise
*None discovered.*

---

## Parameter Observations

| Parameter | Current Value | Observation | Recommended Adjustment |
|-----------|---------------|-------------|------------------------|
| `min_support` | 3 | Too high for small repos (11 commits) | **Lower to 2 for repos <50 commits** |
| `min_correlation` | 0.5 | Not tested (no patterns found) | Keep at 0.5 for next run |
| `promotion_threshold` | 10 | Not tested (no patterns found) | Keep at 10 for testing |
| `direction_threshold` | 1.0 | Working well (clear signal deviation) | Keep at 1.0 |
| `significance_threshold` (Phase 5) | 1.5 | Good — surfaced 4 meaningful changes | Keep at 1.5 |
| `min_baseline` (Phase 2) | 5 | Too high for 11 commits (45% of data) | **Lower to 3 for repos <50 commits** |

---

## Baseline Norms (Git-only, small Python repo)

Based on 11 commits:

| Metric | Mean | Stddev | Range | Notes |
|--------|------|--------|-------|-------|
| `files_touched` | 6.7 | 8.5 | 1–51 | High variance due to merge commit |
| `dispersion` | 0.32 | 0.41 | 0–1.7 | Typical for small focused changes |
| `change_locality` | 0.19 | 0.32 | 0–1.0 | Gini coefficient, 1.0 = fully concentrated |
| `cochange_novelty_ratio` | 0.99 | 0.03 | 0.62–1.0 | Usually high (new file pairs) |

**Reliability:** ⚠️ **Low** — baselines computed from only 11 commits. Expect these to stabilize after 50+ commits.

---

## Adapter Issues

### Git Adapter
- ✅ No issues
- Works correctly with `GitPython`
- Deduplication by commit SHA working

### CI / Build
- ❌ Not tested (no CI data in this repo yet)

### Testing
- ❌ Not tested (no test suite runs captured)

### Dependencies
- ❌ Not tested (no dependency snapshots ingested)

### Other Families
- ❌ Not tested

---

## Recommendations

### Immediate Next Steps
1. **Run on a larger repo:** Clone `fastapi` (500 commits) and run the same pipeline
2. **Add multi-family data:** Collect test results (pytest --junitxml) and dependency snapshots (pip freeze) for evolution-engine
3. **Lower min_support:** Change to 2 for small repos to allow pattern discovery with less data

### Parameter Changes for Next Run
```python
phase4 = Phase4Engine(RUN_DIR, params={
    "min_support": 2,          # Lowered from 3 for small repos
    "min_correlation": 0.5,    # Keep
    "promotion_threshold": 10, # Keep
    "direction_threshold": 1.0, # Keep
})
```

### Patterns to Add to Seed KB
*None yet — need cross-family patterns from larger repos.*

### New Adapters Needed
- ✅ GitSourceAdapter — working
- 🔄 JUnitXMLAdapter — exists but not tested with real data
- 🔄 PipDependencyAdapter — exists but not tested with real data
- ❌ GitHub Actions API adapter — needed for real CI data collection

---

## Quality Validation

### Pipeline Mechanics
- ✅ All 5 phases execute without errors
- ✅ Output directories created correctly
- ✅ JSON files are well-formed
- ✅ Phase outputs chain correctly (Phase 2 reads Phase 1, Phase 3 reads Phase 2, etc.)

### Contract Adherence
- ✅ Phase 1 events follow `ADAPTER_CONTRACT.md`
- ✅ Phase 2 signals follow `PHASE_2_CONTRACT.md`
- ✅ Phase 3 explanations follow validation gate (no recommendations, no judgment)
- ✅ Phase 4 KB schema matches `PHASE_4_DESIGN.md`
- ✅ Phase 5 advisory follows `PHASE_5_CONTRACT.md`

### Output Quality
- ✅ **summary.txt** is human-readable and clear
- ✅ **chat.txt** is concise and suitable for messaging platforms
- ✅ **investigation_prompt.txt** is actionable for AI assistants
- ✅ **advisory.json** is well-structured and complete
- ✅ Visual bars in summary.txt render correctly

---

## Calibration Status

| Criteria | Status | Notes |
|----------|--------|-------|
| Pipeline works end-to-end | ✅ Complete | All phases execute successfully |
| Multi-family data tested | ❌ Pending | Only git data so far |
| Patterns discovered | ❌ Pending | Need larger repos or multi-family data |
| False positives documented | ❌ Pending | No patterns to classify yet |
| Parameters validated | 🔄 Partial | Need to test with pattern discovery |
| Baseline norms established | 🔄 Partial | Git-only, low confidence |

---

## Next Calibration Target

**Repository:** `fastapi` (Python, medium size, good CI + test + dependency coverage)  
**Expected improvements:**
- 500 commits → stable baselines
- Real pytest output → test family signals
- requirements.txt → dependency family signals
- Potential for cross-family pattern discovery (git + testing, git + dependencies)
