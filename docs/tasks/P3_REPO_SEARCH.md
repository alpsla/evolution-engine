# Task: P3 — Calibration Repo Search & Validation

> **For:** Sonnet 4.5 (or equivalent)
> **Effort:** 0.5 day
> **Blocks:** Multi-family calibration runs (P4)
> **Priority:** 3
> **Can run in parallel with:** P1 (Git History Walker) and P2 (GitHub API Adapter)

---

## Goal

Search for, evaluate, and validate 5+ open-source repositories that have rich
multi-family source data available for calibration. For each candidate, verify
which source families are actually accessible and document the findings.

**Output:** A validated calibration target list at `.calibration/repo_validation.md`

---

## Prerequisites

You need the `gh` CLI (GitHub CLI) authenticated, and `git` available.

```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
```

---

## Selection Criteria

Each repo MUST have:
- ✅ 500+ commits (stable baselines for Phase 2)
- ✅ Public GitHub Actions CI (workflow runs accessible via API)
- ✅ At least one lockfile tracked in git history (for dependency family)
- ✅ At least 3 source families extractable

SHOULD have:
- Different programming language (need Python, Go, TypeScript minimum)
- Active development (recent commits)
- GitHub Releases (for deployment family)
- OpenAPI spec or similar schema file in repo (for schema family)
- Terraform or IaC files (for config family)

---

## Candidate Repositories

Start with these candidates (but feel free to add better ones):

| Repository | Language | URL |
|-----------|----------|-----|
| fastapi | Python | `github.com/fastapi/fastapi` |
| gin | Go | `github.com/gin-gonic/gin` |
| next.js | TypeScript | `github.com/vercel/next.js` |
| terraform-provider-aws | Go/HCL | `github.com/hashicorp/terraform-provider-aws` |
| grafana | Go + TS | `github.com/grafana/grafana` |
| kubernetes | Go | `github.com/kubernetes/kubernetes` |
| django | Python | `github.com/django/django` |
| express | JavaScript | `github.com/expressjs/express` |

---

## Validation Process (Per Repo)

For each candidate, run these checks and document the results:

### Check 1: Commit Count
```bash
gh api repos/{owner}/{repo} -q '.size'
gh api repos/{owner}/{repo}/commits?per_page=1 -i 2>&1 | grep -i 'link:'
# Or clone shallow and count:
# git clone --depth 1000 ... && git log --oneline | wc -l
```
**Need:** 500+

### Check 2: GitHub Actions CI (public workflow runs)
```bash
# Check if workflow runs exist and are public
gh api repos/{owner}/{repo}/actions/runs?per_page=5 -q '.total_count'

# Check a sample run for job details
gh api repos/{owner}/{repo}/actions/runs?per_page=1 -q '.workflow_runs[0] | {id, name, conclusion, created_at}'
```
**Need:** total_count > 100, runs include conclusion and timing data

### Check 3: Lockfile in Git History (dependency family)
```bash
# Check if lockfile exists in current HEAD
gh api repos/{owner}/{repo}/contents/requirements.txt 2>/dev/null && echo "HAS requirements.txt"
gh api repos/{owner}/{repo}/contents/go.sum 2>/dev/null && echo "HAS go.sum"
gh api repos/{owner}/{repo}/contents/go.mod 2>/dev/null && echo "HAS go.mod"
gh api repos/{owner}/{repo}/contents/package-lock.json 2>/dev/null && echo "HAS package-lock.json"
gh api repos/{owner}/{repo}/contents/package.json 2>/dev/null && echo "HAS package.json"
gh api repos/{owner}/{repo}/contents/Pipfile.lock 2>/dev/null && echo "HAS Pipfile.lock"
gh api repos/{owner}/{repo}/contents/pyproject.toml 2>/dev/null && echo "HAS pyproject.toml"
gh api repos/{owner}/{repo}/contents/Cargo.lock 2>/dev/null && echo "HAS Cargo.lock"
```
**Need:** At least one lockfile that can be parsed by our adapters

### Check 4: GitHub Releases (deployment family)
```bash
gh api repos/{owner}/{repo}/releases?per_page=5 -q '.[].tag_name'
gh api repos/{owner}/{repo}/releases -q 'length'
```
**Need:** 10+ releases for meaningful deployment signals

### Check 5: OpenAPI / Schema Files (schema family)
```bash
# Search for OpenAPI specs in the repo
gh api "search/code?q=openapi+repo:{owner}/{repo}+extension:json" -q '.total_count'
gh api "search/code?q=openapi+repo:{owner}/{repo}+extension:yaml" -q '.total_count'

# Or check common paths
gh api repos/{owner}/{repo}/contents/docs 2>/dev/null | jq '.[].name' | grep -i "openapi\|swagger\|api"
```
**Need:** At least one spec file tracked in git

### Check 6: Terraform / IaC Files (config family)
```bash
gh api "search/code?q=resource+repo:{owner}/{repo}+extension:tf" -q '.total_count'
```
**Need:** .tf files in repo (only relevant for infra repos)

### Check 7: Security Advisories
```bash
gh api repos/{owner}/{repo}/security-advisories 2>/dev/null | jq 'length'
# Or check Dependabot alerts
gh api repos/{owner}/{repo}/dependabot/alerts?per_page=5 2>/dev/null
```
**Need:** Any security data (nice to have, not required)

---

## Output Format

Create the file `.calibration/repo_validation.md` with this structure:

```markdown
# Calibration Repository Validation

**Date:** YYYY-MM-DD
**Validated by:** [model name]

## Summary

| Repository | Language | Commits | Families Available | Priority |
|-----------|----------|---------|-------------------|----------|
| fastapi | Python | 6713 | Git, Deps, CI, Schema, Releases | 1 |
| ... | ... | ... | ... | ... |

## Detailed Validation

### 1. fastapi (Python)

**URL:** github.com/fastapi/fastapi
**Commits:** 6713
**Already cloned:** Yes (at .calibration/repos/fastapi/)

| Family | Source | Available? | Details |
|--------|--------|-----------|---------|
| Version Control | Git history | ✅ | 6713 commits |
| Dependencies | pyproject.toml in git | ✅ / ❌ | Tracked since commit X |
| CI / Build | GitHub Actions API | ✅ / ❌ | N workflow runs |
| Schema / API | OpenAPI spec in git | ✅ / ❌ | Path: docs/... |
| Deployment | GitHub Releases | ✅ / ❌ | N releases |
| Config | Terraform files | ❌ | N/A — not an infra repo |
| Security | Security advisories | ✅ / ❌ | N advisories |
| Testing | CI test artifacts | ❌ | Not publicly downloadable |

**Lockfile path(s):** `pyproject.toml`, `requirements.txt`
**CI workflow(s):** `.github/workflows/test.yml`, ...
**Schema file(s):** `docs/en/docs/openapi.json` (if exists)
**Notes:** [any issues, concerns, or special considerations]

**Verdict:** ✅ APPROVED for calibration (N families available)

### 2. gin (Go)
[... same format ...]

### 3. next.js (TypeScript)
[... same format ...]

[... etc for each candidate ...]

## Priority Ranking

Based on the validation:

1. **[repo]** — N families, [language], [why first]
2. **[repo]** — N families, [language], [why second]
3. ...

## Repos Rejected

- **[repo]** — rejected because [reason]

## Recommendations

- [Which repos to calibrate first]
- [Which lockfile paths to use for Git History Walker config]
- [Any repos that need special adapter handling]
```

---

## Important Notes

1. **GitHub API rate limits:** Authenticated requests are limited to 5000/hour.
   Use `gh api` which handles auth automatically. If you hit limits, note it and continue.

2. **Don't clone repos** in this task — just validate via the GitHub API.
   Cloning happens during calibration runs (P4).

3. **Focus on data AVAILABILITY, not quality.** We'll assess data quality during
   calibration runs. Here we just need to confirm the data exists and is accessible.

4. **Language diversity matters.** We need at least Python, Go, and TypeScript
   repos to validate that patterns are structural, not language-specific.

5. **Lockfile path is critical.** Document the exact path for each lockfile
   found — the Git History Walker (P1) needs these paths as configuration.

6. **If you find better candidates** than the ones listed above, add them.
   Good candidates: active development, multiple lockfiles, public CI, releases.

---

## Success Criteria

- [ ] 5+ repos validated with detailed family coverage
- [ ] At least 3 languages represented (Python, Go, TypeScript)
- [ ] Each validated repo has 3+ extractable source families
- [ ] Exact lockfile paths documented for Git History Walker configuration
- [ ] Priority ranking based on family coverage and data quality
- [ ] `.calibration/repo_validation.md` created with all findings
