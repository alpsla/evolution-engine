#!/usr/bin/env bash
# Evolution Engine — Demo Script
#
# Demonstrates the full EE flow on a real repository.
#
# Usage:
#   ./scripts/demo.sh                    # Use a temp repo
#   ./scripts/demo.sh /path/to/repo      # Use an existing repo
#   GITHUB_TOKEN=ghp_xxx ./scripts/demo.sh  # Unlock CI + deployment families
#
# Prerequisites:
#   pip install evolution-engine   (or: pip install -e .)

set -euo pipefail

REPO="${1:-}"
CLEANUP=false

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

header() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}\n"; }
step()   { echo -e "${GREEN}▸ $1${NC}"; }

echo -e "${YELLOW}"
echo "╔═══════════════════════════════════════════════╗"
echo "║    Evolution Engine — Demo                    ║"
echo "║    Cross-signal development process monitor   ║"
echo "╚═══════════════════════════════════════════════╝"
echo -e "${NC}"

# ─── Step 1: Set up repo ───

if [ -z "$REPO" ]; then
    REPO=$(mktemp -d)
    CLEANUP=true
    header "Step 1: Setting up demo repository"
    step "Cloning a sample repo..."
    git clone --depth=200 https://github.com/tiangolo/fastapi.git "$REPO" 2>/dev/null
    echo "  Cloned fastapi (200 commits) to $REPO"
else
    header "Step 1: Using existing repository"
    echo "  Path: $REPO"
fi

cd "$REPO"

# ─── Step 2: Analyze ───

header "Step 2: Running evo analyze"
step "Detecting adapters and running pipeline..."

TOKEN_ARG=""
if [ -n "${GITHUB_TOKEN:-}" ]; then
    TOKEN_ARG="--token $GITHUB_TOKEN"
    echo "  GITHUB_TOKEN detected — CI, deployment, and security families enabled"
fi

evo analyze . $TOKEN_ARG || true

# ─── Step 3: Sources ───

header "Step 3: Checking detected data sources"
step "Running evo sources..."
evo sources . $TOKEN_ARG || true

# ─── Step 4: Show prompt ───

header "Step 4: Investigation prompt"
step "Generating investigation prompt for AI assistants..."

if [ -f .evo/phase5/investigation_prompt.txt ]; then
    echo ""
    echo "  The investigation prompt is ready at:"
    echo "  .evo/phase5/investigation_prompt.txt"
    echo ""
    echo "  First 5 lines:"
    head -5 .evo/phase5/investigation_prompt.txt | sed 's/^/  /'
    echo "  ..."
else
    echo "  No investigation prompt generated (no significant findings)"
fi

# ─── Step 5: Report ───

header "Step 5: Generating HTML report"
step "Running evo report..."

if [ -f .evo/phase5/advisory.json ]; then
    evo report . --output .evo/report.html || true
    echo "  Report saved to: .evo/report.html"
    # Open on macOS
    if command -v open &>/dev/null && [ -f .evo/report.html ]; then
        echo "  Opening in browser..."
        open .evo/report.html
    fi
else
    echo "  No advisory found — skipping report"
fi

# ─── Summary ───

header "Summary"
echo "  What happened:"
echo "    1. EE scanned the repo for data sources (git, lockfiles, CI configs)"
echo "    2. Phase 1 ingested events from all detected sources"
echo "    3. Phase 2 computed behavioral baselines and deviations"
echo "    4. Phase 3 generated PM-friendly explanations"
echo "    5. Phase 4 discovered cross-family patterns"
echo "    6. Phase 5 produced an advisory with risk levels"
echo ""
echo "  Next steps:"
echo "    evo investigate .                  # AI root cause analysis"
echo "    evo fix .                          # AI fix loop (iterate until clear)"
echo "    evo sources --what-if datadog      # See what more data would add"
echo ""
echo "  All data stays local — nothing left your machine."

# Cleanup
if [ "$CLEANUP" = true ]; then
    echo ""
    echo "  Temp repo at: $REPO"
    echo "  (delete with: rm -rf $REPO)"
fi
