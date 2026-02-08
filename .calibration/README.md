# Calibration Quick Reference

## Directory Structure

```
.calibration/
├── repos/                      # Cloned repositories (not tracked in git)
│   ├── fastapi/
│   ├── gin/
│   └── ...
├── runs/                       # Pipeline output per repo
│   ├── evolution-engine/
│   │   ├── events/             # Phase 1: Git events
│   │   ├── phase2/             # Phase 2: Signals
│   │   ├── phase3/             # Phase 3: Explanations
│   │   ├── phase4/             # Phase 4: Patterns & KB
│   │   └── phase5/             # Phase 5: Advisory reports
│   │       ├── advisory.json
│   │       ├── summary.txt
│   │       ├── chat.txt
│   │       ├── investigation_prompt.txt
│   │       └── evidence.json
│   └── ...
├── reports/                    # Calibration analysis
│   ├── evolution-engine_calibration.md
│   └── ...
├── calibration_log.md          # Running log of all runs
├── seed_patterns.json          # (To be created after 3+ repos)
└── run_calibration.py          # Reusable pipeline runner
```

## Completed Runs

### Run 1: evolution-engine ✅
- **Status:** Complete
- **Date:** 2026-02-06
- **Commits:** 11
- **Families:** Git only
- **Patterns found:** 0 (insufficient data)
- **Report:** `.calibration/reports/evolution-engine_calibration.md`
- **Key insight:** Pipeline works, but need larger repos for pattern discovery

### Run 2: fastapi ✅
- **Status:** Complete
- **Date:** 2026-02-07
- **Commits:** 6,713
- **Families:** Git only
- **Patterns found:** 0 (need multi-family data)
- **Report:** `.calibration/reports/fastapi_calibration.md`
- **Key insight:** Pattern discovery requires cross-family data (CI, deps, testing)

## Repository Search & Discovery

### Automated Search Agent (Recommended) 🚀

**NEW:** Automated discovery of 100+ repositories with multi-family data coverage.

```bash
# Discover and rank 100+ repositories automatically
python search_agent.py

# Custom search (500+ stars, 500 repos)
python search_agent.py --min-stars 500 --max-repos 500

# Specific languages only
python search_agent.py --languages Python Go TypeScript
```

**Output:** `repos_ranked.csv` with 100+ repositories ranked by calibration score

**See:** [`SEARCH_AGENT_GUIDE.md`](SEARCH_AGENT_GUIDE.md) for complete documentation

### Manual Validation (Alternative)

For manual validation of specific repositories:

```bash
# Validate single repository
./validate_repo.sh fastapi fastapi

# Quick test
./quick_test_validation.sh

# Batch validate pre-selected 8
./validate_all_candidates.sh
```

**See:** [`P3_REPO_SEARCH.md`](P3_REPO_SEARCH.md) for manual validation procedures

Results are tracked in `repo_validation.md`.

## Next Steps

1. ✅ Complete Phase 3 repo search (see `P3_REPO_SEARCH.md`)
2. ⏳ Implement Git History Walker adapter (dependencies, schema, config from git)
3. ⏳ Implement GitHub API adapter (CI, deployments, security)
4. ⏳ Run multi-family calibration on 5 repos
5. ⏳ Compile `seed_patterns.json` from validated patterns

## Commands

### Run calibration on a repo
```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
source .venv/bin/activate
python .calibration/run_calibration.py
```

### View Phase 5 reports
```bash
# Human-readable summary
cat .calibration/runs/evolution-engine/phase5/summary.txt

# Chat format
cat .calibration/runs/evolution-engine/phase5/chat.txt

# Investigation prompt
cat .calibration/runs/evolution-engine/phase5/investigation_prompt.txt
```

### Inspect Phase 4 patterns
```python
from pathlib import Path
from evolution.knowledge_store import SQLiteKnowledgeStore

kb = SQLiteKnowledgeStore(Path('.calibration/runs/evolution-engine/phase4/knowledge.db'))
patterns = kb.list_patterns()
for p in patterns:
    print(f'{p["sources"]} — {p["metrics"]} (corr={p.get("correlation_strength", 0):.2f})')
kb.close()
```

## Files Created This Session

1. `.calibration/` directory structure
2. `.calibration/calibration_log.md` — running log
3. `.calibration/run_calibration.py` — reusable pipeline runner
4. `.calibration/reports/evolution-engine_calibration.md` — detailed analysis
5. `.calibration/runs/evolution-engine/` — full pipeline outputs (Phase 1-5)
