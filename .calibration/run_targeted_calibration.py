#!/usr/bin/env python3
"""
Calibration v3 — 9 Families (+ testing, coverage, error_tracking)

Calibrate 130+ repos across all signal families. New in v3:
  - testing + coverage families in git history walker
  - 15 Sentry-focused repos (rich CI/deployment for cross-family patterns)
  - 10 testing/coverage-rich repos
  - Re-run 30+ existing repos with updated walker (testing + coverage)
  - Parallel execution with ProcessPoolExecutor

Strategy:
  Phase A: Sentry-focused repos (15 new) — clone + full calibration
  Phase B: Testing/coverage-rich repos (10 new/existing)
  Phase C: Re-run existing repos with updated pipeline (testing+coverage)
  Phase D: GitLab repos (git + dependency only)
  Phase E: Aggregate all patterns

Usage:
    export GITHUB_TOKEN=$(gh auth token)

    # Run everything (sequential):
    python .calibration/run_targeted_calibration.py

    # Run everything in parallel:
    python .calibration/run_targeted_calibration.py --parallel

    # Just new Sentry repos:
    python .calibration/run_targeted_calibration.py --sentry-only --parallel

    # Just testing/coverage repos:
    python .calibration/run_targeted_calibration.py --testing-only --parallel

    # Just re-run existing with new families:
    python .calibration/run_targeted_calibration.py --rerun-only --parallel

    # Aggregate only:
    python .calibration/run_targeted_calibration.py --aggregate-only

    # List all repos:
    python .calibration/run_targeted_calibration.py --list
"""

import argparse
import json
import multiprocessing
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPOS_DIR = PROJECT_ROOT / ".calibration" / "repos"
RUNS_DIR = PROJECT_ROOT / ".calibration" / "runs"
LOGS_DIR = PROJECT_ROOT / ".calibration" / "logs" / "v3"

# ─────────────────────────────────────────────────────────────────────
# v2 GITHUB REPOS — carried over from calibration v2
# ─────────────────────────────────────────────────────────────────────
GITHUB_REPOS_V2 = [
    ("vercel/next.js", "TypeScript"),
    ("facebook/react", "JavaScript"),
    ("microsoft/TypeScript", "TypeScript"),
    ("expressjs/express", "JavaScript"),
    ("remix-run/remix", "TypeScript"),
    ("vitejs/vite", "TypeScript"),
    ("django/django", "Python"),
    ("pallets/flask", "Python"),
    ("psf/requests", "Python"),
    ("pydantic/pydantic", "Python"),
    ("langchain-ai/langchain", "Python"),
    ("cli/cli", "Go"),
    ("containerd/containerd", "Go"),
    ("grafana/grafana", "Go"),
    ("hashicorp/terraform", "Go"),
    ("starship/starship", "Rust"),
    ("alacritty/alacritty", "Rust"),
    ("bevyengine/bevy", "Rust"),
    ("rails/rails", "Ruby"),
    ("mastodon/mastodon", "Ruby"),
    ("apache/kafka", "Java"),
    ("elastic/elasticsearch", "Java"),
]

# ─────────────────────────────────────────────────────────────────────
# PHASE A: Sentry-Focused Repos (NEW in v3)
# Use Sentry SDK + rich CI/deployment for cross-family patterns
# ─────────────────────────────────────────────────────────────────────
SENTRY_REPOS = [
    ("getsentry/sentry", "Python"),             # Sentry itself, pytest + coverage
    ("WeblateOrg/weblate", "Python"),           # sentry-sdk>=2.28.0, coverage XML
    ("zulip/zulip", "Python"),                  # sentry-sdk, pytest, coverage XML
    ("langgenius/dify", "Python"),              # sentry-sdk[flask], pytest
    ("saleor/saleor", "Python"),               # sentry-sdk~=2.12, JUnit XML
    ("n8n-io/n8n", "TypeScript"),              # @sentry/node, Jest coverage
    ("excalidraw/excalidraw", "TypeScript"),    # @sentry/browser, Vitest
    ("calcom/cal.com", "TypeScript"),           # @sentry/nextjs, Vitest
    ("novuhq/novu", "TypeScript"),             # @sentry/nestjs + @sentry/node
    ("supabase/supabase", "TypeScript"),        # @sentry/nextjs, Jest
    ("outline/outline", "TypeScript"),          # @sentry/node + @sentry/react
    ("go-gitea/gitea", "Go"),                  # SENTRY_DSN, Go test + coverage
    ("mattermost/mattermost", "Go"),           # sentry-go, Cypress + Playwright
    ("strapi/strapi", "TypeScript"),           # @sentry/node via plugin
    ("PostHog/posthog", "Python"),             # Sentry integration, pytest-split
]

# ─────────────────────────────────────────────────────────────────────
# PHASE B: Testing/Coverage-Rich Repos (some already cloned)
# Repos that commit JUnit XML or Cobertura XML reports
# ─────────────────────────────────────────────────────────────────────
TESTING_REPOS = [
    ("paperless-ngx/paperless-ngx", "Python"),  # junit.xml + coverage.xml
    ("django/django", "Python"),                # Already cloned, add testing walk
    ("pallets/flask", "Python"),                # Already cloned, add testing walk
    ("pydantic/pydantic", "Python"),            # Already cloned, add testing walk
    ("spring-projects/spring-boot", "Java"),    # Surefire JUnit XML, already cloned
    ("apache/kafka", "Java"),                   # JUnit XML in CI, already cloned
    ("elastic/elasticsearch", "Java"),          # JUnit XML, already cloned
    ("grafana/grafana", "Go"),                  # Go test reports, already cloned
    ("hashicorp/terraform", "Go"),              # Go test, already cloned
    ("microsoft/TypeScript", "TypeScript"),     # Already cloned, extensive tests
]

# ─────────────────────────────────────────────────────────────────────
# PHASE C: Re-run existing repos with testing + coverage families
# These have v2 calibration data but only dependency/schema/config walker
# Re-running will pick up testing + coverage from the updated walker
# ─────────────────────────────────────────────────────────────────────
RERUN_EXISTING = [
    # v2 repos that had API data (most valuable for cross-family)
    "rails/rails",
    "mastodon/mastodon",
    "electron/electron",
    "discourse/discourse",
    "Homebrew/brew",
    "angular/angular",
    "mui/material-ui",
    "hashicorp/vagrant",
    "spring-projects/spring-boot",
    "sveltejs/svelte",
    # Additional v2 repos worth re-running
    "vercel/next.js",
    "facebook/react",
    "expressjs/express",
    "vitejs/vite",
    "django/django",
    "pallets/flask",
    "psf/requests",
    "pydantic/pydantic",
    "langchain-ai/langchain",
    "cli/cli",
    "containerd/containerd",
    "grafana/grafana",
    "hashicorp/terraform",
    "starship/starship",
    "alacritty/alacritty",
    "bevyengine/bevy",
    "apache/kafka",
    "elastic/elasticsearch",
    "remix-run/remix",
    "microsoft/TypeScript",
]

# ─────────────────────────────────────────────────────────────────────
# PHASE D: GitLab repos — git + dependency only
# ─────────────────────────────────────────────────────────────────────
GITLAB_REPOS = [
    ("gitlab-org/gitlab-runner", "Go", "https://gitlab.com/gitlab-org/gitlab-runner.git"),
    ("inkscape/inkscape", "C++", "https://gitlab.com/inkscape/inkscape.git"),
    ("fdroid/fdroidclient", "Java", "https://gitlab.com/fdroid/fdroidclient.git"),
    ("gnome/gnome-shell", "JavaScript", "https://gitlab.gnome.org/GNOME/gnome-shell.git"),
    ("tortoisegit/tortoisegit", "C++", "https://gitlab.com/tortoisegit/tortoisegit.git"),
]


def _safe_dir(slug):
    return slug.replace("/", "--")


def clone_github_repo(slug, depth=2000):
    """Clone a GitHub repo (shallow, then unshallow)."""
    repo_dir = REPOS_DIR / _safe_dir(slug)
    if repo_dir.exists():
        print(f"  [clone] {slug} -- already exists")
        return repo_dir

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{slug}.git"
    print(f"  [clone] {slug} -- cloning (depth={depth})...")
    try:
        subprocess.run(
            ["git", "clone", "--depth", str(depth), url, str(repo_dir)],
            check=True, capture_output=True, timeout=600,
        )
        # Try to unshallow for better baseline computation
        subprocess.run(
            ["git", "fetch", "--unshallow"],
            cwd=str(repo_dir), capture_output=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        print(f"  [clone] {slug} -- timeout, using shallow")
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode()[:200] if e.stderr else str(e)
        print(f"  [clone] {slug} -- failed: {err}")
        return None
    return repo_dir


def clone_gitlab_repo(slug, url, depth=2000):
    """Clone a GitLab repo."""
    repo_dir = REPOS_DIR / f"gitlab--{_safe_dir(slug)}"
    if repo_dir.exists():
        print(f"  [clone] gitlab/{slug} -- already exists")
        return repo_dir

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  [clone] gitlab/{slug} -- cloning from {url}...")
    try:
        subprocess.run(
            ["git", "clone", "--depth", str(depth), url, str(repo_dir)],
            check=True, capture_output=True, timeout=600,
        )
        subprocess.run(
            ["git", "fetch", "--unshallow"],
            cwd=str(repo_dir), capture_output=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        print(f"  [clone] gitlab/{slug} -- timeout, using shallow")
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode()[:200] if e.stderr else str(e)
        print(f"  [clone] gitlab/{slug} -- failed: {err}")
        return None
    return repo_dir


def calibrate_repo(slug, repo_dir, run_name, skip_api=False):
    """Run calibration using the existing calibrate_repo module."""
    evo_dir = RUNS_DIR / run_name

    # Skip if already fully calibrated (has result file)
    result_file = evo_dir / "calibration_result.json"
    if result_file.exists():
        print(f"  [skip] {slug} -- already has calibration_result.json")
        with open(result_file) as f:
            return json.load(f)

    # Clean partial runs
    if evo_dir.exists() and not result_file.exists():
        import shutil
        print(f"  [clean] Removing partial run at {evo_dir}")
        shutil.rmtree(evo_dir)

    parts = slug.split("/", 1)
    owner, repo = parts[0], parts[1]

    try:
        from examples.calibrate_repo import run_calibration
        result = run_calibration(
            repo_path=str(repo_dir),
            owner=owner,
            repo=repo,
            evo_dir=evo_dir,
            skip_api=skip_api,
            enable_llm=False,
        )
        if result:
            result_file.parent.mkdir(parents=True, exist_ok=True)
            with open(result_file, "w") as f:
                json.dump(result, f, indent=2, default=str)
        return result
    except Exception as e:
        print(f"  [ERROR] {slug}: {e}")
        import traceback
        traceback.print_exc()
        return {"scope": slug, "error": str(e)}


def _calibrate_worker(args):
    """Top-level function for ProcessPoolExecutor.

    Must be top-level (not a lambda/closure) for pickling.
    Each worker process gets its own memory space, avoiding GIL and
    _CatFileContentStream thread-safety issues.
    """
    slug, repo_dir, run_name, skip_api = args

    # Re-add project root to sys.path in the child process
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    # Suppress LLM calls in child process
    os.environ["PHASE31_ENABLED"] = "false"
    os.environ["PHASE4B_ENABLED"] = "false"

    # Redirect output to per-repo log file
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"{_safe_dir(slug)}.log"
    with open(log_file, "w") as log:
        # Redirect stdout/stderr for this process
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = log
        sys.stderr = log
        try:
            result = calibrate_repo(slug, repo_dir, run_name, skip_api=skip_api)
            return slug, result, None
        except Exception as e:
            import traceback
            traceback.print_exc(file=log)
            return slug, {"scope": slug, "error": str(e)}, e
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr


def run_parallel(tasks, max_workers=None):
    """Run calibration tasks in parallel using ProcessPoolExecutor.

    Args:
        tasks: List of (slug, repo_dir, run_name, skip_api) tuples
        max_workers: Max parallel processes (default: min(cpu_count, 8))

    Returns:
        List of result dicts
    """
    if max_workers is None:
        # Limit to 8 to stay under GitHub API rate limit (5000 req/hr)
        max_workers = min(multiprocessing.cpu_count(), 8)

    total = len(tasks)
    results = []
    print(f"\n  Starting parallel calibration: {total} repos, {max_workers} workers")
    print(f"  Logs: {LOGS_DIR}/")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_slug = {}
        for task in tasks:
            future = executor.submit(_calibrate_worker, task)
            future_to_slug[future] = task[0]  # slug

        completed = 0
        for future in as_completed(future_to_slug):
            slug = future_to_slug[future]
            completed += 1
            try:
                _, result, error = future.result(timeout=1800)  # 30 min timeout per repo
                if error:
                    print(f"  [{completed}/{total}] {slug} -- FAILED: {error}")
                elif result and result.get("events", 0) > 0:
                    families = len(result.get("families", []))
                    signals = result.get("signals", 0)
                    elapsed = result.get("elapsed_seconds", 0)
                    print(f"  [{completed}/{total}] {slug} -- "
                          f"fam={families} sig={signals} ({elapsed:.0f}s)")
                else:
                    print(f"  [{completed}/{total}] {slug} -- no events")
                results.append(result)
            except Exception as e:
                print(f"  [{completed}/{total}] {slug} -- EXCEPTION: {e}")
                results.append({"scope": slug, "error": str(e)})

    return results


def run_aggregation():
    """Run the aggregation script to update universal_patterns.json."""
    print("\n" + "=" * 70)
    print("AGGREGATING PATTERNS")
    print("=" * 70)

    agg_script = PROJECT_ROOT / "scripts" / "aggregate_calibration.py"
    if not agg_script.exists():
        print(f"  Aggregation script not found: {agg_script}")
        return

    result = subprocess.run(
        [sys.executable, str(agg_script), "--verbose", "--min-repos", "1"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


def print_summary(results):
    """Print calibration summary."""
    print("\n" + "=" * 70)
    print("CALIBRATION v3 SUMMARY")
    print("=" * 70)

    successful = [r for r in results if r and "error" not in r and r.get("events", 0) > 0]
    failed = [r for r in results if not r or "error" in r or r.get("events", 0) == 0]

    print(f"\nSuccessful: {len(successful)}")
    print(f"Failed:     {len(failed)}")

    # Family coverage
    all_families = set()
    family_repo_count = {}
    for r in successful:
        families = r.get("families", [])
        all_families.update(families)
        for f in families:
            family_repo_count[f] = family_repo_count.get(f, 0) + 1

    print(f"\nFamily coverage across {len(successful)} repos:")
    for f in sorted(family_repo_count, key=lambda x: family_repo_count[x], reverse=True):
        bar = "#" * family_repo_count[f]
        print(f"  {f:20s} {family_repo_count[f]:3d} repos  {bar}")

    # Highlight new families
    new_families = {"testing", "coverage", "error_tracking"}
    found_new = new_families & set(family_repo_count.keys())
    if found_new:
        print(f"\n  NEW v3 families found: {', '.join(sorted(found_new))}")
    else:
        print(f"\n  WARNING: No new v3 families (testing/coverage/error_tracking) found")

    # Multi-family repos
    multi = [r for r in successful if len(r.get("families", [])) >= 3]
    print(f"\nMulti-family repos (>=3 families): {len(multi)}")
    for r in sorted(multi, key=lambda x: len(x.get("families", [])), reverse=True):
        fams = ", ".join(r.get("families", []))
        patterns = r.get("phase4", {}).get("patterns_discovered", 0)
        print(f"  {r['scope']:45s} [{fams}] -> {patterns} patterns")

    print("\nPer-repo details:")
    for r in sorted(successful, key=lambda x: x.get("phase4", {}).get("patterns_discovered", 0), reverse=True):
        p4 = r.get("phase4", {})
        patterns = p4.get("patterns_discovered", 0)
        fams = len(r.get("families", []))
        events = r.get("events", 0)
        sigs = r.get("signals", 0)
        elapsed = r.get("elapsed_seconds", 0)
        fam_list = r.get("families", [])
        has_new = "+" if any(f in new_families for f in fam_list) else " "
        print(f"  {has_new} {r['scope']:44s} "
              f"fam={fams} ev={events:6d} sig={sigs:6d} pat={patterns} ({elapsed:.0f}s)")

    for r in failed:
        scope = r.get("scope", "?") if r else "?"
        err = r.get("error", "unknown") if r else "calibration returned None"
        print(f"  X {scope:44s} {str(err)[:60]}")


def _find_repo_dir(slug):
    """Find existing repo directory for a slug."""
    candidates = [
        REPOS_DIR / _safe_dir(slug),
        REPOS_DIR / slug.split("/")[1],  # Just repo name (old format)
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Calibration v3 — 9 families across 130+ repos"
    )
    parser.add_argument("--list", action="store_true", help="List repos and exit")
    parser.add_argument("--parallel", action="store_true",
                        help="Run calibration in parallel (ProcessPoolExecutor)")
    parser.add_argument("--workers", type=int, default=None,
                        help="Max parallel workers (default: min(cpu_count, 8))")
    parser.add_argument("--sentry-only", action="store_true",
                        help="Only run Phase A: Sentry repos")
    parser.add_argument("--testing-only", action="store_true",
                        help="Only run Phase B: Testing/coverage repos")
    parser.add_argument("--rerun-only", action="store_true",
                        help="Only run Phase C: Re-run existing repos")
    parser.add_argument("--gitlab-only", action="store_true",
                        help="Only run Phase D: GitLab repos")
    parser.add_argument("--github-only", action="store_true",
                        help="Only run Phase A + B (GitHub repos)")
    parser.add_argument("--aggregate-only", action="store_true",
                        help="Only run aggregation")
    parser.add_argument("--no-aggregate", action="store_true",
                        help="Skip aggregation at end")
    parser.add_argument("--skip-clone-errors", action="store_true",
                        help="Continue on clone failures")
    parser.add_argument("--force-rerun", action="store_true",
                        help="Re-run even if calibration_result.json exists")
    args = parser.parse_args()

    # ── List mode ──
    if args.list:
        print("=== Phase A: Sentry repos (NEW) ===")
        for slug, lang in SENTRY_REPOS:
            cloned = "C" if _find_repo_dir(slug) else " "
            calibrated = "R" if (RUNS_DIR / _safe_dir(slug)).exists() else " "
            print(f"  [{cloned}{calibrated}] {slug:45s} {lang}")

        print(f"\n=== Phase B: Testing/Coverage repos ===")
        for slug, lang in TESTING_REPOS:
            cloned = "C" if _find_repo_dir(slug) else " "
            run_name = f"{_safe_dir(slug)}-v3"
            calibrated = "R" if (RUNS_DIR / run_name).exists() else " "
            print(f"  [{cloned}{calibrated}] {slug:45s} {lang}")

        print(f"\n=== Phase C: Re-run existing with testing+coverage ===")
        for slug in RERUN_EXISTING:
            cloned = "C" if _find_repo_dir(slug) else " "
            run_name = f"{_safe_dir(slug)}-v3"
            calibrated = "R" if (RUNS_DIR / run_name).exists() else " "
            print(f"  [{cloned}{calibrated}] {slug:45s}")

        print(f"\n=== Phase D: GitLab repos ===")
        for slug, lang, url in GITLAB_REPOS:
            cloned = "C" if (REPOS_DIR / f"gitlab--{_safe_dir(slug)}").exists() else " "
            calibrated = "R" if (RUNS_DIR / f"gitlab--{_safe_dir(slug)}-v3").exists() else " "
            print(f"  [{cloned}{calibrated}] gitlab/{slug:40s} {lang}")

        print("\n  Legend: C=cloned, R=calibrated")
        return

    if args.aggregate_only:
        run_aggregation()
        return

    # ── Token setup ──
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                token = result.stdout.strip()
                os.environ["GITHUB_TOKEN"] = token
                print(f"Got GITHUB_TOKEN from gh CLI (length={len(token)})")
        except Exception:
            pass

    if not token and not args.gitlab_only:
        print("WARNING: No GITHUB_TOKEN. GitHub repos will only get git + dependency signals.")
        print("   For full calibration: export GITHUB_TOKEN=$(gh auth token)")

    if token:
        try:
            result = subprocess.run(
                ["gh", "api", "rate_limit", "--jq",
                 '.resources.core | "\\(.remaining)/\\(.limit)"'],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                print(f"GitHub API rate limit: {result.stdout.strip()}")
        except Exception:
            pass

    # Determine which phases to run
    run_a = not any([args.testing_only, args.rerun_only, args.gitlab_only])
    run_b = not any([args.sentry_only, args.rerun_only, args.gitlab_only])
    run_c = not any([args.sentry_only, args.testing_only, args.gitlab_only, args.github_only])
    run_d = not any([args.sentry_only, args.testing_only, args.rerun_only, args.github_only])

    # Override for specific flags
    if args.sentry_only:
        run_a, run_b, run_c, run_d = True, False, False, False
    if args.testing_only:
        run_a, run_b, run_c, run_d = False, True, False, False
    if args.rerun_only:
        run_a, run_b, run_c, run_d = False, False, True, False
    if args.gitlab_only:
        run_a, run_b, run_c, run_d = False, False, False, True

    all_results = []
    start_time = time.time()
    parallel_tasks = []  # Collect tasks for parallel mode

    # ── Phase A: Sentry-Focused Repos ──
    if run_a:
        print("\n" + "=" * 70)
        print(f"PHASE A: SENTRY REPOS ({len(SENTRY_REPOS)} repos)")
        print("=" * 70)

        for slug, lang in SENTRY_REPOS:
            repo_dir = _find_repo_dir(slug)
            if not repo_dir:
                print(f"\n  Cloning {slug}...")
                repo_dir = clone_github_repo(slug)
            if not repo_dir:
                if args.skip_clone_errors:
                    all_results.append({"scope": slug, "error": "clone failed"})
                    continue
                print(f"  Failed to clone {slug}, stopping Phase A.")
                break

            run_name = _safe_dir(slug)
            if args.force_rerun:
                # Remove existing result to force re-run
                result_file = RUNS_DIR / run_name / "calibration_result.json"
                if result_file.exists():
                    result_file.unlink()

            if args.parallel:
                parallel_tasks.append((slug, str(repo_dir), run_name, False))
            else:
                print(f"\n--- [{len(all_results)+1}] {slug} ({lang}) ---")
                result = calibrate_repo(slug, repo_dir, run_name)
                all_results.append(result)

    # ── Phase B: Testing/Coverage Repos ──
    if run_b:
        print("\n" + "=" * 70)
        print(f"PHASE B: TESTING/COVERAGE REPOS ({len(TESTING_REPOS)} repos)")
        print("=" * 70)

        for slug, lang in TESTING_REPOS:
            repo_dir = _find_repo_dir(slug)
            if not repo_dir:
                print(f"\n  Cloning {slug}...")
                repo_dir = clone_github_repo(slug)
            if not repo_dir:
                if args.skip_clone_errors:
                    all_results.append({"scope": slug, "error": "clone failed"})
                    continue
                print(f"  Failed to clone {slug}, continuing...")
                all_results.append({"scope": slug, "error": "clone failed"})
                continue

            # Use -v3 suffix to avoid overwriting v2 results
            run_name = f"{_safe_dir(slug)}-v3"
            if args.force_rerun:
                result_file = RUNS_DIR / run_name / "calibration_result.json"
                if result_file.exists():
                    result_file.unlink()

            if args.parallel:
                parallel_tasks.append((slug, str(repo_dir), run_name, False))
            else:
                print(f"\n--- [{len(all_results)+1}] {slug} ({lang}) ---")
                result = calibrate_repo(slug, repo_dir, run_name)
                all_results.append(result)

    # ── Phase C: Re-run Existing Repos ──
    if run_c:
        print("\n" + "=" * 70)
        print(f"PHASE C: RE-RUN EXISTING ({len(RERUN_EXISTING)} repos)")
        print("=" * 70)

        for slug in RERUN_EXISTING:
            repo_dir = _find_repo_dir(slug)
            if not repo_dir:
                print(f"  {slug} -- not cloned, skipping")
                continue

            # Use -v3 suffix for re-runs
            run_name = f"{_safe_dir(slug)}-v3"
            if args.force_rerun:
                result_file = RUNS_DIR / run_name / "calibration_result.json"
                if result_file.exists():
                    result_file.unlink()

            if args.parallel:
                parallel_tasks.append((slug, str(repo_dir), run_name, False))
            else:
                print(f"\n--- [{len(all_results)+1}] {slug} (re-run v3) ---")
                result = calibrate_repo(slug, repo_dir, run_name)
                all_results.append(result)

    # ── Phase D: GitLab Repos ──
    if run_d:
        print("\n" + "=" * 70)
        print(f"PHASE D: GITLAB REPOS ({len(GITLAB_REPOS)} repos)")
        print("=" * 70)

        for slug, lang, url in GITLAB_REPOS:
            repo_dir = REPOS_DIR / f"gitlab--{_safe_dir(slug)}"
            if not repo_dir.exists():
                repo_dir = clone_gitlab_repo(slug, url)
            if not repo_dir:
                all_results.append({"scope": f"gitlab/{slug}", "error": "clone failed"})
                continue

            run_name = f"gitlab--{_safe_dir(slug)}-v3"
            if args.force_rerun:
                result_file = RUNS_DIR / run_name / "calibration_result.json"
                if result_file.exists():
                    result_file.unlink()

            if args.parallel:
                parallel_tasks.append((slug, str(repo_dir), run_name, True))
            else:
                print(f"\n--- [{len(all_results)+1}] gitlab/{slug} ({lang}) ---")
                result = calibrate_repo(slug, repo_dir, run_name, skip_api=True)
                all_results.append(result)

    # ── Execute parallel tasks ──
    if args.parallel and parallel_tasks:
        # Deduplicate by run_name (same repo might appear in multiple phases)
        seen_runs = set()
        deduped = []
        for task in parallel_tasks:
            run_name = task[2]
            if run_name not in seen_runs:
                seen_runs.add(run_name)
                deduped.append(task)
            else:
                print(f"  [dedup] Skipping duplicate: {task[0]} ({run_name})")
        parallel_tasks = deduped

        parallel_results = run_parallel(parallel_tasks, max_workers=args.workers)
        all_results.extend(parallel_results)

    # ── Summary ──
    elapsed_total = time.time() - start_time
    print(f"\n\nTotal calibration time: {elapsed_total/60:.1f} minutes")
    print_summary(all_results)

    # ── Aggregation ──
    if not args.no_aggregate:
        run_aggregation()

    # Save results
    results_file = PROJECT_ROOT / ".calibration" / "calibration_v3_results.json"
    with open(results_file, "w") as f:
        json.dump({
            "version": "v3",
            "timestamp": datetime.now().isoformat(),
            "elapsed_minutes": round(elapsed_total / 60, 1),
            "parallel": args.parallel,
            "workers": args.workers or min(multiprocessing.cpu_count(), 8),
            "results": [r for r in all_results if r],
        }, f, indent=2, default=str)
    print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    main()
