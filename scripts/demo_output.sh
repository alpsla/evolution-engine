#!/usr/bin/env bash
# Scripted demo output — produces the exact output from VIDEO_SCRIPT.md
# Used by demo_scripted.tape for a reproducible, polished recording
#
# Usage: bash scripts/demo_output.sh <scene>

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

scene="${1:-all}"

demo_install() {
    echo -e "${DIM}Collecting evolution-engine${NC}"
    sleep 0.3
    echo -e "${DIM}  Downloading evolution_engine-0.3.0-py3-none-any.whl (128 kB)${NC}"
    sleep 0.2
    echo -e "${DIM}Installing collected packages: evolution-engine${NC}"
    sleep 0.3
    echo -e "${GREEN}Successfully installed evolution-engine-0.3.0${NC}"
}

demo_analyze() {
    echo -e "${CYAN}Scanning sources...${NC}"
    sleep 0.4
    echo -e "  ${GREEN}✓${NC} git history (50 commits)"
    sleep 0.2
    echo -e "  ${GREEN}✓${NC} package-lock.json (dependency tracking)"
    sleep 0.2
    echo -e "  ${GREEN}✓${NC} .github/workflows (CI detection)"
    sleep 0.3
    echo ""
    echo -e "Phase 1: Collecting events... ${BOLD}847 events${NC}"
    sleep 0.4
    echo -e "Phase 2: Extracting signals... ${BOLD}2,541 signals${NC}"
    sleep 0.4
    echo -e "Phase 3: Generating explanations..."
    sleep 0.3
    echo -e "Phase 4: Matching patterns... ${BOLD}12 patterns matched${NC}"
    sleep 0.3
    echo -e "Phase 5: Building advisory..."
    sleep 0.5
    echo ""
    echo -e "${YELLOW}⚠️  3 significant changes detected${NC}"
    echo ""
    printf " %-3s %-10s %-12s %-22s %s\n" "#" "Severity" "Family" "Metric" "Deviation"
    printf " %-3s %-10s %-12s %-22s %s\n" "─" "────────" "──────" "──────" "─────────"
    printf " %-3s ${RED}%-10s${NC} %-12s %-22s %s\n" "1" "🔴 High" "git" "dispersion" "+3.2σ (0.87 vs baseline 0.32)"
    printf " %-3s ${YELLOW}%-10s${NC} %-12s %-22s %s\n" "2" "🟡 Medium" "ci" "run_duration" "+2.1σ (340s vs baseline 180s)"
    printf " %-3s ${YELLOW}%-10s${NC} %-12s %-22s %s\n" "3" "🟡 Medium" "dependency" "dependency_count" "+1.8σ (47 vs baseline 38)"
    echo ""
    echo -e "${BLUE}Pattern:${NC} ci_failure + high_dispersion → scattered refactoring (85% confidence)"
}

demo_report() {
    echo -e "Report saved to ${BOLD}.evo/report.html${NC}"
    sleep 0.3
    echo "Opening in browser..."
}

demo_verify() {
    echo -e "${CYAN}Comparing with previous analysis...${NC}"
    sleep 0.5
    echo ""
    echo -e " ${GREEN}✅${NC} git/dispersion — returned to normal (0.34)"
    sleep 0.3
    echo -e " ${YELLOW}⚠️${NC}  ci/run_duration — still deviating (+1.9σ)"
    sleep 0.3
    echo -e " ${GREEN}✅${NC} dependency/dependency_count — stabilized"
    echo ""
    echo -e "Resolution rate: ${BOLD}67%${NC} (2 of 3 resolved)"
}

demo_investigate() {
    echo -e "${DIM}🤖 AI Transparency: This feature uses AI to analyze advisory findings.${NC}"
    echo ""
    echo "Investigating 3 findings..."
    sleep 0.5
    echo ""
    echo -e "${BOLD}Finding 1${NC} (git/dispersion +3.2σ):"
    sleep 0.3
    echo "  Commit abc1234 touched 12 files across 5 directories."
    sleep 0.2
    echo "  This appears to be a large refactoring that started in commit def5678."
    sleep 0.2
    echo "  The dispersion spike correlates with CI duration increase."
    echo ""
    echo -e "  ${BLUE}Recommendation:${NC} Review commits abc1234..ghi9012 for unintended scope creep."
}

case "$scene" in
    install)     demo_install ;;
    analyze)     demo_analyze ;;
    report)      demo_report ;;
    verify)      demo_verify ;;
    investigate) demo_investigate ;;
    all)
        demo_install
        echo ""
        demo_analyze
        echo ""
        demo_report
        echo ""
        demo_investigate
        echo ""
        demo_verify
        ;;
    *) echo "Usage: $0 {install|analyze|report|verify|investigate|all}" ;;
esac
