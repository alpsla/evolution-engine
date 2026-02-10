# Session Transition — 2026-02-09

## What Was Done This Session

### 6-Wave Data Quality Fix (ALL COMPLETED)

The pipeline was producing unreliable output: 8/13 metrics degenerate, absurd deviation scores (775σ, 17,364σ), explanation mismatches, single-event conflation. All 6 waves were implemented and tested:

| Wave | File(s) | What Changed |
|------|---------|-------------|
| 1 | `evolution/phase2_engine.py` | Replaced z-score with MAD/IQR robust deviation + degenerate flagging |
| 2 | `evolution/phase2_engine.py`, `evolution/adapters/deployment/github_releases_adapter.py` | Removed 5 degenerate metrics (`job_count`, `failure_rate`, `deploy_duration`, `is_rollback`, `direct_count`), added 4 (`run_failed`, `release_cadence_hours`, `is_prerelease`, `asset_count`), mega-commit novelty cap |
| 3 | `evolution/phase4_engine.py` | Pre-filter degenerate signals, confidence weighting (`r * min(1, n/30)`), diagnostic logging |
| 4 | `evolution/phase5_engine.py` | Compound-key explanation lookup, event grouping by trigger, candidate pattern surfacing, degenerate filter in `_filter_significant()`, METRIC_LABELS update |
| 5 | `evolution/phase4_engine.py` | Temporal alignment pass (24h windows) supplements commit-SHA alignment for sparse cross-family overlap |
| 6 | `evolution/phase3_engine.py` | Templates updated for new/removed metrics, degenerate handling, median/MAD display |

### E2E Test on fastapi (PASSED)

```
Pipeline: 6.6s total (Phase 2: 4.6s, Phase 3: 0.6s, Phase 4: 0.7s, Phase 5: 0.6s)
Events:   11,593 cached
Signals:  27,390 across 4 families (ci: 990, dep: 4,121, deploy: 498, git: 21,781)
Deviating: 4,421 (16%)
Advisory: 6 significant changes across ci, dependency, git
Patterns: 0 discovered (neither commit-SHA nor temporal alignment)
```

Run command: `PHASE31_ENABLED=false PHASE4B_ENABLED=false PYTHONUNBUFFERED=1 .venv/bin/python examples/run_e2e.py`

## Uncommitted Changes

All changes are unstaged. Files modified:

```
M  evolution/phase2_engine.py          (Waves 1, 2)
M  evolution/phase3_engine.py          (Wave 6)
M  evolution/phase4_engine.py          (Waves 3, 5)
M  evolution/phase5_engine.py          (Wave 4)
M  evolution/adapters/deployment/github_releases_adapter.py  (Wave 2)
M  docs/IMPLEMENTATION_PLAN.md         (prior session)
M  evolution/adapters/git/git_adapter.py       (prior session)
M  evolution/adapters/git/git_history_walker.py (prior session)
?? examples/calibrate_repo.py
?? examples/debug_phase3.py            (can delete — diagnostic script)
?? examples/rerun_phases2_5.py         (can delete — diagnostic script)
?? examples/run_e2e.py                 (keep — useful E2E test runner)
```

Tests: 2/2 pass (`pytest tests/ -v`)

## Remaining Issues (Priority Order)

### 1. Phase 4 discovers 0 patterns (HIGH)
Despite 4,421 deviating signals across 4 families, no cross-family correlations found. Both commit-SHA and temporal alignment passes returned empty. Possible causes:
- `min_support=3` too strict for sparse cross-family overlap (git: 6,708 commits, CI: 58 runs, shared SHAs: ~11)
- After degenerate filtering, remaining metrics may not have enough co-deviating pairs
- **Investigation needed**: Log metric pair overlap counts, check if temporal buckets produce any shared windows, consider lowering `min_support` to 2 for temporal alignment

### 2. Extreme IQR deviation display (MEDIUM)
- `files_touched`: 1030x IQR (764-file commit vs median 1)
- `cochange_novelty_ratio`: -405x IQR (0.0 vs median 1.0)
- Mathematically correct but meaningless at this scale
- **Options**: Cap display at ±100, use percentile rank, or log-scale for display

### 3. `.env` silently enables LLM — calibration trap (HIGH)
The `.env` file has `PHASE31_ENABLED=true` with an OpenRouter API key. When running calibration, `load_dotenv()` picks this up and Phase 3 attempts 27K+ LLM calls per repo (hangs for hours).
- **Fix options**:
  - Add CLI flag `--no-llm` to calibration scripts
  - Add `CALIBRATION_MODE=true` env var that auto-disables LLM
  - Update `.env` to have `PHASE31_ENABLED=false` by default
- **Workaround**: Always prefix calibration with `PHASE31_ENABLED=false PHASE4B_ENABLED=false`

### 4. LLM cost optimization (HIGH — user concern)
User reports ~$5 per Claude Code session. For batch calibration of 120 repos with LLM:
- Phase 3: 27K signals/repo × 120 repos = 3.3M LLM calls (OpenRouter haiku ~$0.0001/call = ~$330)
- Phase 4b: Much fewer but uses Sonnet (~$0.003/call)
- **Options to discuss**:
  - Skip LLM entirely for calibration (template-only) — already fast at 0.6s/repo
  - Sample only top-N deviating signals for LLM enhancement (e.g. top 50 per repo)
  - Batch-process explanations in groups rather than 1-by-1
  - Run LLM enhancement as a separate post-calibration step on interesting repos only

### 5. Dependency `count=0` noise (LOW)
Early fastapi commits (2018) before `pyproject.toml` existed show `dependency_count=0`. This triggers as a deviation but is a data collection artifact, not a meaningful signal. Consider:
- Minimum `dependency_count` threshold before emitting signal
- Or mark as "insufficient data" when count=0 in early history

## Architecture Notes

### Signal Shape (post-fix)
```json
{
  "engine_id": "git",
  "metric": "files_touched",
  "observed": 764,
  "baseline": {"mean": 4.48, "stddev": 12.66, "median": 1.0, "mad": 0.0},
  "deviation": {"measure": 1030.05, "unit": "iqr_normalized", "degenerate": false},
  "window": {"size": 50, "from": "...", "to": "..."},
  "confidence": {"status": "sufficient", "sample_count": 50}
}
```

### Deviation Units
- `modified_zscore` = `0.6745 * (observed - median) / MAD` (primary, when MAD > 0)
- `iqr_normalized` = `(observed - median) / (IQR / 1.35)` (fallback when MAD=0, IQR > 0)
- `degenerate` = MAD=0 AND IQR=0 (constant baseline, excluded from advisory)

### Phase 4 Alignment
- Pass 1: Commit-SHA alignment (precise, preferred)
- Pass 2: Temporal alignment (24h windows, supplementary for sparse cross-family overlap)
- `discovered_pairs` set prevents duplicates between passes

## Quick Start for Next Session

```bash
# Run tests
.venv/bin/python -m pytest tests/ -v

# Run E2E (no LLM)
PHASE31_ENABLED=false PHASE4B_ENABLED=false PYTHONUNBUFFERED=1 .venv/bin/python examples/run_e2e.py

# Check Phase 4 debug output
cat .calibration/runs/fastapi/phase4/phase4_summary.json

# Read advisory
cat .calibration/runs/fastapi/phase5/summary.txt
```
