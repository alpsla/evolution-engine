"""
Calibration Orchestrator — Full 9-Family Pipeline

Runs all 5 phases on a repository using:
  - Git adapter (version_control family)
  - Git History Walker (dependency, schema, config, testing, coverage families — from git files)
  - GitHub API adapters (CI, deployment, security families — from API)

Parallelized:
  - API family fetches run concurrently (ThreadPoolExecutor)
  - Git history walk + API fetches overlap when possible
  - Phase 2 family engines run concurrently

Usage:
    python examples/calibrate_repo.py <repo_path> <owner/repo> [--evo-dir DIR]

Example:
    python examples/calibrate_repo.py .calibration/repos/fastapi tiangolo/fastapi
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.phase3_engine import Phase3Engine
from evolution.phase4_engine import Phase4Engine
from evolution.phase5_engine import Phase5Engine
from evolution.adapters.git.git_adapter import GitSourceAdapter
from evolution.adapters.git.git_history_walker import GitHistoryWalker
from evolution.adapters.ci.github_actions_adapter import GitHubActionsAdapter
from evolution.adapters.deployment.github_releases_adapter import GitHubReleasesAdapter
from evolution.adapters.security.github_security_adapter import GitHubSecurityAdapter
from evolution.adapters.github_client import GitHubClient


def _fetch_api_family(name, adapter_factory, client):
    """Fetch events from an API adapter (runs in thread).

    Returns (name, events_list) where events_list is a list of raw event dicts.
    The actual Phase 1 ingestion happens on the main thread to avoid index races.
    """
    try:
        adapter = adapter_factory(client)
        events = list(adapter.iter_events())
        return name, events, None
    except Exception as e:
        return name, [], e


def run_calibration(repo_path: str, owner: str, repo: str, evo_dir: Path,
                    skip_api: bool = False, enable_llm: bool = False):
    """Run full 7-family calibration pipeline with parallel execution.

    Args:
        enable_llm: If False (default), forces PHASE31_ENABLED and PHASE4B_ENABLED
                    to false, preventing accidental LLM calls during calibration.
                    Pass True to opt in to LLM-enhanced explanations and pattern
                    interpretation.
    """
    if not enable_llm:
        os.environ["PHASE31_ENABLED"] = "false"
        os.environ["PHASE4B_ENABLED"] = "false"

    repo_path = Path(repo_path).resolve()
    scope = f"{owner}/{repo}"
    start = datetime.now()

    print("=" * 70)
    print(f"Calibration: {scope}")
    print(f"Repo path:   {repo_path}")
    print(f"Output:      {evo_dir}")
    print(f"Started:     {start.isoformat()}")
    print("=" * 70)

    if not repo_path.exists():
        print(f"\nRepo not found at {repo_path}")
        return None

    # ── Phase 1: Ingest events from all families ──

    phase1 = Phase1Engine(evo_dir)
    family_counts = {}

    # 1a. Git commits (version_control)
    print("\n[Phase 1] Ingesting git commits...")
    git_adapter = GitSourceAdapter(repo_path=str(repo_path))
    count = phase1.ingest(git_adapter)
    family_counts["version_control"] = count
    print(f"  git: {count} events")

    # 1b + 1c: Run git history walk and API fetches concurrently
    # API fetches are I/O-bound and can overlap with the CPU-bound git walk.
    api_futures = {}
    api_executor = None

    if not skip_api:
        token = os.getenv("GITHUB_TOKEN")
        if token:
            print("\n[Phase 1] Starting API fetches (concurrent)...")
            client = GitHubClient(owner, repo, token,
                                  cache_dir=evo_dir / "api_cache")

            api_factories = {
                "ci": lambda c: GitHubActionsAdapter(client=c, max_runs=500),
                "deployment": lambda c: GitHubReleasesAdapter(client=c),
                "security": lambda c: GitHubSecurityAdapter(client=c),
            }

            api_executor = ThreadPoolExecutor(max_workers=3,
                                              thread_name_prefix="api")
            for name, factory in api_factories.items():
                future = api_executor.submit(_fetch_api_family, name, factory,
                                             client)
                api_futures[future] = name
        else:
            print("\n[Phase 1] No GITHUB_TOKEN set, skipping API families")

    # 1b. Git History Walker (dependency, schema, config) — runs on main thread
    # while API fetches happen in background threads
    print("\n[Phase 1] Walking git history for file-based families...")
    t0 = time.monotonic()
    walker = GitHistoryWalker(
        repo_path=str(repo_path),
        target_families=["dependency", "schema", "config", "testing", "coverage"],
    )

    walker_counts = {"dependency": 0, "schema": 0, "config": 0, "testing": 0, "coverage": 0}
    for commit, family, adapter, committed_at in walker.iter_commit_events():
        n = phase1.ingest(adapter, override_observed_at=committed_at)
        if n > 0:
            walker_counts[family] += n

    walker_elapsed = time.monotonic() - t0
    for family, count in walker_counts.items():
        if count > 0:
            family_counts[family] = count
            print(f"  {family}: {count} events")
    print(f"  (walker: {walker_elapsed:.1f}s)")

    # 1c. Collect API results (should already be done or nearly done)
    if api_futures:
        print("\n[Phase 1] Collecting API results...")
        for future in as_completed(api_futures):
            name, events, error = future.result()
            if error:
                print(f"  {name}: failed ({error})")
                continue

            if events:
                # Wrap events in a simple iterable adapter for Phase1 ingestion
                class _ListAdapter:
                    def __init__(self, evts):
                        self._events = evts
                    def iter_events(self):
                        return iter(self._events)

                count = phase1.ingest(_ListAdapter(events))
                family_counts[name] = count
                print(f"  {name}: {count} events")
            else:
                print(f"  {name}: 0 events")

        api_executor.shutdown(wait=False)
        print(f"  API stats: {client.stats}")

    total_events = sum(family_counts.values())
    active_families = [f for f, c in family_counts.items() if c > 0]
    print(f"\n  TOTAL: {total_events} events across {len(active_families)} families")
    print(f"  Families: {', '.join(active_families)}")

    if total_events == 0:
        print("\nNo events ingested. Cannot continue.")
        return None

    # ── Phase 2: Baselines & Deviation Signals (parallel families) ──

    print("\n[Phase 2] Computing baselines and deviation signals (parallel)...")
    t0 = time.monotonic()
    phase2 = Phase2Engine(evo_dir, window_size=50, min_baseline=5)
    signals = phase2.run_all_parallel()

    signal_counts = {f: len(s) for f, s in signals.items() if s}
    total_signals = sum(signal_counts.values())
    p2_elapsed = time.monotonic() - t0
    print(f"  {total_signals} signals across {len(signal_counts)} families ({p2_elapsed:.1f}s)")
    for family, count in sorted(signal_counts.items()):
        print(f"    {family}: {count}")

    # ── Phase 3: Explanations ──

    print("\n[Phase 3] Generating explanations...")
    t0 = time.monotonic()
    phase3 = Phase3Engine(evo_dir)
    explanations = phase3.run()
    p3_elapsed = time.monotonic() - t0
    print(f"  {len(explanations)} explanations generated ({p3_elapsed:.1f}s)")

    # ── Phase 4: Pattern Discovery ──

    print("\n[Phase 4] Discovering cross-family patterns...")
    phase4 = Phase4Engine(evo_dir)
    p4_result = phase4.run()
    print(f"  Result: {p4_result}")

    # ── Phase 5: Advisory ──

    print("\n[Phase 5] Generating advisory report...")
    phase5 = Phase5Engine(evo_dir)
    advisory_result = phase5.run(scope=scope)

    if advisory_result["status"] == "complete":
        advisory = advisory_result["advisory"]
        print(f"  Significant changes: {advisory['summary']['significant_changes']}")
        print(f"  Families affected: {advisory['summary']['families_affected']}")
        print(f"  Pattern matches: {advisory['summary']['known_patterns_matched']}")
        print(f"\n  Outputs:")
        for fmt, path in advisory_result.get("formats", {}).items():
            print(f"    {fmt}: {path}")
    else:
        print(f"  Status: {advisory_result['status']}")
        print(f"  {advisory_result.get('message', '')}")

    # ── Summary ──

    elapsed = (datetime.now() - start).total_seconds()
    print("\n" + "=" * 70)
    print(f"Calibration complete: {scope}")
    print(f"  Events: {total_events} | Signals: {total_signals} | "
          f"Families: {len(active_families)} | Time: {elapsed:.1f}s")
    print("=" * 70)

    return {
        "scope": scope,
        "events": total_events,
        "families": active_families,
        "signals": total_signals,
        "signal_counts": signal_counts,
        "phase4": p4_result,
        "advisory_status": advisory_result["status"],
        "elapsed_seconds": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="Calibration orchestrator")
    parser.add_argument("repo_path", help="Path to cloned repository")
    parser.add_argument("owner_repo", help="GitHub owner/repo (e.g. tiangolo/fastapi)")
    parser.add_argument("--evo-dir", default=None,
                        help="Output directory (default: .calibration/runs/<repo>)")
    parser.add_argument("--skip-api", action="store_true",
                        help="Skip GitHub API calls (git-only families)")
    parser.add_argument("--llm", action="store_true",
                        help="Enable LLM calls (Phase 3.1 + 4b). Off by default to avoid cost.")
    args = parser.parse_args()

    owner, repo = args.owner_repo.split("/", 1)
    evo_dir = Path(args.evo_dir) if args.evo_dir else Path(f".calibration/runs/{repo}")

    result = run_calibration(args.repo_path, owner, repo, evo_dir,
                             skip_api=args.skip_api, enable_llm=args.llm)

    if result:
        print(f"\nResult: {result}")


if __name__ == "__main__":
    main()
