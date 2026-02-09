#!/bin/bash
# Monitor batch calibration progress
# Usage: bash .calibration/monitor.sh

cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine

echo "=== Batch Calibration Progress ==="
echo "Time: $(date)"
echo ""

# Count completed repos
completed=$(find .calibration/runs -name "calibration_result.json" 2>/dev/null | wc -l | tr -d ' ')
echo "Completed: $completed / 92 repos"
echo ""

# Show per-batch log status
for i in 0 1 2 3; do
    log=".calibration/logs/batch_${i}.log"
    if [ -f "$log" ]; then
        lines=$(wc -l < "$log" | tr -d ' ')
        last=$(tail -1 "$log" 2>/dev/null)
        running=$(pgrep -f "batch $i --batch-size" >/dev/null 2>&1 && echo "RUNNING" || echo "DONE")
        echo "Batch $i: $running ($lines lines) — $last"
    else
        echo "Batch $i: NOT STARTED"
    fi
done

echo ""
echo "=== Completed Repos ==="
for f in .calibration/runs/*/calibration_result.json; do
    [ -f "$f" ] || continue
    dir=$(dirname "$f")
    name=$(basename "$dir")
    info=$(python3 -c "
import json
r=json.load(open('$f'))
p=r.get('phase4',{}).get('patterns_discovered',0)
e=r.get('events',0)
s=r.get('signals',0)
t=r.get('calibration_time_seconds', r.get('elapsed_seconds','?'))
print(f'events={e:6d} signals={s:5d} patterns={p} time={t}s')
" 2>/dev/null)
    echo "  $name: $info"
done

echo ""
echo "=== Errors ==="
for i in 0 1 2 3; do
    log=".calibration/logs/batch_${i}.log"
    [ -f "$log" ] && grep -c "\[ERROR\]" "$log" 2>/dev/null | xargs -I{} echo "  Batch $i: {} errors"
done
