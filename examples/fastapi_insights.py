"""
FastAPI Repository Insights

Analyze the multi-family signals to extract interesting patterns
from FastAPI's evolution.
"""

from pathlib import Path
import json
from collections import defaultdict


def main():
    evo_dir = Path(".evo_fastapi")
    
    print("=" * 70)
    print("FastAPI Repository - Multi-Family Evolution Insights")
    print("=" * 70)
    
    # Load dependency events to show evolution timeline
    dep_events = []
    for f in sorted((evo_dir / "events").glob("*.json")):
        data = json.loads(f.read_text())
        if data.get('source_family') == 'dependency':
            dep_events.append({
                'timestamp': data['observed_at'],
                'commit_sha': data['payload']['trigger']['commit_sha'][:7],
                'total_count': data['payload']['snapshot']['total_count'],
                'direct_count': data['payload']['snapshot']['direct_count'],
                'dependencies': data['payload']['dependencies']
            })
    
    # Sort by timestamp
    dep_events.sort(key=lambda x: x['timestamp'])
    
    print(f"\n[Dependency Evolution Timeline]")
    print(f"  Total snapshots: {len(dep_events)}")
    print(f"  First snapshot: {dep_events[0]['timestamp'][:10]} (commit {dep_events[0]['commit_sha']})")
    print(f"  Last snapshot: {dep_events[-1]['timestamp'][:10]} (commit {dep_events[-1]['commit_sha']})")
    
    # Show dependency count evolution (sample points)
    print(f"\n[Dependency Count Over Time - Sample Points]")
    sample_indices = [0, len(dep_events)//4, len(dep_events)//2, 3*len(dep_events)//4, -1]
    for idx in sample_indices:
        evt = dep_events[idx]
        print(f"  {evt['timestamp'][:10]} | {evt['commit_sha']} | {evt['total_count']:3d} deps ({evt['direct_count']:3d} direct)")
    
    # Track dependency additions/removals
    print(f"\n[Dependency Changes]")
    min_deps = min(e['total_count'] for e in dep_events)
    max_deps = max(e['total_count'] for e in dep_events)
    avg_deps = sum(e['total_count'] for e in dep_events) / len(dep_events)
    
    print(f"  Min dependencies: {min_deps}")
    print(f"  Max dependencies: {max_deps}")
    print(f"  Avg dependencies: {avg_deps:.1f}")
    print(f"  Growth: {max_deps - min_deps} dependencies added")
    
    # Find largest jumps
    print(f"\n[Largest Dependency Increases]")
    jumps = []
    for i in range(1, len(dep_events)):
        prev = dep_events[i-1]
        curr = dep_events[i]
        diff = curr['total_count'] - prev['total_count']
        if diff > 0:
            jumps.append((diff, curr['commit_sha'], curr['timestamp'][:10], curr['total_count']))
    
    jumps.sort(reverse=True)
    for diff, commit, date, total in jumps[:5]:
        print(f"  +{diff:2d} deps | {commit} | {date} | total={total}")
    
    # Most common dependencies
    print(f"\n[Most Stable Dependencies - Present in >80% of snapshots]")
    dep_names = defaultdict(int)
    for evt in dep_events:
        for dep in evt['dependencies']:
            dep_names[dep['name']] += 1
    
    threshold = len(dep_events) * 0.8
    stable_deps = [(name, count) for name, count in dep_names.items() if count > threshold]
    stable_deps.sort(key=lambda x: x[1], reverse=True)
    
    for name, count in stable_deps[:10]:
        pct = (count / len(dep_events)) * 100
        print(f"  {name:30s} | present in {count:3d}/{len(dep_events)} snapshots ({pct:.0f}%)")
    
    # Load Phase 2 signals
    phase2_dir = evo_dir / "phase2"
    signal_counts = {'git': 0, 'dependency': 0}
    
    for family in ['git', 'dependency']:
        signal_file = phase2_dir / f"{family}_signals.json"
        if signal_file.exists():
            signals = json.loads(signal_file.read_text())
            signal_counts[family] = len(signals)
    
    print(f"\n[Phase 2 Signals Generated]")
    for family, count in signal_counts.items():
        print(f"  {family}: {count} signals")
    
    print("\n" + "=" * 70)
    print("✅ FastAPI shows rich multi-family evolution!")
    print("=" * 70)
    print(f"\nKey Findings:")
    print(f"  • {len(dep_events)} dependency snapshots across {dep_events[-1]['timestamp'][:4]}-{dep_events[0]['timestamp'][:4]}")
    print(f"  • Dependency count grew from {min_deps} to {max_deps}")
    print(f"  • {len(stable_deps)} stable core dependencies")
    print(f"  • {signal_counts['git']} git signals + {signal_counts['dependency']} dependency signals")


if __name__ == "__main__":
    main()
