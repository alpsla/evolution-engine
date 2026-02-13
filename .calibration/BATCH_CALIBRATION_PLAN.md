# Batch Calibration Plan — 120 Repos in Parallel

> **Goal:** Run the full Evolution Engine pipeline (Phases 1-5) on all 120 candidate repos
> to collect as many cross-family patterns as possible for the seed Knowledge Base.
>
> **Method:** Parallel Claude Code agents (Sonnet 4.5) with `--dangerously-skip-permissions`.
>
> **Created:** February 8, 2026

---

## Prerequisites

### Environment Setup

```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine

# Activate venv
source .venv/bin/activate

# Set GitHub token (required for CI, deployment, security families)
export GITHUB_TOKEN=<your-token>

# LLM enhancement (optional — both have retry/backoff and graceful fallback)
# export PHASE31_ENABLED=true   # Phase 3.1 LLM renderer (requires OPENROUTER_API_KEY or ANTHROPIC_API_KEY)
# export PHASE4B_ENABLED=true   # Phase 4b semantic interpreter (same key requirement)
```

### Verify Token Works

```bash
# Option 1: Using gh CLI (recommended - handles auth automatically)
gh api rate_limit --jq '.resources.core | "Rate limit: \(.remaining)/\(.limit) (resets: \(.reset | todateiso8601))"'

# Option 2: Using curl with GITHUB_TOKEN env var
if [ -z "$GITHUB_TOKEN" ]; then
  echo "GITHUB_TOKEN not set. Using gh CLI instead:"
  gh api rate_limit --jq '.resources.core | "Rate limit: \(.remaining)/\(.limit)"'
else
  # Use jq if available (simpler than Python)
  if command -v jq &> /dev/null; then
    curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit | \
      jq -r '.resources.core | "Rate limit: \(.remaining)/\(.limit) (resets: \(.reset | todateiso8601))"'
  else
    # Fallback to Python (handles errors gracefully)
    curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit | \
      python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    core = data['resources']['core']
    remaining = core['remaining']
    limit = core['limit']
    reset_time = core['reset']
    print(f'Rate limit: {remaining}/{limit} (resets at {reset_time})')
except (KeyError, json.JSONDecodeError) as e:
    print(f'Error parsing rate limit response: {e}', file=sys.stderr)
    sys.exit(1)
"
  fi
fi
```

GitHub free tier: 5,000 requests/hour. With 120 repos × ~55 API requests each = ~6,600 requests.
Running in batches or pacing is needed to stay within limits.

---

## Batch Calibration Script

The script is at `examples/batch_calibrate.py`.

### List All Repos
```bash
python examples/batch_calibrate.py --list
```

### Single Repo Test
```bash
python examples/batch_calibrate.py tiangolo/fastapi
```

### Run All (Sequential)
```bash
python examples/batch_calibrate.py --all --skip-existing
```

### Run in Batches (for Parallel Agents)
```bash
# 12 batches of 10 repos each (adjust batch-size as needed)
python examples/batch_calibrate.py --batch 0 --batch-size 10 --skip-existing
python examples/batch_calibrate.py --batch 1 --batch-size 10 --skip-existing
# ... through batch 11
```

---

## Parallel Execution with Claude Code Agents

### Option A: Multiple Claude Code Sessions (Recommended)

Open multiple terminal sessions, each running a different batch:

```bash
# Terminal 1
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
claude --dangerously-skip-permissions --model sonnet -p "
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
source .venv/bin/activate
export GITHUB_TOKEN=<token>
.venv/bin/python examples/batch_calibrate.py --batch 0 --batch-size 8 --skip-existing
"

# Terminal 2
claude --dangerously-skip-permissions --model sonnet -p "
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
source .venv/bin/activate
export GITHUB_TOKEN=<token>
.venv/bin/python examples/batch_calibrate.py --batch 1 --batch-size 8 --skip-existing
"

# ... repeat for each batch
```

### Option B: Shell-Based Parallel (Simpler)

```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
export GITHUB_TOKEN=<token>

# Run 4 batches in parallel (adjust based on CPU/memory)
for batch in 0 1 2 3; do
  .venv/bin/python examples/batch_calibrate.py \
    --batch $batch --batch-size 23 --skip-existing \
    > .calibration/runs/batch_${batch}.log 2>&1 &
done
wait
echo "All batches complete"
```

### Option C: Claude Code Agent Per Repo (Maximum Parallelism)

For each repo, spawn a Claude Code agent:

```bash
# Generate commands
python -c "
import json
repos = json.load(open('.calibration/repos_found.json'))
for r in repos:
    slug = f\"{r['owner']['login']}/{r['name']}\"
    print(f'claude --dangerously-skip-permissions --model sonnet -p \"cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine && GITHUB_TOKEN=<token> .venv/bin/python examples/batch_calibrate.py {slug} --skip-existing\" &')
"
```

**Warning:** Running all 120 simultaneously will exhaust API rate limits.
Recommend max 4-6 parallel agents at a time.

---

## Rate Limit Management

GitHub API: 5,000 requests/hour per token.

| Repos in parallel | Requests/repo | Time to exhaust | Recommendation |
|-------------------|---------------|-----------------|----------------|
| 1 | ~55 | Never | Safe but slow |
| 4 | ~220 | ~22 hours | Safe |
| 8 | ~440 | ~11 hours | Safe |
| 12 | ~660 | ~7.5 hours | Monitor |
| 20+ | ~1100+ | < 5 hours | Risk hitting limit |

**Mitigation:** The `GitHubClient` has built-in rate limit detection and backoff.
If `remaining < 50`, it waits until the reset window.

### LLM Rate Limits (Phase 3.1 / Phase 4b)

Both LLM clients (`OpenRouterClient`, `AnthropicClient`) have built-in resilience:
- **Retry with exponential backoff** (3 attempts, 2s base delay)
- **429 rate limit handling** with `Retry-After` header support
- **Adaptive pacing** — increases delay between requests on repeated errors
- **Graceful fallback** — if all retries fail, Phase 3.1 falls back to template text,
  Phase 4b stores pattern without semantic description

No LLM failure will crash the pipeline. LLM enhancement is safe to leave enabled.

---

## What Each Calibration Produces

Per repo (stored in `.calibration/runs/<repo>/`):

```
.calibration/runs/<repo>/
├── events/                    # Phase 1: Raw events (JSON per event)
├── index/                     # Phase 1: Deduplication index
├── api_cache/                 # GitHub API response cache
├── phase2/                    # Phase 2: Signal files per family
│   ├── git_signals.json
│   ├── ci_signals.json
│   ├── dependency_signals.json
│   └── ...
├── phase3/                    # Phase 3: Explanations
│   └── explanations.json
├── phase4/                    # Phase 4: Patterns + Knowledge Base
│   ├── phase4_summary.json
│   └── knowledge.db
├── phase5/                    # Phase 5: Advisory outputs
│   ├── advisory.json
│   ├── summary.txt
│   ├── chat.txt
│   └── investigation_prompt.txt
└── calibration_result.json    # Overall calibration metrics
```

---

## Collecting Results

After all batches complete, aggregate results:

```python
import json
from pathlib import Path

runs_dir = Path(".calibration/runs")
all_results = []
for result_file in runs_dir.glob("*/calibration_result.json"):
    with open(result_file) as f:
        all_results.append(json.load(f))

# Summary
total_patterns = sum(
    r.get("phase4", {}).get("patterns_discovered", 0)
    for r in all_results if "error" not in r
)
successful = [r for r in all_results if "error" not in r and r.get("events", 0) > 0]
families_seen = set()
for r in successful:
    families_seen.update(r.get("families", []))

print(f"Repos calibrated: {len(successful)}")
print(f"Total patterns:   {total_patterns}")
print(f"Families covered: {families_seen}")
for r in sorted(successful, key=lambda x: x.get("phase4", {}).get("patterns_discovered", 0), reverse=True):
    p = r.get("phase4", {}).get("patterns_discovered", 0)
    if p > 0:
        print(f"  {r['scope']:40s} {p} patterns, {len(r.get('families', []))} families")
```

---

## Expected Outcomes

Based on the 120 repo list:

| Category | Count | Families Expected | Pattern Potential |
|----------|-------|-------------------|-------------------|
| Go projects (with go.sum) | ~15 | git + dep + ci + deploy | High (transitive deps vary) |
| Python projects (with requirements.txt) | ~20 | git + dep + ci + deploy | Medium (direct deps only) |
| JavaScript/TypeScript (with package-lock.json) | ~25 | git + dep + ci + deploy | High (deep dep trees) |
| Java (with maven/gradle) | ~10 | git + ci + deploy | Medium (walker doesn't parse Maven/Gradle yet) |
| Ruby (with Gemfile.lock) | ~8 | git + dep + ci + deploy | High (direct+transitive) |
| Rust (with Cargo.lock) | ~10 | git + dep + ci + deploy | High (deep dep trees) |
| C/C++ projects | ~10 | git + ci + deploy | Low (no dependency lockfile) |
| Documentation/list repos | ~28 | SKIPPED | None |

**Target:** 10+ validated cross-family patterns from 5+ languages.

---

## Skipped Repos (28)

Documentation-only, awesome-lists, and algorithm collections are skipped automatically.
See `SKIP_REPOS` set in `examples/batch_calibrate.py`.

---

## Post-Calibration Tasks

1. **Aggregate patterns** — Merge all `phase4_summary.json` files
2. **Classify patterns** — Generalizable vs local-only vs false positive
3. **Tune parameters** — Compare conservative/moderate/aggressive profiles
4. **Seed KB** — Promote validated patterns to global knowledge
5. **Build Report Generator** — HTML/PDF from best calibrated repo
6. **Sample report** — Use richest-patterned repo for marketing
