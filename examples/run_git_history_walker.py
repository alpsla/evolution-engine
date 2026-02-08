"""
Example: Git History Walker

Demonstrates using the Git History Walker to extract historical
dependency, schema, and config snapshots from git history.
"""

from pathlib import Path
from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.adapters.git.git_adapter import GitSourceAdapter
from evolution.adapters.git.git_history_walker import GitHistoryWalker


def main():
    # Setup
    repo_path = "."  # Current repository
    evo_dir = Path(".evo")
    
    print("=" * 60)
    print("Git History Walker - Historical Evolution Analysis")
    print("=" * 60)
    
    # Phase 1: Record git commits
    print("\n[Phase 1] Recording git commits...")
    phase1 = Phase1Engine(evo_dir)
    
    git_adapter = GitSourceAdapter(repo_path=repo_path)
    git_count = phase1.ingest(git_adapter)
    print(f"  ✓ Recorded {git_count} git commits")
    
    # Phase 1: Walk history and extract dependency/schema/config snapshots
    print("\n[Phase 1] Walking git history for dependency/schema/config files...")
    walker = GitHistoryWalker(
        repo_path=repo_path,
        target_families=['dependency', 'schema', 'config']
    )
    
    family_counts = {'dependency': 0, 'schema': 0, 'config': 0}
    for commit, family, adapter, committed_at in walker.iter_commit_events():
        count = phase1.ingest(adapter, override_observed_at=committed_at)
        if count > 0:
            family_counts[family] += count
            print(f"  ✓ Commit {commit.hexsha[:7]} ({family}): {count} events")
    
    print(f"\n  Summary:")
    print(f"    - Dependency snapshots: {family_counts['dependency']}")
    print(f"    - Schema versions: {family_counts['schema']}")
    print(f"    - Config snapshots: {family_counts['config']}")
    
    # Phase 2: Compute baselines and deviations
    print("\n[Phase 2] Computing baselines and deviation signals...")
    phase2 = Phase2Engine(evo_dir, window_size=10, min_baseline=3)
    results = phase2.run_all()
    
    families_with_signals = {}
    for family, signals in results.items():
        if signals:
            families_with_signals[family] = len(signals)
    
    print(f"  ✓ Generated signals for families:")
    for family, count in families_with_signals.items():
        print(f"    - {family}: {count} signals")
    
    print("\n" + "=" * 60)
    print("✅ Analysis complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
