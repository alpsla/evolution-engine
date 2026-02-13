# Evolution Engine — Calibration Guide

> **Operator Manual for Knowledge Base Seeding**
>
> This document provides step-by-step instructions for running the Evolution Engine
> against real open-source repositories to discover, validate, and curate patterns
> that will seed the Knowledge Base before production use.
>
> **Audience:** An AI assistant (Sonnet 4.5 or equivalent) or a human operator
> who will execute calibration runs systematically.

---

## 1. Prerequisites

### 1.1 Environment Setup

```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
source .venv/bin/activate
pip install -e .
```

Ensure `.env` has:
```
OPENROUTER_API_KEY=<your-key>
PHASE31_ENABLED=true
PHASE31_MODEL=anthropic/claude-3.5-haiku
PHASE4B_ENABLED=true
PHASE4B_MODEL=anthropic/claude-sonnet-4.5
```

### 1.2 Workspace Structure

Each calibration repo gets its own directory under `.calibration/`:

```
.calibration/
├── repos/                    # Cloned repositories
│   ├── fastapi/
│   ├── next.js/
│   └── ...
├── runs/                     # Pipeline output per repo
│   ├── fastapi/
│   │   ├── events/           # Phase 1
│   │   ├── phase2/           # Phase 2 signals
│   │   ├── phase3/           # Phase 3 explanations
│   │   ├── phase4/           # Phase 4 KB + patterns
│   │   └── phase5/           # Phase 5 advisories
│   └── ...
├── reports/                  # Calibration analysis per repo
│   ├── fastapi_calibration.md
│   └── ...
├── seed_patterns.json        # Curated patterns for seed KB
└── calibration_log.md        # Running log of all calibration activity
```

Create this structure before starting:
```bash
mkdir -p .calibration/repos .calibration/runs .calibration/reports
```

---

## 2. Target Repositories

### 2.1 Priority Order

Start with repos that are easiest to test and provide the most coverage:

| Priority | Repository | Language | Clone URL | Why First |
|----------|-----------|----------|-----------|-----------|
| **1** | **evolution-engine** | Python | (local) | Meta-calibration, we control it |
| **2** | **fastapi** | Python | `github.com/fastapi/fastapi` | Medium size, Python, has CI+tests+deps |
| **3** | **gin** | Go | `github.com/gin-gonic/gin` | Different language, clean CI |
| **4** | **next.js** | TypeScript | `github.com/vercel/next.js` | Large, JS ecosystem, npm deps |
| **5** | **spring-boot** | Java | `github.com/spring-projects/spring-boot` | Java ecosystem, large test suite |

### 2.2 Clone Commands

```bash
cd .calibration/repos
git clone --depth 500 https://github.com/fastapi/fastapi.git
git clone --depth 500 https://github.com/gin-gonic/gin.git
git clone --depth 200 https://github.com/vercel/next.js.git
git clone --depth 200 https://github.com/spring-projects/spring-boot.git
```

Use `--depth` to keep clone sizes manageable. 200-500 commits is sufficient for baseline calibration.

---

## 3. Calibration Procedure (Per Repository)

### 3.1 Step 1: Git-Only Run (Version Control Family)

Every repo starts with Git — this is the guaranteed source family.

```python
import sys
sys.path.insert(0, "/Users/Shared/OpenClaw-Workspace/repos/evolution-engine")

from pathlib import Path
from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.phase3_engine import Phase3Engine
from evolution.phase4_engine import Phase4Engine
from evolution.phase5_engine import Phase5Engine

REPO_NAME = "fastapi"  # Change per repo
REPO_PATH = Path(f".calibration/repos/{REPO_NAME}")
RUN_DIR = Path(f".calibration/runs/{REPO_NAME}")

# Phase 1: Ingest git history
from evolution.adapters.git import GitSourceAdapter
phase1 = Phase1Engine(RUN_DIR)
git_adapter = GitSourceAdapter(str(REPO_PATH))
git_count = phase1.ingest(git_adapter)
print(f"Phase 1: Ingested {git_count} git events")

# Phase 2: Compute baselines
phase2 = Phase2Engine(RUN_DIR, min_baseline=10)
git_signals = phase2.run_git()
print(f"Phase 2: {len(git_signals)} git signals")

# Phase 3: Generate explanations
phase3 = Phase3Engine(RUN_DIR)
explanations = phase3.run()
print(f"Phase 3: {len(explanations)} explanations")

# Phase 4: Discover patterns
phase4 = Phase4Engine(RUN_DIR, params={
    "min_support": 5,
    "min_correlation": 0.5,
    "promotion_threshold": 15,
    "direction_threshold": 1.0,
})
p4_result = phase4.run()
print(f"Phase 4: {p4_result['patterns_discovered']} patterns")

# Phase 5: Generate advisory
phase5 = Phase5Engine(RUN_DIR, significance_threshold=1.5)
p5_result = phase5.run(scope=REPO_NAME)
print(f"Phase 5: {p5_result['status']}")

phase4.close()
```

### 3.2 Step 2: Add Additional Source Families

For each repo, investigate what additional source data is available:

**Check for CI data:**
```bash
ls .calibration/repos/fastapi/.github/workflows/
```
If GitHub Actions workflows exist, the repo has CI data. Currently our CI adapter
requires pre-collected run data (JSON). For calibration, you can:
- Use the GitHub API to fetch recent workflow runs
- Or skip CI for now and focus on Git + Testing + Dependencies

**Check for test data:**
```bash
# Look for test configuration
ls .calibration/repos/fastapi/tests/
ls .calibration/repos/fastapi/pytest.ini 2>/dev/null
ls .calibration/repos/fastapi/setup.cfg 2>/dev/null
```
If tests exist, run them locally and capture JUnit XML output:
```bash
cd .calibration/repos/fastapi
pip install -e ".[test]" 2>/dev/null
pytest --junitxml=../../runs/fastapi/test_results.xml tests/ 2>/dev/null
```

**Check for dependency data:**
```bash
# Python
ls .calibration/repos/fastapi/requirements*.txt
ls .calibration/repos/fastapi/pyproject.toml
# JavaScript
ls .calibration/repos/fastapi/package.json
# Go
ls .calibration/repos/fastapi/go.mod
```

**Check for OpenAPI/schema data:**
```bash
ls .calibration/repos/fastapi/docs/ 2>/dev/null
find .calibration/repos/fastapi -name "openapi*.json" -o -name "openapi*.yaml" 2>/dev/null
```

### 3.3 Step 3: Review Phase 4 Patterns

After running the pipeline, examine the discovered patterns:

```python
from evolution.knowledge_store import SQLiteKnowledgeStore

kb = SQLiteKnowledgeStore(RUN_DIR / "phase4" / "knowledge.db")
patterns = kb.list_patterns()

print(f"\nTotal patterns: {len(patterns)}\n")
for p in sorted(patterns, key=lambda x: abs(x.get("correlation_strength", 0)), reverse=True):
    print(f"[{p['confidence_tier']}] {p['sources']} — {p['metrics']}")
    print(f"  corr={p.get('correlation_strength', 0):.2f}, "
          f"occurrences={p['occurrence_count']}")
    if p.get("description_semantic"):
        print(f"  semantic: {p['description_semantic']}")
    print(f"  statistical: {p.get('description_statistical', '')[:120]}")
    print()

kb.close()
```

### 3.4 Step 4: Classify Patterns

For each discovered pattern, classify it into one of these categories:

| Category | Action | Example |
|----------|--------|---------|
| **Valid & Generalizable** | Add to seed KB | "Dependency growth correlates with test suite duration increase" |
| **Valid & Local-only** | Keep in repo KB, don't generalize | "This specific module's changes correlate with CI time" |
| **False Positive** | Document and suppress | "Two metrics correlate only because both increase monotonically" |
| **Noise** | Ignore | Low correlation, low occurrence count |

**How to classify:**
1. **Does it make structural sense?** If dispersion increases and test failures increase, that's plausible — scattered changes are harder to test.
2. **Is it language-specific?** If the pattern only appears in Python repos and relates to Python-specific metrics, it's local.
3. **Is it a monotonic artifact?** If both metrics simply grow over time (test count, dependency count), correlation is spurious.
4. **Is it strong enough?** Correlation < 0.5 and occurrence < 10 is probably noise.

### 3.5 Step 5: Write Calibration Report

For each repo, create a report at `.calibration/reports/{repo}_calibration.md`:

```markdown
# Calibration Report: {repo_name}

**Date:** YYYY-MM-DD
**Language:** {language}
**Commits analyzed:** {N}
**Source families tested:** Git, [others]

## Pipeline Results

| Phase | Count |
|-------|-------|
| Phase 1 events | {N} |
| Phase 2 signals | {N} |
| Phase 3 explanations | {N} |
| Phase 4 patterns discovered | {N} |
| Phase 4 knowledge artifacts | {N} |
| Phase 5 significant changes | {N} |

## Patterns Discovered

### Valid & Generalizable
- {pattern description}: corr={X}, occurrences={N}
  Why: {structural reasoning}

### Valid & Local
- {pattern description}: corr={X}, occurrences={N}
  Why: {specific to this repo's structure}

### False Positives
- {pattern description}: corr={X}, occurrences={N}
  Why: {reason it's spurious — e.g., monotonic growth}

## Parameter Observations
- min_support={X} worked well / was too low / too high
- min_correlation={X} produced {N} patterns — adjust to {Y}?
- significance_threshold={X} surfaced {N} changes — too many / too few?

## Baseline Norms (for this language/size)
- files_touched: typical range {X}-{Y}
- dispersion: typical range {X}-{Y}
- [other metrics with stable ranges]

## Adapter Issues
- [Any data quality problems, missing fields, parse errors]

## Recommendations
- [Suggested parameter changes]
- [Patterns to add to seed KB]
- [New adapters needed]
```

---

## 4. Parameter Tuning

### 4.1 Parameters to Track

| Parameter | Current Default | What to Watch |
|-----------|---------------|---------------|
| `min_support` | 3 | Too low = too many noise patterns. Too high = miss real patterns. Target: 5-10 for calibration. |
| `min_correlation` | 0.5 | Too low = spurious correlations. Too high = miss weak but real signals. Target: 0.5-0.7. |
| `promotion_threshold` | 10 | How many times before pattern becomes knowledge. Target: 15-25 for production. |
| `direction_threshold` | 1.0 | Stddev threshold for "increased/decreased". 1.0 is standard; try 0.8 and 1.5. |
| `significance_threshold` (Phase 5) | 1.5 | How many stddev before a change is "significant". Try 1.0, 1.5, 2.0. |
| `min_baseline` (Phase 2) | 5 | Minimum events before baselines are computed. Try 10, 20 for large repos. |

### 4.2 Tuning Process

For each repo, run the pipeline 3 times with different parameter sets:

**Conservative (fewer patterns, higher quality):**
```python
params_conservative = {
    "min_support": 10,
    "min_correlation": 0.7,
    "promotion_threshold": 25,
    "direction_threshold": 1.5,
}
```

**Moderate (balanced):**
```python
params_moderate = {
    "min_support": 5,
    "min_correlation": 0.5,
    "promotion_threshold": 15,
    "direction_threshold": 1.0,
}
```

**Aggressive (more patterns, more noise):**
```python
params_aggressive = {
    "min_support": 3,
    "min_correlation": 0.3,
    "promotion_threshold": 10,
    "direction_threshold": 0.8,
}
```

Record how many patterns each produces and what the quality looks like. The goal is to find the sweet spot where:
- 80%+ of discovered patterns are "valid" (not false positives)
- Cross-family patterns are consistently found
- Single-family noise is filtered out

---

## 5. Seed KB Curation

### 5.1 What Goes Into the Seed KB

After calibrating across 3+ repos, compile validated patterns into `.calibration/seed_patterns.json`:

```json
{
  "seed_version": "1.0",
  "calibrated_from": ["evolution-engine", "fastapi", "gin"],
  "patterns": [
    {
      "name": "Dependency Growth + Test Duration Increase",
      "sources": ["dependency", "testing"],
      "metrics": ["dependency_count", "suite_duration"],
      "typical_correlation": 0.72,
      "seen_in_repos": 3,
      "description_semantic": "As the dependency count grows, test suite execution time increases proportionally, reflecting the overhead of validating a larger dependency surface.",
      "generalizable": true,
      "notes": "Consistent across Python and Go repos."
    }
  ],
  "false_positives": [
    {
      "name": "Monotonic Growth Artifact",
      "sources": ["schema", "dependency"],
      "metrics": ["endpoint_count", "dependency_count"],
      "why_false": "Both metrics grow monotonically in active repos. Correlation is an artifact of time, not structural coupling.",
      "mitigation": "Consider detrending or rate-of-change metrics in future versions."
    }
  ],
  "recommended_defaults": {
    "min_support": 5,
    "min_correlation": 0.5,
    "promotion_threshold": 15,
    "direction_threshold": 1.0,
    "significance_threshold": 1.5,
    "min_baseline": 10
  }
}
```

### 5.2 Quality Bar

A pattern should only enter the seed KB if:
- Seen in at least 2 different repos
- Correlation strength >= 0.5
- Has a plausible structural explanation (not a monotonic artifact)
- Not language-specific (or explicitly tagged as such)

---

## 6. Calibration Log

Maintain a running log at `.calibration/calibration_log.md`:

```markdown
# Calibration Log

## 2026-02-08: evolution-engine (meta)
- Git only, 11 commits
- 70 patterns discovered with aggressive params — too many, mostly noise
- Recommended: raise min_support to 5, min_correlation to 0.5

## 2026-02-09: fastapi
- Git: 500 commits, Python
- Testing: pytest with 200+ tests
- Dependencies: requirements.txt with 15 direct deps
- Results: ...
```

---

## 7. Source Family Coverage Checklist

Track which source families have been tested with real data:

| Family | Adapter | Tested With Real Data? | Repos Tested |
|--------|---------|----------------------|-------------|
| Version Control | GitSourceAdapter | [ ] | |
| CI / Build | (GitHub API needed) | [ ] | |
| Test Execution | JUnitXMLAdapter | [ ] | |
| Dependency | PipDependencyAdapter | [ ] | |
| Schema / API | OpenAPIAdapter | [ ] | |
| Deployment | GitHubReleasesAdapter | [ ] | |
| Configuration | TerraformAdapter | [ ] | |
| Security | TrivyAdapter | [ ] | |

### Notes on Real Data Collection

**Git:** Works out of the box with any git repo. No issues expected.

**CI / Build:** The current `GitHubActionsAdapter` needs pre-collected JSON data. To get real CI data:
```bash
# Fetch recent GitHub Actions runs via API
gh api repos/{owner}/{repo}/actions/runs --paginate -q '.workflow_runs[:50]' > ci_runs.json
```
You may need to write a small adapter script to convert this to the format our adapter expects.

**Testing:** Run the repo's test suite with JUnit XML output:
```bash
# Python (pytest)
pytest --junitxml=test_results.xml

# Go
go test -v ./... 2>&1 | go-junit-report > test_results.xml

# JavaScript (jest)
npx jest --reporters=jest-junit
```

**Dependencies:**
```bash
# Python
pip freeze > requirements_frozen.txt

# JavaScript
npm ls --all --json > deps.json

# Go
go list -m all > go_modules.txt
```

**Security:** Run Trivy locally:
```bash
# Container scan
trivy image --format json -o scan.json {image}

# Filesystem scan
trivy fs --format json -o scan.json .
```

---

## 8. Success Criteria

Calibration is complete when:

- [ ] 5+ repos have been run through the full pipeline
- [ ] 3+ languages are represented (Python, Go, TypeScript minimum)
- [ ] Seed KB contains 10+ validated, generalizable patterns
- [ ] False positive list documents 5+ known spurious correlations
- [ ] Recommended parameter defaults are validated across all repos
- [ ] Each calibration report is written and reviewed
- [ ] At least 2 source families beyond Git have been tested with real data
- [ ] Phase 5 advisory output has been reviewed for clarity and usefulness

---

## 9. Common Issues and Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Too many patterns | 100+ patterns from a single repo | Raise `min_support` to 5-10, `min_correlation` to 0.6+ |
| No patterns | 0 patterns discovered | Lower `min_correlation` to 0.3, check that signals actually deviate |
| All patterns are noise | Patterns between unrelated metrics | Raise `min_correlation`, consider adding intra-family filtering |
| Phase 2 produces few signals | Most events below baseline threshold | Lower `min_baseline` to 5, check that repo has enough history |
| Phase 5 advisory too verbose | 20+ "significant" changes | Raise `significance_threshold` to 2.0 |
| Phase 5 advisory empty | No significant changes | Lower `significance_threshold` to 1.0, check Phase 2 output |
| LLM semantic descriptions are vague | "Various metrics are changing" | Check that Phase 3 explanations exist and are meaningful |
| KB database errors | SQLite lock or corruption | Delete `knowledge.db` and re-run Phase 4 from scratch |

---

## 10. Quick Reference

### Run full pipeline on a repo:
```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
PHASE31_ENABLED=false PHASE4B_ENABLED=false python -c "
from pathlib import Path
from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.phase3_engine import Phase3Engine
from evolution.phase4_engine import Phase4Engine
from evolution.phase5_engine import Phase5Engine
from evolution.adapters.git import GitSourceAdapter

REPO = 'fastapi'
run_dir = Path(f'.calibration/runs/{REPO}')
repo_path = Path(f'.calibration/repos/{REPO}')

p1 = Phase1Engine(run_dir)
p1.ingest(GitSourceAdapter(str(repo_path)))

p2 = Phase2Engine(run_dir, min_baseline=10)
p2.run_all()

p3 = Phase3Engine(run_dir)
p3.run()

p4 = Phase4Engine(run_dir, params={'min_support': 5, 'min_correlation': 0.5, 'promotion_threshold': 15})
r4 = p4.run()
print(f'Patterns: {r4[\"patterns_discovered\"]}')

p5 = Phase5Engine(run_dir, significance_threshold=1.5)
r5 = p5.run(scope=REPO)
print(f'Significant changes: {r5.get(\"advisory\", {}).get(\"summary\", {}).get(\"significant_changes\", 0)}')

p4.close()
"
```

### Inspect patterns:
```bash
python -c "
from pathlib import Path
from evolution.knowledge_store import SQLiteKnowledgeStore
kb = SQLiteKnowledgeStore(Path('.calibration/runs/fastapi/phase4/knowledge.db'))
for p in sorted(kb.list_patterns(), key=lambda x: abs(x.get('correlation_strength',0)), reverse=True)[:10]:
    print(f'{p[\"sources\"]} — {p[\"metrics\"]} corr={p.get(\"correlation_strength\",0):.2f} occ={p[\"occurrence_count\"]}')
    if p.get('description_semantic'): print(f'  {p[\"description_semantic\"]}')
kb.close()
"
```

### Read Phase 5 advisory:
```bash
cat .calibration/runs/fastapi/phase5/summary.txt
```

### Read investigation prompt:
```bash
cat .calibration/runs/fastapi/phase5/investigation_prompt.txt
```
