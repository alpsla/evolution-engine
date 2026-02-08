"""
Phase 2 Analysis on FastAPI Historical Data

Generate multi-family signals from the FastAPI repository's
git history and dependency evolution.
"""

from pathlib import Path
from evolution.phase2_engine import Phase2Engine


def main():
    evo_dir = Path(".evo_fastapi")
    
    print("=" * 70)
    print("Phase 2 Analysis - FastAPI Multi-Family Signals")
    print("=" * 70)
    
    # Check event counts
    import json
    from collections import Counter
    
    families = Counter()
    for f in (evo_dir / "events").glob("*.json"):
        data = json.loads(f.read_text())
        families[data.get('source_family', 'unknown')] += 1
    
    print("\n[Input Events]")
    for family, count in sorted(families.items()):
        print(f"  {family}: {count} events")
    print(f"  TOTAL: {sum(families.values())} events")
    
    # Run Phase 2
    print("\n[Phase 2] Computing baselines and deviation signals...")
    phase2 = Phase2Engine(evo_dir, window_size=50, min_baseline=10)
    results = phase2.run_all()
    
    # Count signals by family
    families_with_signals = {}
    for family, signals in results.items():
        if signals:
            families_with_signals[family] = len(signals)
    
    print(f"\n[Output Signals]")
    print(f"  Families with signals: {len(families_with_signals)}")
    for family, count in sorted(families_with_signals.items()):
        print(f"    {family}: {count} signals")
    
    # Show sample signals from each family
    print("\n[Sample Signals - First 5 from each family]")
    for family, signals in sorted(results.items()):
        if signals:
            print(f"\n  {family.upper()} ({len(signals)} total signals):")
            for sig in signals[:5]:
                metric = sig.get('metric', 'unknown')
                observed = sig.get('observed', 0)
                baseline = sig.get('baseline', {}).get('mean', 0)
                deviation = sig.get('deviation', {}).get('measure', 0)
                event_ref = sig.get('event_ref', '')[:7]
                print(f"    • {metric:25s} | obs={observed:7.1f} base={baseline:7.1f} dev={deviation:6.2f}σ | {event_ref}")
    
    # Show high deviation signals
    print("\n[High Deviation Signals - |deviation| > 2σ]")
    high_dev = []
    for family, signals in results.items():
        for sig in signals:
            dev = abs(sig.get('deviation', {}).get('measure', 0))
            if dev > 2.0:
                high_dev.append((family, sig))
    
    high_dev.sort(key=lambda x: abs(x[1]['deviation']['measure']), reverse=True)
    
    if high_dev:
        for family, sig in high_dev[:10]:
            metric = sig.get('metric', 'unknown')
            observed = sig.get('observed', 0)
            baseline = sig.get('baseline', {}).get('mean', 0)
            deviation = sig.get('deviation', {}).get('measure', 0)
            print(f"  [{family:16s}] {metric:25s} | dev={deviation:6.2f}σ (obs={observed:.1f}, base={baseline:.1f})")
    else:
        print("  (none found with |dev| > 2σ)")
    
    print("\n" + "=" * 70)
    print("✅ Multi-Family Signal Generation Complete!")
    print("=" * 70)
    print(f"\nProof of multi-family signals:")
    print(f"  • Input families: {sorted(families.keys())}")
    print(f"  • Output families: {sorted(families_with_signals.keys())}")
    print(f"  • Total signals: {sum(families_with_signals.values())}")


if __name__ == "__main__":
    main()
