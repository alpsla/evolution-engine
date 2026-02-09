#!/usr/bin/env python3
"""
Batch Calibration Runner — Clone and calibrate all candidate repos.

Designed to be run by parallel Claude Code agents (Sonnet 4.5).
Each agent handles one repo: clone → calibrate → write results.

Usage:
    # Single repo:
    python examples/batch_calibrate.py tiangolo/fastapi

    # All repos (sequential):
    python examples/batch_calibrate.py --all

    # Specific batch (for parallel agents):
    python examples/batch_calibrate.py --batch 0 --batch-size 10

    # List all repos:
    python examples/batch_calibrate.py --list

    # Skip repos that already have results:
    python examples/batch_calibrate.py --all --skip-existing

Environment:
    GITHUB_TOKEN — Required for API families (CI, deployment, security)
    PHASE31_ENABLED=false — Disable LLM enhancement (faster, no OpenRouter needed)
    PHASE4B_ENABLED=false — Disable LLM pattern interpretation
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPOS_FILE = PROJECT_ROOT / ".calibration" / "repos_found.json"
REPOS_DIR = PROJECT_ROOT / ".calibration" / "repos"
RUNS_DIR = PROJECT_ROOT / ".calibration" / "runs"
RESULTS_FILE = PROJECT_ROOT / ".calibration" / "batch_results.json"

# Repos that are documentation/list-only (no meaningful code to analyze)
SKIP_REPOS = {
    "public-apis/public-apis",
    "EbookFoundation/free-programming-books",
    "donnemartin/system-design-primer",
    "vinta/awesome-python",
    "avelino/awesome-go",
    "521xueweihan/HelloGitHub",
    "kamranahmedse/developer-roadmap",
    "yangshun/tech-interview-handbook",
    "trekhleb/javascript-algorithms",
    "airbnb/javascript",
    "Chalarangelo/30-seconds-of-code",
    "ryanmcdermott/clean-code-javascript",
    "jaywcjlove/awesome-mac",
    "microsoft/Web-Dev-For-Beginners",
    "Snailclimb/JavaGuide",
    "krahets/hello-algo",
    "GrowingGit/GitHub-Chinese-Top-Charts",
    "MisterBooo/LeetCodeAnimation",
    "doocs/advanced-java",
    "TheAlgorithms/Python",
    "TheAlgorithms/Java",
    "kdn251/interviews",
    "kilimchoi/engineering-blogs",
    "bayandin/awesome-awesomeness",
    "matteocrippa/awesome-swift",
    "iluwatar/java-design-patterns",
    "freeCodeCamp/devdocs",
    "rust-lang/rustlings",
}


def load_repos():
    """Load repo list from repos_found.json."""
    with open(REPOS_FILE, "r") as f:
        data = json.load(f)
    repos = []
    for r in data:
        owner = r["owner"]["login"]
        name = r["name"]
        slug = f"{owner}/{name}"
        if slug not in SKIP_REPOS:
            repos.append({
                "slug": slug,
                "owner": owner,
                "name": name,
                "language": r.get("language", "unknown"),
                "stars": r.get("stargazersCount", 0),
            })
    return repos


def _safe_dir(slug):
    """Convert 'owner/repo' to 'owner--repo' for safe directory names."""
    return slug.replace("/", "--")


def clone_repo(slug, shallow_commits=2000):
    """Clone a repo (shallow) if not already present."""
    owner, name = slug.split("/", 1)
    repo_dir = REPOS_DIR / _safe_dir(slug)
    if repo_dir.exists():
        print(f"  [clone] {slug} — already exists at {repo_dir}")
        return repo_dir

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{slug}.git"
    print(f"  [clone] {slug} — shallow clone ({shallow_commits} commits)...")
    try:
        subprocess.run(
            ["git", "clone", "--depth", str(shallow_commits), url, str(repo_dir)],
            check=True, capture_output=True, timeout=300,
        )
        # Unshallow to get full history for proper baseline computation
        subprocess.run(
            ["git", "fetch", "--unshallow"],
            cwd=str(repo_dir), capture_output=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        print(f"  [clone] {slug} — timeout, using shallow clone")
    except subprocess.CalledProcessError as e:
        print(f"  [clone] {slug} — failed: {e.stderr.decode()[:200]}")
        return None
    return repo_dir


def calibrate_repo(slug, skip_api=False, enable_llm=False):
    """Run full calibration on a single repo. Returns result dict or None."""
    owner, name = slug.split("/", 1)
    repo_dir = clone_repo(slug)
    if not repo_dir:
        return None

    evo_dir = RUNS_DIR / _safe_dir(slug)

    # Clean partial runs (has run dir but no result file) for idempotent re-runs
    if evo_dir.exists() and not (evo_dir / "calibration_result.json").exists():
        import shutil
        print(f"  [clean] Removing partial run at {evo_dir}")
        shutil.rmtree(evo_dir)

    print(f"\n{'='*60}")
    print(f"Calibrating: {slug}")
    print(f"{'='*60}")

    try:
        from examples.calibrate_repo import run_calibration
        result = run_calibration(
            repo_path=str(repo_dir),
            owner=owner,
            repo=name,
            evo_dir=evo_dir,
            skip_api=skip_api,
            enable_llm=enable_llm,
        )
        return result
    except Exception as e:
        print(f"  [ERROR] {slug}: {e}")
        return {"scope": slug, "error": str(e)}


def save_result(slug, result):
    """Append result to batch_results.json (thread-safe via separate files)."""
    result_file = RUNS_DIR / _safe_dir(slug) / "calibration_result.json"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    with open(result_file, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  [saved] {result_file}")


def has_result(slug):
    """Check if a repo already has calibration results."""
    result_file = RUNS_DIR / _safe_dir(slug) / "calibration_result.json"
    return result_file.exists()


def main():
    parser = argparse.ArgumentParser(description="Batch calibration runner")
    parser.add_argument("repo", nargs="?", help="Single repo to calibrate (owner/repo)")
    parser.add_argument("--all", action="store_true", help="Calibrate all repos")
    parser.add_argument("--batch", type=int, default=None,
                        help="Batch index (0-based) for parallel execution")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Number of repos per batch (default 10)")
    parser.add_argument("--list", action="store_true", help="List all repos and exit")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip repos that already have results")
    parser.add_argument("--skip-api", action="store_true",
                        help="Skip GitHub API families (git+walker only)")
    parser.add_argument("--llm", action="store_true",
                        help="Enable LLM calls (Phase 3.1 + 4b). Off by default to avoid cost.")
    args = parser.parse_args()

    repos = load_repos()

    if args.list:
        for i, r in enumerate(repos):
            existing = "✅" if has_result(r["slug"]) else "  "
            print(f"{existing} {i:3d}. {r['slug']:45s} {r['language']:15s} ★{r['stars']:,}")
        print(f"\nTotal: {len(repos)} repos ({len(SKIP_REPOS)} skipped as non-code)")
        return

    if args.repo:
        # Single repo mode
        result = calibrate_repo(args.repo, skip_api=args.skip_api, enable_llm=args.llm)
        if result:
            save_result(args.repo, result)
        return

    if args.batch is not None:
        # Batch mode — for parallel agents
        start_idx = args.batch * args.batch_size
        batch = repos[start_idx:start_idx + args.batch_size]
        print(f"Batch {args.batch}: repos {start_idx}-{start_idx + len(batch) - 1} "
              f"({len(batch)} repos)")
    elif args.all:
        batch = repos
    else:
        parser.print_help()
        return

    results = []
    for r in batch:
        if args.skip_existing and has_result(r["slug"]):
            print(f"\n[skip] {r['slug']} — already calibrated")
            continue

        t0 = time.time()
        result = calibrate_repo(r["slug"], skip_api=args.skip_api, enable_llm=args.llm)
        elapsed = time.time() - t0

        if result:
            result["calibration_time_seconds"] = round(elapsed, 1)
            save_result(r["slug"], result)
            results.append(result)
        else:
            results.append({"scope": r["slug"], "error": "calibration returned None"})

    # Summary
    print(f"\n{'='*60}")
    print("BATCH SUMMARY")
    print(f"{'='*60}")
    successful = [r for r in results if "error" not in r and r.get("events", 0) > 0]
    failed = [r for r in results if "error" in r or r.get("events", 0) == 0]
    print(f"Successful: {len(successful)}")
    print(f"Failed:     {len(failed)}")
    for r in successful:
        p4 = r.get("phase4", {})
        patterns = p4.get("patterns_discovered", 0)
        print(f"  ✅ {r['scope']:40s} events={r.get('events',0):6d} "
              f"signals={r.get('signals',0):6d} patterns={patterns}")
    for r in failed:
        print(f"  ❌ {r.get('scope', '?'):40s} {r.get('error', 'no events')[:50]}")


if __name__ == "__main__":
    main()
