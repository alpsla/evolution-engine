#!/bin/bash
# validate_repo.sh - Automated repository validation for Evolution Engine calibration
# Usage: ./validate_repo.sh OWNER REPO

set -euo pipefail

OWNER=$1
REPO=$2

if [ -z "$OWNER" ] || [ -z "$REPO" ]; then
  echo "Usage: ./validate_repo.sh OWNER REPO"
  echo "Example: ./validate_repo.sh fastapi fastapi"
  exit 1
fi

echo "========================================"
echo "Repository Validation: $OWNER/$REPO"
echo "========================================"
echo ""

# Check if gh is installed
if ! command -v gh &> /dev/null; then
  echo "ERROR: GitHub CLI (gh) is not installed."
  echo "Install with: brew install gh"
  exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
  echo "ERROR: Not authenticated with GitHub CLI."
  echo "Run: gh auth login"
  exit 1
fi

# 1. Basic Repository Info
echo "## 1. Basic Repository Info"
echo "----------------------------"

REPO_INFO=$(gh api repos/$OWNER/$REPO 2>/dev/null || echo "ERROR")

if [ "$REPO_INFO" = "ERROR" ]; then
  echo "❌ Repository not found or not accessible: $OWNER/$REPO"
  exit 1
fi

LANGUAGE=$(echo "$REPO_INFO" | jq -r '.language // "Unknown"')
STARS=$(echo "$REPO_INFO" | jq -r '.stargazers_count')
FORKS=$(echo "$REPO_INFO" | jq -r '.forks_count')
ARCHIVED=$(echo "$REPO_INFO" | jq -r '.archived')
UPDATED=$(echo "$REPO_INFO" | jq -r '.updated_at')
DEFAULT_BRANCH=$(echo "$REPO_INFO" | jq -r '.default_branch')

echo "Language: $LANGUAGE"
echo "Stars: $STARS"
echo "Forks: $FORKS"
echo "Archived: $ARCHIVED"
echo "Last updated: $UPDATED"
echo "Default branch: $DEFAULT_BRANCH"

if [ "$ARCHIVED" = "true" ]; then
  echo "⚠️  WARNING: Repository is archived"
fi

if [ "$STARS" -lt 1000 ]; then
  echo "⚠️  WARNING: Low star count (< 1000) - may not be widely used"
fi

echo ""

# 2. Commit Count
echo "## 2. Commit Count (Git Family)"
echo "-------------------------------"

COMMIT_COUNT=$(gh api "search/commits?q=repo:$OWNER/$REPO" --jq '.total_count' 2>/dev/null || echo "N/A")

if [ "$COMMIT_COUNT" = "N/A" ]; then
  echo "⚠️  Could not retrieve commit count via search API"
  echo "Falling back to paginated commits..."
  COMMIT_COUNT=$(gh api repos/$OWNER/$REPO/commits --paginate --jq 'length' 2>/dev/null | awk '{s+=$1} END {print s}' || echo "N/A")
fi

echo "Total commits: $COMMIT_COUNT"

if [ "$COMMIT_COUNT" != "N/A" ] && [ "$COMMIT_COUNT" -lt 500 ]; then
  echo "⚠️  WARNING: Low commit count (< 500) - baselines may be unstable"
elif [ "$COMMIT_COUNT" != "N/A" ]; then
  echo "✅ Sufficient commit history for stable baselines"
fi

echo ""

# 3. CI/CD Coverage
echo "## 3. CI/CD Coverage (CI Family)"
echo "--------------------------------"

WORKFLOW_COUNT=$(gh api repos/$OWNER/$REPO/actions/workflows --jq '.total_count' 2>/dev/null || echo "0")
CI_RUN_COUNT=$(gh api repos/$OWNER/$REPO/actions/runs?per_page=1 --jq '.total_count' 2>/dev/null || echo "0")

echo "GitHub Actions workflows: $WORKFLOW_COUNT"
echo "Total CI runs: $CI_RUN_COUNT"

if [ "$WORKFLOW_COUNT" -gt 0 ]; then
  echo "✅ CI/CD available via GitHub Actions"
  echo ""
  echo "Workflows:"
  gh api repos/$OWNER/$REPO/actions/workflows --jq '.workflows[] | "  - \(.name) (\(.state))"' 2>/dev/null || echo "  (could not list workflows)"
  
  if [ "$CI_RUN_COUNT" -lt 100 ]; then
    echo "⚠️  WARNING: Low CI run count (< 100) - limited historical data"
  else
    echo "✅ Sufficient CI run history"
  fi
else
  echo "❌ No GitHub Actions workflows found"
fi

echo ""

# 4. Releases (Deployment Family)
echo "## 4. Releases (Deployment Family)"
echo "-----------------------------------"

RELEASE_COUNT=$(gh api repos/$OWNER/$REPO/releases --paginate --jq 'length' 2>/dev/null || echo "0")
TAG_COUNT=$(gh api repos/$OWNER/$REPO/tags --paginate --jq 'length' 2>/dev/null || echo "0")

echo "Releases: $RELEASE_COUNT"
echo "Tags: $TAG_COUNT"

if [ "$RELEASE_COUNT" -gt 10 ]; then
  echo "✅ Sufficient release history for deployment tracking"
  echo ""
  echo "Recent releases:"
  gh api repos/$OWNER/$REPO/releases?per_page=5 --jq '.[] | "  - \(.tag_name) (\(.published_at[:10]))"' 2>/dev/null
elif [ "$TAG_COUNT" -gt 50 ]; then
  echo "✅ Sufficient tag history for deployment tracking"
else
  echo "⚠️  Limited deployment tracking data"
fi

echo ""

# 5. Security (Security Family)
echo "## 5. Security (Security Family)"
echo "--------------------------------"

ADVISORY_COUNT=$(gh api repos/$OWNER/$REPO/security-advisories --jq 'length' 2>/dev/null || echo "0")
echo "Security advisories: $ADVISORY_COUNT"

# Note: Dependabot and code scanning may require special permissions
echo "(Dependabot and code scanning checks require elevated permissions)"

if [ "$ADVISORY_COUNT" -gt 0 ]; then
  echo "✅ Security advisory data available"
else
  echo "⚠️  No public security advisories"
fi

echo ""

# 6. File Inspection (Dependencies, Schema, Config)
echo "## 6. File Inspection"
echo "---------------------"
echo "Cloning repository for file inspection..."

mkdir -p .calibration/repo_candidates
cd .calibration/repo_candidates

if [ -d "$REPO" ]; then
  echo "Repository already cloned, pulling latest..."
  cd "$REPO"
  git pull --quiet 2>/dev/null || echo "  (could not update)"
else
  git clone --depth 50 --quiet https://github.com/$OWNER/$REPO.git 2>/dev/null
  cd "$REPO"
fi

echo ""
echo "### Dependencies (Dependency Family)"
echo "------------------------------------"

LOCKFILES=$(find . -maxdepth 3 \( \
  -name "requirements*.txt" -o \
  -name "Pipfile.lock" -o \
  -name "poetry.lock" -o \
  -name "pyproject.toml" -o \
  -name "package-lock.json" -o \
  -name "yarn.lock" -o \
  -name "pnpm-lock.yaml" -o \
  -name "go.mod" -o \
  -name "go.sum" -o \
  -name "Gemfile.lock" -o \
  -name "Cargo.lock" -o \
  -name "pom.xml" -o \
  -name "build.gradle*" \
\) 2>/dev/null)

if [ -n "$LOCKFILES" ]; then
  echo "✅ Dependency lockfiles found:"
  echo "$LOCKFILES" | while read -r lockfile; do
    COMMITS=$(git log --oneline --follow -- "$lockfile" 2>/dev/null | wc -l | tr -d ' ')
    echo "  - $lockfile ($COMMITS commits)"
  done
else
  echo "❌ No dependency lockfiles found"
fi

echo ""
echo "### Schema/API (Schema Family)"
echo "------------------------------"

SCHEMA_FILES=$(find . -maxdepth 4 \( \
  -name "openapi*.json" -o \
  -name "openapi*.yaml" -o \
  -name "swagger*.json" -o \
  -name "swagger*.yaml" -o \
  -name "schema.graphql" -o \
  -name "*migration*.sql" \
\) 2>/dev/null | head -10)

if [ -n "$SCHEMA_FILES" ]; then
  echo "✅ Schema/API files found:"
  echo "$SCHEMA_FILES" | while read -r schemafile; do
    COMMITS=$(git log --oneline --follow -- "$schemafile" 2>/dev/null | wc -l | tr -d ' ')
    echo "  - $schemafile ($COMMITS commits)"
  done
else
  # Check for migrations directory
  MIGRATIONS_DIR=$(find . -maxdepth 3 -type d -name "migrations" 2>/dev/null | head -1)
  if [ -n "$MIGRATIONS_DIR" ]; then
    echo "✅ Database migrations directory found: $MIGRATIONS_DIR"
  else
    echo "⚠️  No schema/API files found"
  fi
fi

echo ""
echo "### Configuration (Config Family)"
echo "---------------------------------"

CONFIG_FILES=$(find . -maxdepth 3 \( \
  -name "*.tf" -o \
  -name "*.tfvars" -o \
  -name "Dockerfile*" -o \
  -name "*docker-compose*.yml" -o \
  -name "*docker-compose*.yaml" \
\) 2>/dev/null | head -10)

if [ -n "$CONFIG_FILES" ]; then
  echo "✅ Configuration files found:"
  echo "$CONFIG_FILES" | while read -r configfile; do
    COMMITS=$(git log --oneline --follow -- "$configfile" 2>/dev/null | wc -l | tr -d ' ')
    echo "  - $configfile ($COMMITS commits)"
  done
else
  echo "⚠️  No IaC/config files found"
fi

echo ""
echo "### Testing (Testing Family)"
echo "----------------------------"

TEST_DIRS=$(find . -maxdepth 2 -type d \( -name "tests" -o -name "test" -o -name "__tests__" -o -name "spec" \) 2>/dev/null | head -5)
TEST_FILE_COUNT=$(find . \( \
  -name "*test*.py" -o \
  -name "*_test.go" -o \
  -name "*.test.ts" -o \
  -name "*.test.js" -o \
  -name "*.spec.ts" -o \
  -name "*.spec.js" \
\) 2>/dev/null | wc -l | tr -d ' ')

if [ -n "$TEST_DIRS" ]; then
  echo "✅ Test directories found:"
  echo "$TEST_DIRS"
fi

echo "Test file count: $TEST_FILE_COUNT"

if [ "$TEST_FILE_COUNT" -gt 50 ]; then
  echo "✅ Sufficient test coverage for testing family"
else
  echo "⚠️  Limited test coverage"
fi

cd ../../..

echo ""
echo "========================================"
echo "Validation Summary: $OWNER/$REPO"
echo "========================================"
echo ""
echo "✅ = Available | ⚠️ = Partial/Warning | ❌ = Not Available"
echo ""
echo "Git:          ✅ ($COMMIT_COUNT commits)"
echo "CI/Build:     $([ "$WORKFLOW_COUNT" -gt 0 ] && echo '✅' || echo '❌') ($CI_RUN_COUNT runs)"
echo "Dependencies: $([ -n "$LOCKFILES" ] && echo '✅' || echo '❌')"
echo "Testing:      $([ "$TEST_FILE_COUNT" -gt 50 ] && echo '✅' || [ "$TEST_FILE_COUNT" -gt 0 ] && echo '⚠️' || echo '❌') ($TEST_FILE_COUNT test files)"
echo "Schema/API:   $([ -n "$SCHEMA_FILES" ] && echo '✅' || echo '⚠️')"
echo "Deployment:   $([ "$RELEASE_COUNT" -gt 10 ] && echo '✅' || [ "$RELEASE_COUNT" -gt 0 ] && echo '⚠️' || echo '❌') ($RELEASE_COUNT releases)"
echo "Config:       $([ -n "$CONFIG_FILES" ] && echo '✅' || echo '⚠️')"
echo "Security:     $([ "$ADVISORY_COUNT" -gt 0 ] && echo '✅' || echo '⚠️') ($ADVISORY_COUNT advisories)"
echo ""
echo "Next: Review results and update .calibration/repo_validation.md"
echo ""
