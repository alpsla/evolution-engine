# Phase 3 Repository Search & Validation

> **Operator Manual for Finding Multi-Family Calibration Repos**
>
> This document provides step-by-step `gh api` commands to validate candidate repositories
> for Evolution Engine calibration. Each validation checks for historical multi-family data
> availability across all 8 source families.
>
> **Audience:** AI assistant (Sonnet 4.5 or equivalent) or human operator
>
> **Goal:** Find 8 repos with 4+ family coverage, extract exact lockfile paths for Git History Walker

---

## 1. Prerequisites

### 1.1 Required Tools

```bash
# Install GitHub CLI if not present
brew install gh

# Authenticate
gh auth login

# Verify API access
gh api /user
```

### 1.2 Workspace Setup

```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine/.calibration
mkdir -p repo_candidates
touch repo_validation.md
```

---

## 2. Candidate Repository List

### 2.1 Selection Criteria

**Must have:**
- 500+ commits (stable baselines)
- Active CI/CD (GitHub Actions)
- Dependency management (lockfiles in git history)
- Public repository (API accessible)

**Bonus (for 4+ family coverage):**
- OpenAPI/schema files tracked in git
- Terraform/IaC configuration
- GitHub Releases (deployment tracking)
- Security advisories or Dependabot alerts

### 2.2 Initial 8 Candidates

| # | Repository | Language | Expected Families | Why Selected |
|---|-----------|----------|------------------|--------------|
| 1 | `fastapi/fastapi` | Python | Git, CI, Deps, Testing, Schema | REST framework with OpenAPI |
| 2 | `gin-gonic/gin` | Go | Git, CI, Deps, Testing | Popular Go web framework |
| 3 | `strapi/strapi` | TypeScript | Git, CI, Deps, Testing, Schema | CMS with API generation |
| 4 | `hashicorp/terraform` | Go | Git, CI, Deps, Config | Infrastructure-as-code reference |
| 5 | `kubernetes/kubernetes` | Go | Git, CI, Deps, Security, Deployment | Large-scale production system |
| 6 | `rails/rails` | Ruby | Git, CI, Deps, Testing, Schema | Mature MVC framework |
| 7 | `spring-projects/spring-boot` | Java | Git, CI, Deps, Testing | Enterprise Java framework |
| 8 | `nextjs/next.js` | TypeScript | Git, CI, Deps, Testing, Deployment | Modern web framework |

---

## 3. Validation Procedure (Per Repository)

For each candidate, run these checks in order. Record results in `.calibration/repo_validation.md`.

### 3.1 Basic Repository Info

```bash
OWNER="fastapi"
REPO="fastapi"

# Repository metadata
gh api repos/$OWNER/$REPO --jq '{
  full_name: .full_name,
  language: .language,
  stars: .stargazers_count,
  forks: .forks_count,
  size_kb: .size,
  default_branch: .default_branch,
  created_at: .created_at,
  updated_at: .updated_at,
  has_issues: .has_issues,
  has_wiki: .has_wiki,
  archived: .archived
}'
```

**Acceptance criteria:**
- ✅ Not archived
- ✅ Updated within last 6 months
- ✅ 1000+ stars (active community)

---

### 3.2 Commit Count (Git Family)

```bash
# Get total commit count on default branch
gh api repos/$OWNER/$REPO/commits --paginate \
  --jq 'length' | awk '{s+=$1} END {print s}'

# Alternative: use search API for exact count
gh api search/commits?q=repo:$OWNER/$REPO \
  --jq '.total_count'

# Get recent commits to verify activity
gh api repos/$OWNER/$REPO/commits?per_page=5 \
  --jq '.[] | {sha: .sha[:7], date: .commit.committer.date, message: .commit.message | split("\n")[0]}'
```

**Acceptance criteria:**
- ✅ 500+ commits (minimum for stable baselines)
- ✅ Recent activity (commits within last month)

**Record:**
- Total commits: `_______`
- Last commit date: `_______`

---

### 3.3 CI/CD Coverage (CI Family)

```bash
# List GitHub Actions workflows
gh api repos/$OWNER/$REPO/actions/workflows \
  --jq '.workflows[] | {id: .id, name: .name, path: .path, state: .state}'

# Count total workflow runs (historical CI data)
gh api repos/$OWNER/$REPO/actions/runs?per_page=1 \
  --jq '.total_count'

# Get recent workflow runs with status
gh api repos/$OWNER/$REPO/actions/runs?per_page=10 \
  --jq '.workflow_runs[] | {
    id: .id,
    name: .name,
    status: .status,
    conclusion: .conclusion,
    created_at: .created_at,
    run_number: .run_number
  }'

# Check specific workflow run count (e.g., main CI workflow)
WORKFLOW_ID=$(gh api repos/$OWNER/$REPO/actions/workflows --jq '.workflows[0].id')
gh api repos/$OWNER/$REPO/actions/workflows/$WORKFLOW_ID/runs?per_page=1 \
  --jq '.total_count'
```

**Acceptance criteria:**
- ✅ At least 1 active workflow
- ✅ 100+ historical workflow runs
- ✅ Runs linked to commits (for correlation analysis)

**Record:**
- Workflow count: `_______`
- Total CI runs: `_______`
- Primary workflow: `_______` (name)

---

### 3.4 Dependency Management (Dependency Family)

**Critical:** Find exact lockfile paths for Git History Walker configuration.

```bash
# Clone repo shallow to inspect file structure
cd .calibration/repo_candidates
git clone --depth 50 https://github.com/$OWNER/$REPO.git
cd $REPO

# Python: requirements.txt, Pipfile.lock, poetry.lock, pyproject.toml
find . -maxdepth 3 -name "requirements*.txt" -o -name "Pipfile.lock" -o -name "poetry.lock" -o -name "pyproject.toml"

# JavaScript/TypeScript: package-lock.json, yarn.lock, pnpm-lock.yaml
find . -maxdepth 3 -name "package-lock.json" -o -name "yarn.lock" -o -name "pnpm-lock.yaml"

# Go: go.mod, go.sum
find . -maxdepth 3 -name "go.mod" -o -name "go.sum"

# Ruby: Gemfile.lock
find . -maxdepth 3 -name "Gemfile.lock"

# Java: pom.xml, build.gradle, build.gradle.kts
find . -maxdepth 3 -name "pom.xml" -o -name "build.gradle*"

# Rust: Cargo.lock
find . -maxdepth 3 -name "Cargo.lock"

# Check if lockfile exists in git history (critical for historical tracking)
LOCKFILE="requirements.txt"  # Change per ecosystem
git log --all --oneline --follow -- $LOCKFILE | wc -l
```

**Acceptance criteria:**
- ✅ At least one lockfile present
- ✅ Lockfile has 20+ commits in git history (dependency evolution tracking)

**Record:**
- Lockfile path(s): `_______`
- Lockfile commits: `_______`
- Ecosystem: `_______` (pip, npm, go modules, etc.)

**Output for Git History Walker config:**
```json
{
  "repo": "$OWNER/$REPO",
  "lockfiles": [
    {
      "path": "requirements.txt",
      "type": "pip",
      "commits_tracked": 150
    }
  ]
}
```

---

### 3.5 Testing Coverage (Testing Family)

```bash
# Look for test directories
find . -type d -name "tests" -o -name "test" -o -name "__tests__" -o -name "spec" | head -5

# Count test files
find . -name "*test*.py" -o -name "*_test.go" -o -name "*.test.ts" -o -name "*.spec.ts" | wc -l

# Check for test configuration files
ls pytest.ini pyproject.toml jest.config.js vitest.config.ts go.mod .rspec 2>/dev/null

# Look for CI test artifacts (JUnit XML reports in workflow runs)
# Note: This requires downloading workflow run artifacts, which may need authenticated access
gh api repos/$OWNER/$REPO/actions/runs?per_page=5 \
  --jq '.workflow_runs[] | {id: .id, name: .name, artifacts_url: .artifacts_url}'
```

**Acceptance criteria:**
- ✅ Test directory exists
- ✅ 50+ test files
- ✅ Test configuration present (pytest.ini, jest.config, etc.)

**Record:**
- Test file count: `_______`
- Test framework: `_______`
- CI test integration: `_______` (yes/no)

---

### 3.6 Schema/API Tracking (Schema Family)

```bash
# OpenAPI/Swagger specs
find . -name "openapi*.json" -o -name "openapi*.yaml" -o -name "swagger*.json" -o -name "swagger*.yaml"

# GraphQL schemas
find . -name "schema.graphql" -o -name "*.graphql"

# Database schemas/migrations
find . -type d -name "migrations" -o -name "migrate" | head -5
find . -name "*migration*.sql" -o -name "schema.sql" | head -10

# API documentation
find . -name "api.md" -o -path "*/docs/api/*" -o -path "*/openapi/*" | head -5

# Check if schema files have git history
SCHEMA_FILE=$(find . -name "openapi*.json" | head -1)
if [ -n "$SCHEMA_FILE" ]; then
  git log --oneline --follow -- $SCHEMA_FILE | wc -l
fi
```

**Acceptance criteria:**
- ✅ At least one schema file (OpenAPI, GraphQL, or migrations)
- ✅ Schema file has 10+ commits in git history (API evolution tracking)

**Record:**
- Schema type: `_______` (OpenAPI/GraphQL/DB migrations)
- Schema file path: `_______`
- Schema commits: `_______`

---

### 3.7 Deployment Tracking (Deployment Family)

```bash
# GitHub Releases
gh api repos/$OWNER/$REPO/releases?per_page=1 \
  --jq '.total_count // 0'

gh api repos/$OWNER/$REPO/releases?per_page=10 \
  --jq '.[] | {tag: .tag_name, name: .name, published_at: .published_at, prerelease: .prerelease}'

# Tags (alternative deployment markers)
gh api repos/$OWNER/$REPO/tags?per_page=1 \
  --jq 'length'

# Deployment workflows (GitHub Environments)
gh api repos/$OWNER/$REPO/environments \
  --jq '.environments[] | {name: .name, url: .url}'

# Container registry (Docker images)
gh api users/$OWNER/packages?package_type=container \
  --jq '.[] | select(.name == "'$REPO'") | {name: .name, visibility: .visibility, created_at: .created_at}'
```

**Acceptance criteria:**
- ✅ 10+ releases OR 50+ tags
- ✅ Regular release cadence (not all at once)

**Record:**
- Releases: `_______`
- Latest release: `_______`
- Deployment environments: `_______`

---

### 3.8 Configuration Management (Config Family)

```bash
# Terraform files
find . -name "*.tf" -o -name "*.tfvars" | head -10

# Kubernetes manifests
find . -name "*.yaml" -path "*/k8s/*" -o -path "*/kubernetes/*" | head -10

# Docker configuration
find . -name "Dockerfile*" -o -name "docker-compose*.yml"

# Environment configuration
find . -name ".env*" -o -name "config.yaml" -o -name "config.json" | grep -v node_modules | head -10

# Check if config files have git history
TERRAFORM_FILE=$(find . -name "*.tf" | head -1)
if [ -n "$TERRAFORM_FILE" ]; then
  git log --oneline --follow -- $TERRAFORM_FILE | wc -l
fi
```

**Acceptance criteria:**
- ✅ At least one IaC file (Terraform, Kubernetes, Docker)
- ✅ Config file has 5+ commits in git history

**Record:**
- Config type: `_______` (Terraform/K8s/Docker)
- Config file path: `_______`
- Config commits: `_______`

---

### 3.9 Security Tracking (Security Family)

```bash
# Public security advisories
gh api repos/$OWNER/$REPO/security-advisories \
  --jq '.[] | {ghsa_id: .ghsa_id, summary: .summary, severity: .severity, published_at: .published_at}'

# Dependabot alerts (requires repo admin or security access)
gh api repos/$OWNER/$REPO/dependabot/alerts?per_page=10 \
  --jq '.[] | {number: .number, state: .state, severity: .security_advisory.severity, package: .security_advisory.package.name}'

# Code scanning alerts (if enabled)
gh api repos/$OWNER/$REPO/code-scanning/alerts?per_page=10 \
  --jq '.[] | {number: .number, state: .state, rule: .rule.description, created_at: .created_at}'

# Check for security policy
gh api repos/$OWNER/$REPO/contents/SECURITY.md --jq '.download_url' 2>/dev/null

# Check for .github/workflows with security scanning
grep -r "trivy\|snyk\|security" .github/workflows/*.yml 2>/dev/null
```

**Acceptance criteria:**
- ✅ Security advisories OR Dependabot enabled OR code scanning enabled
- ⚠️ Note: Some security data requires elevated permissions

**Record:**
- Security advisories: `_______`
- Dependabot alerts: `_______`
- Code scanning: `_______` (enabled/disabled)

---

## 4. Output Template

For each validated repository, create an entry in `.calibration/repo_validation.md`:

```markdown
## Repository: $OWNER/$REPO

**Language:** [Python/Go/TypeScript/etc.]
**Stars:** [count]
**Commits:** [count]
**Last updated:** [date]

### Family Coverage Matrix

| Family | Available | Data Source | Quantity | File Paths |
|--------|-----------|-------------|----------|-----------|
| ✅ Git | Yes | Git history | 1,234 commits | — |
| ✅ CI/Build | Yes | GitHub Actions API | 567 runs | — |
| ✅ Dependencies | Yes | Git history | 89 commits | `requirements.txt` |
| ✅ Testing | Yes | Local pytest run | 234 tests | `tests/` |
| ✅ Schema/API | Yes | Git history | 45 commits | `docs/openapi.json` |
| ⚠️ Deployment | Partial | GitHub Releases | 12 releases | — |
| ⚠️ Config | Partial | Git history | 8 commits | `Dockerfile` |
| ❌ Security | No | — | — | — |

**Total families: 5 / 8**

### Git History Walker Config

```json
{
  "repo_path": ".calibration/repos/$REPO",
  "tracked_files": [
    {
      "path": "requirements.txt",
      "family": "dependency",
      "parser": "pip",
      "commits": 89
    },
    {
      "path": "docs/openapi.json",
      "family": "schema",
      "parser": "openapi",
      "commits": 45
    },
    {
      "path": "Dockerfile",
      "family": "config",
      "parser": "dockerfile",
      "commits": 8
    }
  ]
}
```

### Calibration Priority

**Priority:** [High/Medium/Low]

**Rationale:** [Why this repo is a good/poor calibration candidate]

**Recommended parameters:**
- `min_baseline`: [10/20/50 based on commit count]
- `min_support`: [5/10 based on expected pattern density]
- `min_correlation`: [0.5 standard]

---
```

---

## 5. Automated Validation Script

Run all checks for a single repository:

```bash
#!/bin/bash
# validate_repo.sh

OWNER=$1
REPO=$2

if [ -z "$OWNER" ] || [ -z "$REPO" ]; then
  echo "Usage: ./validate_repo.sh OWNER REPO"
  exit 1
fi

echo "=== Validating $OWNER/$REPO ==="

# 1. Basic info
echo "## Basic Info"
gh api repos/$OWNER/$REPO --jq '{language: .language, stars: .stargazers_count, archived: .archived, updated: .updated_at}'

# 2. Commit count
echo -e "\n## Commits"
COMMIT_COUNT=$(gh api "search/commits?q=repo:$OWNER/$REPO" --jq '.total_count' 2>/dev/null || echo "N/A")
echo "Total commits: $COMMIT_COUNT"

# 3. CI runs
echo -e "\n## CI/CD"
CI_COUNT=$(gh api repos/$OWNER/$REPO/actions/runs?per_page=1 --jq '.total_count' 2>/dev/null || echo "0")
echo "Total CI runs: $CI_COUNT"

# 4. Releases
echo -e "\n## Releases"
RELEASE_COUNT=$(gh api repos/$OWNER/$REPO/releases --paginate --jq 'length' 2>/dev/null || echo "0")
echo "Total releases: $RELEASE_COUNT"

# 5. Clone and inspect
echo -e "\n## File Inspection"
cd .calibration/repo_candidates
if [ ! -d "$REPO" ]; then
  git clone --depth 50 https://github.com/$OWNER/$REPO.git 2>/dev/null
fi
cd $REPO

echo "Lockfiles:"
find . -maxdepth 3 \( -name "requirements*.txt" -o -name "package-lock.json" -o -name "go.mod" -o -name "Gemfile.lock" -o -name "Cargo.lock" \)

echo -e "\nSchema files:"
find . -maxdepth 4 \( -name "openapi*.json" -o -name "openapi*.yaml" -o -name "schema.graphql" \)

echo -e "\nConfig files:"
find . -maxdepth 3 \( -name "*.tf" -o -name "Dockerfile*" -o -name "*docker-compose*.yml" \)

cd ../..
echo -e "\n=== Validation complete ==="
```

**Usage:**
```bash
chmod +x validate_repo.sh
./validate_repo.sh fastapi fastapi >> repo_validation.md
./validate_repo.sh gin-gonic gin >> repo_validation.md
./validate_repo.sh strapi strapi >> repo_validation.md
# ... etc
```

---

## 6. Selection Criteria Summary

After validating all 8 candidates, rank them:

| Rank | Repository | Families | Score | Notes |
|------|-----------|----------|-------|-------|
| 1 | `$OWNER/$REPO` | 6/8 | ⭐⭐⭐⭐⭐ | All major families covered |
| 2 | `$OWNER/$REPO` | 5/8 | ⭐⭐⭐⭐ | Missing security, good coverage otherwise |
| 3 | `$OWNER/$REPO` | 4/8 | ⭐⭐⭐ | Git + CI + Deps + Testing |
| ... | ... | ... | ... | ... |

**Minimum acceptance:** 4/8 families with at least:
- ✅ Git (500+ commits)
- ✅ CI (100+ runs)
- ✅ Dependencies (lockfile with 20+ commits)
- ✅ One of: Testing, Schema, Deployment, Config, Security

---

## 7. Next Steps

After validation:

1. **Select top 5 repos** with best family coverage
2. **Clone with deeper history:**
   ```bash
   git clone --depth 500 https://github.com/$OWNER/$REPO.git
   ```
3. **Configure Git History Walker** with exact lockfile paths
4. **Run full calibration pipeline** (see `CALIBRATION_GUIDE.md`)
5. **Document patterns discovered** in `.calibration/reports/`

---

## 8. Quick Reference Commands

```bash
# Check if repo is a good candidate (one-liner)
gh api repos/$OWNER/$REPO --jq '{lang: .language, stars: .stargazers_count, archived: .archived}' && \
gh api "search/commits?q=repo:$OWNER/$REPO" --jq '{commits: .total_count}' && \
gh api repos/$OWNER/$REPO/actions/runs?per_page=1 --jq '{ci_runs: .total_count}'

# Find lockfile commit count
cd .calibration/repo_candidates/$REPO
git log --oneline --follow -- requirements.txt | wc -l

# List all workflows
gh api repos/$OWNER/$REPO/actions/workflows --jq '.workflows[].name'

# Get last 5 releases
gh api repos/$OWNER/$REPO/releases?per_page=5 --jq '.[].tag_name'
```

---

## 9. Troubleshooting

| Issue | Solution |
|-------|----------|
| `gh api` returns 404 | Check repo name, ensure it's public |
| "Resource not accessible by integration" | Some security endpoints require repo admin access |
| Commit count search fails | Use `gh api repos/$OWNER/$REPO/commits --paginate` instead |
| Clone fails | Check network, repo size, or use `--depth` flag |
| No lockfile found | Repo may use different dependency management (check docs) |

---

**End of validation guide. For calibration procedure, see `CALIBRATION_GUIDE.md`.**
