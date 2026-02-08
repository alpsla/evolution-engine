"""
Real-World Analysis: FastAPI Repository

Run Git History Walker on the FastAPI repository to extract
historical dependency evolution and demonstrate multi-family signals.
"""

from pathlib import Path
from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.adapters.git.git_adapter import GitSourceAdapter
from evolution.adapters.git.git_history_walker import GitHistoryWalker


def main():
    # Setup
    fastapi_repo = Path(".calibration/repos/fastapi").resolve()
    evo_dir = Path(".evo_fastapi")
    
    print("=" * 70)
    print("Git History Walker - FastAPI Repository Analysis")
    print("=" * 70)
    print(f"\nRepository: {fastapi_repo}")
    print(f"Output: {evo_dir}")
    
    if not fastapi_repo.exists():
        print(f"\n❌ FastAPI repository not found at {fastapi_repo}")
        return
    
    # Phase 1: Record git commits
    print("\n[Phase 1] Recording git commits...")
    phase1 = Phase1Engine(evo_dir)
    
    git_adapter = GitSourceAdapter(repo_path=str(fastapi_repo))
    git_count = phase1.ingest(git_adapter)
    print(f"  ✓ Recorded {git_count} git commits")
    
    # Phase 1: Walk history and extract dependency/schema/config snapshots
    print("\n[Phase 1] Walking git history for dependency/schema/config files...")
    print("  (This may take a few minutes for a large repository...)")
    
    walker = GitHistoryWalker(
        repo_path=str(fastapi_repo),
        target_families=['dependency', 'schema', 'config']
    )
    
    family_counts = {'dependency': 0, 'schema': 0, 'config': 0}
    commit_details = []
    
    for commit, family, adapter, committed_at in walker.iter_commit_events():
        count = phase1.ingest(adapter, override_observed_at=committed_at)
        if count > 0:
            family_counts[family] += count
            commit_details.append({
                'sha': commit.hexsha[:7],
                'family': family,
                'count': count,
                'message': commit.message.split('\n')[0][:50]
            })
            print(f"  ✓ {commit.hexsha[:7]} ({family}): {count} events - {commit.message.split()[0]}")
    
    print(f"\n  Summary:")
    print(f"    - Git commits: {git_count}")
    print(f"    - Dependency snapshots: {family_counts['dependency']}")
    print(f"    - Schema versions: {family_counts['schema']}")
    print(f"    - Config snapshots: {family_counts['config']}")
    
    total_events = git_count + sum(family_counts.values())
    print(f"    - TOTAL EVENTS: {total_events}")
    
    # Phase 2: Compute baselines and deviations
    print("\n[Phase 2] Computing baselines and deviation signals...")
    phase2 = Phase2Engine(evo_dir, window_size=20, min_baseline=5)
    results = phase2.run_all()
    
    families_with_signals = {}
    for family, signals in results.items():
        if signals:
            families_with_signals[family] = len(signals)
    
    print(f"\n  ✓ Generated signals for {len(families_with_signals)} families:")
    for family, count in sorted(families_with_signals.items()):
        print(f"    - {family}: {count} signals")
    
    # Show sample signals from each family
    print("\n[Sample Signals]")
    for family, signals in results.items():
        if signals:
            print(f"\n  {family.upper()} (showing first 3 of {len(signals)}):")
            for sig in signals[:3]:
                metric = sig.get('metric', 'unknown')
                observed = sig.get('observed', 0)
                baseline = sig.get('baseline', {}).get('mean', 0)
                deviation = sig.get('deviation', {}).get('measure', 0)
                print(f"    • {metric}: observed={observed:.1f}, baseline={baseline:.1f}, deviation={deviation:.2f}σ")
    
    print("\n" + "=" * 70)
    print("✅ Analysis complete!")
    print("=" * 70)
    print(f"\nData stored in: {evo_dir}")
    print(f"Events: {total_events}")
    print(f"Families with signals: {list(families_with_signals.keys())}")


if __name__ == "__main__":
    main()
