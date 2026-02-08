# Repository Search Agent — Usage Guide

**Automated discovery and ranking of repositories with multi-family data coverage**

---

## What It Does

The Search Agent **automatically**:

1. **Searches GitHub** for 100+ repositories matching your criteria
2. **Validates each repo** across all 8 source families
3. **Scores and ranks** by multi-family data availability
4. **Exports results** to CSV with all metrics

---

## Quick Start

```bash
cd .calibration

# Search with defaults (1000+ stars, 200 repos max)
python search_agent.py

# Custom search (500+ stars, 500 repos max)
python search_agent.py --min-stars 500 --max-repos 500

# Specific languages only
python search_agent.py --languages Python Go TypeScript

# Custom output file
python search_agent.py --output my_results.csv
```

**Output:** `repos_ranked.csv` with 100+ validated repositories ranked by calibration score

---

## Search Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--min-stars` | 1000 | Minimum GitHub stars (quality filter) |
| `--max-repos` | 200 | Maximum repositories to search |
| `--languages` | Python, Go, TS, JS, Java, Ruby | Languages to search |
| `--output` | repos_ranked.csv | Output CSV filename |

### Examples

```bash
# High-quality only (10k+ stars)
python search_agent.py --min-stars 10000

# Large search (500 repos)
python search_agent.py --max-repos 500

# Python and Go only
python search_agent.py --languages Python Go

# All parameters
python search_agent.py \
  --min-stars 500 \
  --max-repos 300 \
  --languages Python TypeScript \
  --output python_ts_repos.csv
```

---

## How It Works

### 1. GitHub Search (1-5 minutes)

Uses `gh search repos` to find repositories matching:
- Language (Python, Go, TypeScript, etc.)
- Minimum stars (quality proxy)
- Not archived
- Sorted by popularity

**Example:** 
```
Searching Python repositories (stars>=1000)...
  Found 35 Python repositories
Searching Go repositories (stars>=1000)...
  Found 28 Go repositories
...
Total repositories found: 150
```

### 2. Validation (20-60 minutes for 200 repos)

For each repository, validates:

| Family | Check | Criteria |
|--------|-------|----------|
| ✅ Git | Commit count | 500+ commits |
| ✅ CI/Build | GitHub Actions runs | 100+ runs |
| ✅ Dependencies | Lockfile in git history | 20+ commits |
| ✅ Testing | Test file count | 50+ test files |
| ✅ Schema/API | OpenAPI/GraphQL in git | 10+ commits |
| ✅ Deployment | GitHub Releases | 10+ releases |
| ✅ Config | Terraform/Docker in git | 5+ commits |
| ⚠️ Security | Dependabot (limited API) | Partial |

**Progress output:**
```
[1/150] Validating fastapi/fastapi (Python)...
  ✅ fastapi/fastapi: 6/8 families, score=87.5

[2/150] Validating gin-gonic/gin (Go)...
  ✅ gin-gonic/gin: 5/8 families, score=72.3

⏸️  Pausing 5 seconds (processed 10/150)...
```

### 3. Scoring

Each repository gets a **calibration score (0-100)**:

- **Family coverage:** 10 points per family (max 80)
- **Commit bonus:** Up to 10 points (1000+ commits = full bonus)
- **Lockfile history:** Up to 5 points (deep history = better)
- **CI runs:** Up to 5 points (100+ runs = full bonus)

**Examples:**
- 6 families, 1200 commits, 150 CI runs, 40 lockfile commits = **91 points**
- 4 families, 600 commits, 50 CI runs, 10 lockfile commits = **57 points**

### 4. Export

Results exported to CSV sorted by score (highest first):

```csv
rank,owner,repo,language,stars,commits,family_count,calibration_score,has_git,has_ci,...
1,fastapi,fastapi,Python,75234,6713,6,91.5,True,True,True,True,True,True,False,False,...
2,gin-gonic,gin,Go,72451,3892,5,78.2,True,True,True,True,False,True,True,False,...
...
```

---

## Output Format

### CSV Columns

**Basic Info:**
- `rank` — Ranking by calibration score
- `owner` — Repository owner
- `repo` — Repository name
- `language` — Primary language
- `stars` — GitHub stars
- `commits` — Total commits
- `family_count` — Number of families available (0-8)
- `calibration_score` — Suitability score (0-100)

**Family Availability (True/False):**
- `has_git`, `has_ci`, `has_dependencies`, `has_testing`
- `has_schema`, `has_deployment`, `has_config`, `has_security`

**Family Metrics:**
- `ci_runs` — Total CI workflow runs
- `releases` — Total releases
- `test_files` — Number of test files
- `lockfile_path` — Path to dependency lockfile
- `lockfile_commits` — Commits in lockfile history
- `schema_path` — Path to schema file (OpenAPI, GraphQL)
- `schema_commits` — Commits in schema history
- `config_path` — Path to config file (Terraform, Docker)
- `config_commits` — Commits in config history

### Summary Statistics

After completion, prints:

```
==============================================================
📊 SUMMARY
==============================================================
Total validated repositories: 127
Average family coverage: 4.8/8
Repos with 6+ families: 23
Repos with 4+ families: 89

🏆 Top 10 Repositories:
--------------------------------------------------------------
 1. fastapi/fastapi                (Python      ) 6/8 families score=91.5
 2. gin-gonic/gin                  (Go          ) 5/8 families score=78.2
 3. strapi/strapi                  (TypeScript  ) 6/8 families score=85.7
...
==============================================================
```

---

## Runtime Estimates

| Repos Searched | Expected Time | Validated (~60%) |
|---------------|---------------|------------------|
| 50 | 10-15 minutes | ~30 repos |
| 100 | 20-30 minutes | ~60 repos |
| 200 | 40-60 minutes | ~120 repos |
| 500 | 2-3 hours | ~300 repos |

**Rate limiting:** Pauses every 10 repos (5 seconds) to avoid GitHub API limits.

---

## Prerequisites

1. **GitHub CLI installed:**
   ```bash
   brew install gh
   ```

2. **GitHub CLI authenticated:**
   ```bash
   gh auth login
   ```

3. **Python 3.8+:**
   ```bash
   python3 --version
   ```

4. **Disk space:** ~50MB for temporary repo clones

---

## Workflow Integration

### 1. Discovery (This Tool)

```bash
# Find 200+ repos with multi-family data
python search_agent.py --max-repos 300 --output repos_ranked.csv
```

### 2. Selection

```python
# Filter top repos by score
import pandas as pd
df = pd.read_csv('repos_ranked.csv')

# Get top 10 with 6+ families
top10 = df[(df['family_count'] >= 6)].head(10)
print(top10[['owner', 'repo', 'family_count', 'calibration_score']])
```

### 3. Calibration

```bash
# Run full pipeline on selected repos
for repo in $(cat top_repos.txt); do
  python .calibration/run_calibration.py --repo $repo
done
```

### 4. Pattern Discovery

Review Phase 4 outputs from multi-family runs:

```bash
# See discovered patterns
python -c "
from evolution.knowledge_store import SQLiteKnowledgeStore
from pathlib import Path

kb = SQLiteKnowledgeStore(Path('.calibration/runs/REPO/phase4/knowledge.db'))
for p in kb.list_patterns()[:20]:
    print(f'{p['sources']} — {p['metrics']} (corr={p.get('correlation_strength', 0):.2f})')
kb.close()
"
```

---

## Troubleshooting

### "GitHub CLI not authenticated"

```bash
gh auth login
# Follow prompts
```

### "No repositories found"

- Lower `--min-stars` threshold
- Add more `--languages`
- Check network connection

### "Validation too slow"

- Reduce `--max-repos`
- Use `--min-stars 5000` (higher quality, fewer repos)
- Run in background: `nohup python search_agent.py &`

### "Rate limit exceeded"

Wait 1 hour or:
- Run with fewer repos
- Increase pause intervals in code

### "Clone failed"

Some repos may be too large or have restrictions. The agent will skip these automatically.

---

## Advanced Usage

### Custom Filtering

Edit `search_agent.py` to add custom filters:

```python
# In validate_repository(), add:
if candidate.stars < 5000:
    return None  # Skip low-star repos

if candidate.forks < 100:
    return None  # Skip low-fork repos
```

### Language-Specific Searches

```bash
# Python data science repos
python search_agent.py \
  --languages Python \
  --min-stars 2000 \
  --output python_ds_repos.csv

# Infrastructure repos (Go, Terraform)
python search_agent.py \
  --languages Go \
  --min-stars 1000 \
  --output infra_repos.csv
```

### Re-ranking Results

```python
import pandas as pd

df = pd.read_csv('repos_ranked.csv')

# Custom scoring: prioritize CI + dependencies
df['custom_score'] = (
    df['family_count'] * 10 +
    df['ci_runs'] / 10 +
    df['lockfile_commits'] * 2
)

df_sorted = df.sort_values('custom_score', ascending=False)
df_sorted.to_csv('repos_custom_ranked.csv', index=False)
```

---

## What's Next

After running the search agent:

1. **Review `repos_ranked.csv`** — Check top 20-50 repos

2. **Select calibration candidates** — Pick 5-10 with highest scores

3. **Clone top repos:**
   ```bash
   mkdir -p .calibration/repos
   cd .calibration/repos
   git clone --depth 500 https://github.com/OWNER/REPO.git
   ```

4. **Run calibration pipeline:**
   ```bash
   python .calibration/run_calibration.py --repo REPO_NAME
   ```

5. **Discover patterns** — Review Phase 4 outputs

6. **Build seed KB** — Compile validated patterns into `seed_patterns.json`

---

## Comparison: Manual vs Automated

| Approach | Time | Coverage | Effort |
|----------|------|----------|--------|
| **Manual** (P3_REPO_SEARCH.md) | 4-6 hours | 8 repos | High (per-repo commands) |
| **Automated** (search_agent.py) | 30-60 min | 100+ repos | Low (one command) |

**Recommendation:** Use automated search to find 100+ candidates, then manually deep-dive on top 10.

---

## Example Run

```bash
$ python search_agent.py --min-stars 1000 --max-repos 100

🚀 Starting Repository Search Agent
==============================================================
✅ GitHub CLI authenticated
🔍 Searching GitHub for candidate repositories...
Searching Python repositories (stars>=1000)...
  Found 18 Python repositories
Searching Go repositories (stars>=1000)...
  Found 15 Go repositories
Searching TypeScript repositories (stars>=1000)...
  Found 21 TypeScript repositories
...
✅ Total repositories found: 95

==============================================================
🔬 Validating 95 repositories across 8 families...
==============================================================

[1/95] Validating fastapi/fastapi (Python)...
  ✅ fastapi/fastapi: 6/8 families, score=91.5

[2/95] Validating gin-gonic/gin (Go)...
  ✅ gin-gonic/gin: 5/8 families, score=78.2

...

[10/95] Validating strapi/strapi (TypeScript)...
  ✅ strapi/strapi: 6/8 families, score=85.7

⏸️  Pausing 5 seconds (processed 10/95)...

...

==============================================================
✅ Validation complete: 67/95 repositories passed
==============================================================

💾 Exporting results to repos_ranked.csv...
✅ Exported 67 repositories

==============================================================
📊 SUMMARY
==============================================================
Total validated repositories: 67
Average family coverage: 4.9/8
Repos with 6+ families: 15
Repos with 4+ families: 52

🏆 Top 10 Repositories:
--------------------------------------------------------------
 1. fastapi/fastapi                (Python      ) 6/8 families score=91.5
 2. strapi/strapi                  (TypeScript  ) 6/8 families score=85.7
 3. gin-gonic/gin                  (Go          ) 5/8 families score=78.2
 4. spring-projects/spring-boot    (Java        ) 5/8 families score=76.8
 5. rails/rails                    (Ruby        ) 6/8 families score=88.3
 6. vercel/next.js                 (TypeScript  ) 5/8 families score=74.5
 7. kubernetes/kubernetes          (Go          ) 7/8 families score=95.2
 8. hashicorp/terraform            (Go          ) 5/8 families score=72.1
 9. django/django                  (Python      ) 5/8 families score=70.4
10. nestjs/nest                    (TypeScript  ) 5/8 families score=68.9
==============================================================
```

---

**Now you have 100+ ranked repositories ready for calibration!** 🎉
