#!/bin/bash
# Parallel calibration — runs up to 4 repos concurrently
# Each repo gets its own log file in .calibration/logs/parallel/

set -e
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine

export GITHUB_TOKEN=$(gh auth token)
VENV=".venv/bin/python"
LOGDIR=".calibration/logs/parallel"
mkdir -p "$LOGDIR"

# Function to calibrate a single repo
calibrate_one() {
    local slug="$1"
    local repo_dir="$2"
    local run_name="$3"
    local skip_api="$4"
    local logfile="$LOGDIR/${run_name}.log"

    echo "[START] $slug → $run_name"

    $VENV -u -c "
import sys, os, json, time
sys.path.insert(0, '.')
os.environ['GITHUB_TOKEN'] = os.environ.get('GITHUB_TOKEN', '')
os.environ['PHASE31_ENABLED'] = 'false'
os.environ['PHASE4B_ENABLED'] = 'false'

from pathlib import Path
from examples.calibrate_repo import run_calibration

slug = '$slug'
repo_dir = '$repo_dir'
run_name = '$run_name'
skip_api = $skip_api
evo_dir = Path('.calibration/runs') / run_name

result_file = evo_dir / 'calibration_result.json'
if result_file.exists():
    print(f'SKIP {slug} — already done')
    sys.exit(0)

# Clean partial
if evo_dir.exists() and not result_file.exists():
    import shutil
    shutil.rmtree(evo_dir)

owner, repo = slug.split('/', 1)
try:
    result = run_calibration(str(repo_dir), owner, repo, evo_dir, skip_api=skip_api, enable_llm=False)
    if result:
        result_file.parent.mkdir(parents=True, exist_ok=True)
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        fams = len(result.get('families', []))
        pats = result.get('phase4', {}).get('patterns_discovered', 0)
        print(f'DONE {slug}: {result[\"events\"]} events, {fams} families, {pats} patterns')
except Exception as e:
    print(f'ERROR {slug}: {e}')
" > "$logfile" 2>&1

    local status=$?
    local last_line=$(tail -1 "$logfile")
    echo "[DONE] $slug ($last_line)"
}

# ── Phase B: Re-run existing repos with API (parallel) ──
echo "========================================"
echo "PARALLEL PHASE B: Re-run with API"
echo "========================================"

PHASE_B_REPOS=(
    "rails/rails|.calibration/repos/rails--rails|rails--rails-api2|False"
    "mastodon/mastodon|.calibration/repos/mastodon--mastodon|mastodon--mastodon-api2|False"
    "electron/electron|.calibration/repos/electron--electron|electron--electron-api2|False"
    "discourse/discourse|.calibration/repos/discourse--discourse|discourse--discourse-api2|False"
    "Homebrew/brew|.calibration/repos/Homebrew--brew|Homebrew--brew-api2|False"
    "angular/angular|.calibration/repos/angular--angular|angular--angular-api2|False"
    "mui/material-ui|.calibration/repos/mui--material-ui|mui--material-ui-api2|False"
    "hashicorp/vagrant|.calibration/repos/hashicorp--vagrant|hashicorp--vagrant-api2|False"
    "spring-projects/spring-boot|.calibration/repos/spring-projects--spring-boot|spring-projects--spring-boot-api2|False"
    "sveltejs/svelte|.calibration/repos/sveltejs--svelte|sveltejs--svelte-api2|False"
)

RUNNING=0
MAX_PARALLEL=4

for entry in "${PHASE_B_REPOS[@]}"; do
    IFS='|' read -r slug repo_dir run_name skip_api <<< "$entry"

    # Check if repo clone exists
    if [ ! -d "$repo_dir" ]; then
        echo "[SKIP] $slug — repo not cloned at $repo_dir"
        continue
    fi

    # Check if already done
    if [ -f ".calibration/runs/$run_name/calibration_result.json" ]; then
        echo "[SKIP] $slug — already calibrated"
        continue
    fi

    # Wait if at max parallel
    while [ $RUNNING -ge $MAX_PARALLEL ]; do
        wait -n 2>/dev/null || true
        RUNNING=$((RUNNING - 1))
    done

    calibrate_one "$slug" "$repo_dir" "$run_name" "$skip_api" &
    RUNNING=$((RUNNING + 1))
done

# Wait for Phase B to complete
wait
echo ""
echo "Phase B complete."

# ── Phase C: GitLab repos (parallel, skip API) ──
echo "========================================"
echo "PARALLEL PHASE C: GitLab repos"
echo "========================================"

GITLAB_REPOS=(
    "gitlab-org/gitlab-runner|https://gitlab.com/gitlab-org/gitlab-runner.git"
    "inkscape/inkscape|https://gitlab.com/inkscape/inkscape.git"
    "fdroid/fdroidclient|https://gitlab.com/fdroid/fdroidclient.git"
    "gnome/gnome-shell|https://gitlab.gnome.org/GNOME/gnome-shell.git"
    "tortoisegit/tortoisegit|https://gitlab.com/tortoisegit/tortoisegit.git"
)

RUNNING=0

for entry in "${GITLAB_REPOS[@]}"; do
    IFS='|' read -r slug url <<< "$entry"
    safe_name="gitlab--$(echo $slug | tr '/' '--')"
    repo_dir=".calibration/repos/$safe_name"

    # Clone if needed
    if [ ! -d "$repo_dir" ]; then
        echo "[CLONE] gitlab/$slug..."
        git clone --depth 2000 "$url" "$repo_dir" 2>/dev/null || {
            echo "[SKIP] gitlab/$slug — clone failed"
            continue
        }
        cd "$repo_dir" && git fetch --unshallow 2>/dev/null; cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
    fi

    # Check if already done
    if [ -f ".calibration/runs/$safe_name/calibration_result.json" ]; then
        echo "[SKIP] gitlab/$slug — already calibrated"
        continue
    fi

    while [ $RUNNING -ge $MAX_PARALLEL ]; do
        wait -n 2>/dev/null || true
        RUNNING=$((RUNNING - 1))
    done

    calibrate_one "$slug" "$repo_dir" "$safe_name" "True" &
    RUNNING=$((RUNNING + 1))
done

wait
echo ""
echo "Phase C complete."

# ── Aggregate ──
echo "========================================"
echo "AGGREGATING PATTERNS"
echo "========================================"
$VENV scripts/aggregate_calibration.py --verbose --min-repos 2

echo ""
echo "========================================"
echo "ALL DONE"
echo "========================================"
echo "Results in .calibration/logs/parallel/"
echo "Per-repo: .calibration/runs/*/calibration_result.json"
echo "Patterns: evolution/data/universal_patterns.json"
