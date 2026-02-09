#!/bin/bash
# Launch 4 parallel calibration batches
set -e

cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine

export GITHUB_TOKEN="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"
# LLM disabled by default — use --llm flag to opt in
# export PHASE31_ENABLED=true
# export PHASE4B_ENABLED=true
export PYTHONUNBUFFERED=1

PYTHON=".venv/bin/python"
SCRIPT="examples/batch_calibrate.py"
LOGDIR=".calibration/logs"

mkdir -p "$LOGDIR"

for batch in 0 1 2 3; do
    $PYTHON -u $SCRIPT --batch $batch --batch-size 23 --skip-existing \
        > "$LOGDIR/batch_${batch}.log" 2>&1 &
    echo "Batch $batch PID: $!"
done

echo ""
echo "All 4 batches launched at $(date)"
echo "Monitor: bash .calibration/monitor.sh"
echo "Logs:    tail -f .calibration/logs/batch_*.log"
