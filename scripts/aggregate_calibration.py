#!/usr/bin/env python3
"""
Aggregate Calibration — Merge Phase 4 patterns across repos into universal patterns.

Scans all calibration runs, extracts patterns from each repo's knowledge.db,
groups by fingerprint (same fingerprint = same behavioral pattern), aggregates
evidence, and produces evolution/data/universal_patterns.json.

Usage:
    python scripts/aggregate_calibration.py
    python scripts/aggregate_calibration.py --min-repos 3 --verbose
    python scripts/aggregate_calibration.py --runs-dir .calibration/runs --out evolution/data/universal_patterns.json
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_RUNS_DIR = PROJECT_ROOT / ".calibration" / "runs"
DEFAULT_OUTPUT = PROJECT_ROOT / "evolution" / "data" / "universal_patterns.json"


def _read_patterns_from_db(db_path: Path) -> list[dict]:
    """Read all non-expired patterns from a repo's knowledge.db."""
    patterns = []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Read candidate patterns
        for row in conn.execute(
            "SELECT * FROM patterns WHERE expired = 0"
        ).fetchall():
            d = dict(row)
            for key in ("sources", "metrics"):
                if isinstance(d.get(key), str):
                    d[key] = json.loads(d[key])
            patterns.append(d)

        # Read promoted knowledge artifacts
        for row in conn.execute("SELECT * FROM knowledge").fetchall():
            d = dict(row)
            for key in ("sources", "metrics"):
                if isinstance(d.get(key), str):
                    d[key] = json.loads(d[key])
            # Normalize knowledge artifacts to look like patterns
            d.setdefault("occurrence_count", d.get("support_count", 1))
            d.setdefault("confidence_tier", "confirmed")
            d.setdefault("discovery_method", "statistical")
            patterns.append(d)

        conn.close()
    except Exception as e:
        print(f"  [warn] Could not read {db_path}: {e}", file=sys.stderr)
    return patterns


def _read_phase4_summary(summary_path: Path) -> list[dict]:
    """Read phase4_summary.json as fallback when knowledge.db is missing."""
    try:
        with open(summary_path) as f:
            data = json.load(f)
        # phase4_summary.json may be a list of pattern summaries or a dict
        if isinstance(data, dict):
            patterns = data.get("patterns", [])
        elif isinstance(data, list):
            patterns = data
        else:
            return []
        return [p for p in patterns if isinstance(p, dict) and "fingerprint" in p]
    except Exception as e:
        print(f"  [warn] Could not read {summary_path}: {e}", file=sys.stderr)
        return []


def _canonical_repo_name(name: str) -> str:
    """Normalize repo names to detect duplicates.

    Examples:
        'fastapi-parallel' → 'fastapi'
        'gin' → 'gin'  (short names kept as-is; 'gin-gonic--gin' is different)
    """
    # Strip known suffixes from re-runs of the same repo
    for suffix in ("-parallel", "-rerun", "-v2", "-retry"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def collect_patterns(
    runs_dir: Path, verbose: bool = False, exclude: set[str] | None = None,
) -> dict:
    """Scan all calibration runs, extract patterns per repo.

    Returns:
        {
            "by_fingerprint": {fingerprint: [{"repo": ..., "pattern": ...}, ...]},
            "repo_stats": {repo_name: {"patterns": N, "families": [...]}},
        }
    """
    by_fingerprint = defaultdict(list)
    repo_stats = {}
    # Track canonical names already processed to skip duplicates
    seen_canonical = {}  # canonical_name → run_dir.name (the one we kept)

    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue

        repo_name = run_dir.name
        if exclude and repo_name in exclude:
            if verbose:
                print(f"  [skip] {repo_name}: excluded")
            continue

        canonical = _canonical_repo_name(repo_name)
        if canonical in seen_canonical:
            if verbose:
                print(f"  [skip] {repo_name}: duplicate of {seen_canonical[canonical]}")
            continue
        seen_canonical[canonical] = repo_name
        db_path = run_dir / "phase4" / "knowledge.db"
        summary_path = run_dir / "phase4" / "phase4_summary.json"

        # Try knowledge.db first (authoritative), fall back to summary
        if db_path.exists():
            patterns = _read_patterns_from_db(db_path)
            source = "knowledge.db"
        elif summary_path.exists():
            patterns = _read_phase4_summary(summary_path)
            source = "phase4_summary.json"
        else:
            if verbose:
                print(f"  [skip] {repo_name}: no Phase 4 data")
            continue

        if not patterns:
            if verbose:
                print(f"  [skip] {repo_name}: 0 patterns ({source})")
            continue

        # Deduplicate within repo by fingerprint (keep the one with highest occurrence_count)
        seen = {}
        for p in patterns:
            fp = p.get("fingerprint")
            if not fp:
                continue
            existing = seen.get(fp)
            if not existing or p.get("occurrence_count", 1) > existing.get("occurrence_count", 1):
                seen[fp] = p

        families = set()
        for p in seen.values():
            for s in p.get("sources", []):
                families.add(s)
            by_fingerprint[p["fingerprint"]].append({
                "repo": canonical,
                "pattern": p,
            })

        repo_stats[repo_name] = {
            "patterns": len(seen),
            "families": sorted(families),
            "source": source,
        }

        if verbose:
            print(f"  [ok]   {repo_name}: {len(seen)} patterns from {source} "
                  f"(families: {', '.join(sorted(families))})")

    return {
        "by_fingerprint": dict(by_fingerprint),
        "repo_stats": repo_stats,
    }


def aggregate_patterns(
    by_fingerprint: dict,
    min_repos: int = 2,
    min_total_occurrences: int = 3,
) -> list[dict]:
    """Merge patterns with the same fingerprint into universal patterns.

    A pattern is promoted to "universal" if:
    - Seen in >= min_repos different repos
    - Total occurrence_count across repos >= min_total_occurrences

    Returns list of universal pattern digests, sorted by repo_count desc.
    """
    universal = []

    for fingerprint, entries in by_fingerprint.items():
        # Deduplicate: if same canonical repo appears multiple times, keep best
        deduped = {}
        for entry in entries:
            repo = entry["repo"]
            existing = deduped.get(repo)
            if not existing or (
                entry["pattern"].get("occurrence_count", 1)
                > existing["pattern"].get("occurrence_count", 1)
            ):
                deduped[repo] = entry
        entries = list(deduped.values())

        repo_count = len(entries)
        if repo_count < min_repos:
            continue

        # Aggregate stats
        total_occurrences = 0
        weighted_correlation_sum = 0.0
        weight_sum = 0
        best_description = ""
        best_semantic = None
        sources = None
        metrics = None
        pattern_type = None
        discovery_method = None

        for entry in entries:
            p = entry["pattern"]
            occ = p.get("occurrence_count", 1)
            total_occurrences += occ

            # Weighted average of correlation strength
            corr = p.get("correlation_strength") or p.get("correlation")
            if corr is not None:
                weighted_correlation_sum += corr * occ
                weight_sum += occ

            # Take the longest/best description
            desc = p.get("description_statistical", "")
            if len(desc) > len(best_description):
                best_description = desc

            semantic = p.get("description_semantic")
            if semantic and (not best_semantic or len(semantic) > len(best_semantic)):
                best_semantic = semantic

            # Sources/metrics should be identical for same fingerprint
            if sources is None:
                sources = p.get("sources", [])
                metrics = p.get("metrics", [])
                pattern_type = p.get("pattern_type", "co_occurrence")
                discovery_method = p.get("discovery_method", "statistical")

        if total_occurrences < min_total_occurrences:
            continue

        avg_correlation = (
            round(weighted_correlation_sum / weight_sum, 4)
            if weight_sum > 0 else None
        )

        repos_seen = sorted(set(e["repo"] for e in entries))

        universal.append({
            "fingerprint": fingerprint,
            "pattern_type": pattern_type,
            "discovery_method": discovery_method,
            "sources": sources,
            "metrics": metrics,
            "description_statistical": best_description,
            "description_semantic": best_semantic,
            "correlation_strength": avg_correlation,
            "occurrence_count": total_occurrences,
            "confidence_tier": "confirmed" if repo_count >= 5 else "statistical",
            "scope": "universal",
            "repo_count": repo_count,
            "repos_observed": repos_seen,
        })

    # Sort: most widespread first, then by total occurrences
    universal.sort(key=lambda p: (-p["repo_count"], -p["occurrence_count"]))
    return universal


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate calibration patterns into universal_patterns.json"
    )
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR,
                        help="Directory containing calibration runs")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT,
                        help="Output path for universal_patterns.json")
    parser.add_argument("--min-repos", type=int, default=2,
                        help="Minimum repos seeing a pattern to include (default: 2)")
    parser.add_argument("--min-occurrences", type=int, default=3,
                        help="Minimum total occurrences across repos (default: 3)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-repo details")
    parser.add_argument("--all", action="store_true",
                        help="Also output repo-local patterns (seen in 1 repo)")
    args = parser.parse_args()

    print(f"Scanning calibration runs in {args.runs_dir}...")
    result = collect_patterns(args.runs_dir, verbose=args.verbose)

    repo_stats = result["repo_stats"]
    by_fingerprint = result["by_fingerprint"]

    print(f"\nRepos with patterns: {len(repo_stats)}")
    print(f"Unique fingerprints: {len(by_fingerprint)}")

    # Distribution of fingerprints by repo count
    repo_count_dist = defaultdict(int)
    for fp, entries in by_fingerprint.items():
        repo_count_dist[len(entries)] += 1
    print(f"\nFingerprint distribution by repo count:")
    for n in sorted(repo_count_dist):
        label = f"{n} repo{'s' if n > 1 else ''}"
        print(f"  {label:12s}: {repo_count_dist[n]} fingerprints")

    # Aggregate
    min_repos = 1 if args.all else args.min_repos
    universal = aggregate_patterns(
        by_fingerprint,
        min_repos=min_repos,
        min_total_occurrences=args.min_occurrences if not args.all else 1,
    )

    print(f"\nUniversal patterns (>={args.min_repos} repos): "
          f"{sum(1 for p in universal if p['repo_count'] >= args.min_repos)}")
    if args.all:
        print(f"Local patterns (1 repo only): "
              f"{sum(1 for p in universal if p['repo_count'] == 1)}")
    print(f"Total output: {len(universal)} patterns")

    # Produce output
    output = {
        "version": "1.0",
        "generated_by": "scripts/aggregate_calibration.py",
        "repos_analyzed": len(repo_stats),
        "total_unique_fingerprints": len(by_fingerprint),
        "min_repos_filter": args.min_repos,
        "patterns": universal,
        # Stripped version for import (keep repo_count, drop repos_observed)
        "import_ready": [
            {k: v for k, v in p.items() if k != "repos_observed"}
            for p in universal
            if p["repo_count"] >= args.min_repos
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nWritten to {args.out}")
    print(f"  import_ready: {len(output['import_ready'])} patterns "
          "(use this array for kb_export.import_patterns)")

    # Print top patterns
    if universal:
        print(f"\nTop patterns:")
        for i, p in enumerate(universal[:10], 1):
            sources = " × ".join(p["sources"])
            metrics = ", ".join(p["metrics"])
            corr = f"r={p['correlation_strength']:.3f}" if p.get("correlation_strength") else "r=?"
            print(f"  {i}. [{sources}] {metrics}  "
                  f"{corr}  seen in {p['repo_count']} repos ({p['occurrence_count']} times)")


if __name__ == "__main__":
    main()
