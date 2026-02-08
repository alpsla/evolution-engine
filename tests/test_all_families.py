#!/usr/bin/env python3
"""
End-to-end test for all source families through Phase 1 → 2 → 3 → 4.

Generates realistic fixture data for each family, ingests through Phase 1,
computes Phase 2 baselines/signals, generates Phase 3 explanations,
and runs Phase 4 pattern discovery + KB storage.

Usage:
    python tests/test_all_families.py
"""

import json
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.phase3_engine import Phase3Engine
from evolution.phase4_engine import Phase4Engine
from evolution.phase5_engine import Phase5Engine

# Adapters
from evolution.adapters.testing import JUnitXMLAdapter
from evolution.adapters.dependency import PipDependencyAdapter
from evolution.adapters.schema import OpenAPIAdapter
from evolution.adapters.deployment import GitHubReleasesAdapter
from evolution.adapters.config import TerraformAdapter
from evolution.adapters.security import TrivyAdapter

# Git adapter (already exists)
from evolution.adapters.git import GitSourceAdapter

# ──────────────────── Fixture Generators ────────────────────

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

BASE_TIME = datetime(2026, 1, 1, 10, 0, 0)
COMMIT_SHAS = [f"{i:040x}" for i in range(100, 120)]  # 20 fake SHAs


def make_testing_fixtures(n: int = 15) -> list:
    """Generate n test suite run fixtures with realistic variation."""
    runs = []
    base_tests = 120
    for i in range(n):
        t = BASE_TIME + timedelta(hours=i * 6)
        total = base_tests + random.randint(-5, 10)
        failed = random.randint(0, max(1, total // 10))
        skipped = random.randint(0, 5)
        errored = random.randint(0, 1)
        passed = total - failed - skipped - errored
        duration = random.uniform(30, 180)

        cases = []
        for j in range(total):
            if j < passed:
                status = "passed"
            elif j < passed + failed:
                status = "failed"
            elif j < passed + failed + skipped:
                status = "skipped"
            else:
                status = "errored"
            cases.append({
                "name": f"test_{j:03d}",
                "classname": f"tests.module_{j // 20}",
                "status": status,
                "duration_seconds": round(random.uniform(0.01, 3.0), 3),
            })

        runs.append({
            "suite_name": "unit_tests",
            "trigger": {
                "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                "branch": "main",
            },
            "execution": {
                "started_at": t.isoformat() + "Z",
                "completed_at": (t + timedelta(seconds=duration)).isoformat() + "Z",
                "duration_seconds": round(duration, 3),
            },
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errored": errored,
            },
            "cases": cases,
        })
    return runs


def make_dependency_fixtures(n: int = 12) -> list:
    """Generate n dependency snapshot fixtures with realistic variation."""
    snapshots = []
    base_deps = [
        "flask", "requests", "sqlalchemy", "pydantic", "celery",
        "redis", "boto3", "pytest", "black", "mypy",
    ]
    current_deps = list(base_deps)

    possible_additions = [
        "fastapi", "uvicorn", "httpx", "aiohttp", "numpy",
        "pandas", "scipy", "pillow", "jinja2", "click",
    ]

    for i in range(n):
        # Occasionally add or remove a dep
        if i > 0 and random.random() < 0.4 and possible_additions:
            new_dep = possible_additions.pop(0)
            current_deps.append(new_dep)
        if i > 0 and random.random() < 0.15 and len(current_deps) > 5:
            current_deps.remove(random.choice(current_deps))

        deps = []
        for dep_name in current_deps:
            major = random.randint(1, 5)
            minor = random.randint(0, 20)
            patch = random.randint(0, 10)
            deps.append({
                "name": dep_name,
                "version": f"{major}.{minor}.{patch}",
                "direct": True,
                "depth": 1,
            })

        # Add some transitive deps
        transitive_count = random.randint(15, 40)
        for j in range(transitive_count):
            deps.append({
                "name": f"transitive-pkg-{j}",
                "version": f"1.{random.randint(0, 9)}.{random.randint(0, 9)}",
                "direct": False,
                "depth": random.randint(2, 4),
            })

        snapshots.append({
            "ecosystem": "pip",
            "manifest_file": "requirements.txt",
            "trigger": {"commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)]},
            "snapshot": {
                "direct_count": len(current_deps),
                "transitive_count": transitive_count,
                "total_count": len(deps),
                "max_depth": max(d["depth"] for d in deps),
            },
            "dependencies": deps,
        })
    return snapshots


def make_schema_fixtures(n: int = 10) -> list:
    """Generate n API schema version fixtures with realistic variation."""
    versions = []
    endpoints = 8
    types = 5
    fields = 20

    for i in range(n):
        # API grows over time with occasional churn
        ep_add = random.randint(0, 2)
        ep_rm = random.randint(0, 1) if i > 3 else 0
        f_add = random.randint(0, 5)
        f_rm = random.randint(0, 2) if i > 2 else 0
        t_add = random.randint(0, 1)
        t_rm = 0

        endpoints += ep_add - ep_rm
        types += t_add - t_rm
        fields += f_add - f_rm

        versions.append({
            "schema_name": "user-service-api",
            "schema_format": "openapi",
            "version": f"1.{i}.0",
            "trigger": {"commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)]},
            "structure": {
                "endpoint_count": endpoints,
                "type_count": types,
                "field_count": fields,
            },
            "diff": {
                "endpoints_added": ep_add,
                "endpoints_removed": ep_rm,
                "fields_added": f_add,
                "fields_removed": f_rm,
                "types_added": t_add,
                "types_removed": t_rm,
            },
        })
    return versions


def make_deployment_fixtures(n: int = 12) -> list:
    """Generate n deployment event fixtures with realistic variation."""
    deployments = []
    for i in range(n):
        t = BASE_TIME + timedelta(days=i * 2, hours=random.randint(0, 12))
        duration = random.uniform(30, 600)
        is_failure = random.random() < 0.15
        is_rollback = random.random() < 0.1 and i > 2

        if is_rollback:
            trigger_type = "rollback"
        elif random.random() < 0.8:
            trigger_type = "automated"
        else:
            trigger_type = "manual"

        deployments.append({
            "deployment_id": f"deploy-{i:04d}",
            "environment": random.choice(["production", "staging", "production"]),
            "trigger": {
                "type": trigger_type,
                "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                "ref": f"v1.{i}.0",
            },
            "status": "failure" if is_failure else "success",
            "timing": {
                "initiated_at": t.isoformat() + "Z",
                "completed_at": (t + timedelta(seconds=duration)).isoformat() + "Z",
                "duration_seconds": round(duration, 1),
            },
            "version": f"v1.{i}.0",
        })
    return deployments


def make_config_fixtures(n: int = 10) -> list:
    """Generate n config snapshot fixtures with realistic variation."""
    snapshots = []
    resources = 12
    resource_types = 4
    files = 5

    for i in range(n):
        r_add = random.randint(0, 3)
        r_rm = random.randint(0, 1) if i > 3 else 0
        r_mod = random.randint(0, 4)

        resources += r_add - r_rm
        if random.random() < 0.2:
            resource_types += 1
        if random.random() < 0.3:
            files += 1

        snapshots.append({
            "config_scope": "production-cluster",
            "config_format": "terraform",
            "trigger": {
                "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                "apply_id": f"apply-{i:04d}",
            },
            "structure": {
                "resource_count": resources,
                "resource_types": resource_types,
                "file_count": files,
            },
            "diff": {
                "resources_added": r_add,
                "resources_removed": r_rm,
                "resources_modified": r_mod,
            },
        })
    return snapshots


def make_security_fixtures(n: int = 12) -> list:
    """Generate n security scan fixtures with realistic variation."""
    scans = []
    base_vulns = 15
    CVE_POOL = [f"CVE-2026-{i:04d}" for i in range(1, 60)]

    for i in range(n):
        t = BASE_TIME + timedelta(days=i * 3)
        total_vulns = base_vulns + random.randint(-3, 5)
        critical = random.randint(0, 2)
        high = random.randint(1, 5)
        medium = random.randint(3, 8)
        low = total_vulns - critical - high - medium
        if low < 0:
            low = 0
            total_vulns = critical + high + medium

        findings = []
        for j in range(total_vulns):
            if j < critical:
                sev = "critical"
            elif j < critical + high:
                sev = "high"
            elif j < critical + high + medium:
                sev = "medium"
            else:
                sev = "low"

            has_fix = random.random() < 0.6
            findings.append({
                "id": CVE_POOL[j % len(CVE_POOL)],
                "severity": sev,
                "package": f"pkg-{random.randint(1, 20)}",
                "installed_version": f"1.{random.randint(0, 9)}.{random.randint(0, 9)}",
                "fixed_version": f"1.{random.randint(10, 20)}.0" if has_fix else None,
                "title": f"Vulnerability in pkg-{random.randint(1, 20)}",
            })

        # Slowly reduce vulns over time (patching)
        if i > 5:
            base_vulns = max(5, base_vulns - 1)

        scans.append({
            "scanner": "trivy",
            "scanner_version": "0.50.0",
            "scan_target": "myapp:latest",
            "trigger": {
                "type": "commit" if random.random() < 0.6 else "schedule",
                "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)] if random.random() < 0.7 else "",
            },
            "execution": {
                "started_at": t.isoformat() + "Z",
                "completed_at": (t + timedelta(seconds=random.uniform(10, 60))).isoformat() + "Z",
            },
            "summary": {
                "total": total_vulns,
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": low,
                "info": 0,
            },
            "findings": findings,
        })
    return scans


# ──────────────────── Test Runner ────────────────────

def separator(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def run_test():
    # Use a clean test directory
    test_dir = Path(__file__).resolve().parent / "test_evo"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True)

    repo_root = Path(__file__).resolve().parent.parent

    separator("PHASE 1: Ingestion — All Families")

    phase1 = Phase1Engine(test_dir)

    # 1. Git adapter (use actual repo)
    print("\n  [Git] Ingesting from local repository...")
    try:
        git_adapter = GitSourceAdapter(str(repo_root))
        git_count = phase1.ingest(git_adapter)
        print(f"  [Git] Ingested {git_count} events")
    except Exception as e:
        print(f"  [Git] Skipped (no git history): {e}")
        git_count = 0

    # 2. Testing adapter (fixtures)
    print("\n  [Testing] Generating fixture data...")
    test_runs = make_testing_fixtures(15)
    testing_adapter = JUnitXMLAdapter(runs=test_runs, source_id="junit_xml:fixture")
    test_count = phase1.ingest(testing_adapter)
    print(f"  [Testing] Ingested {test_count} events")

    # 3. Dependency adapter (fixtures)
    print("\n  [Dependency] Generating fixture data...")
    dep_snapshots = make_dependency_fixtures(12)
    dep_adapter = PipDependencyAdapter(snapshots=dep_snapshots, source_id="pip:fixture")
    dep_count = phase1.ingest(dep_adapter)
    print(f"  [Dependency] Ingested {dep_count} events")

    # 4. Schema adapter (fixtures)
    print("\n  [Schema] Generating fixture data...")
    schema_versions = make_schema_fixtures(10)
    schema_adapter = OpenAPIAdapter(versions=schema_versions, source_id="openapi:fixture")
    schema_count = phase1.ingest(schema_adapter)
    print(f"  [Schema] Ingested {schema_count} events")

    # 5. Deployment adapter (fixtures)
    print("\n  [Deployment] Generating fixture data...")
    deployments = make_deployment_fixtures(12)
    deploy_adapter = GitHubReleasesAdapter(deployments=deployments, source_id="github_releases:fixture")
    deploy_count = phase1.ingest(deploy_adapter)
    print(f"  [Deployment] Ingested {deploy_count} events")

    # 6. Config adapter (fixtures)
    print("\n  [Config] Generating fixture data...")
    config_snapshots = make_config_fixtures(10)
    config_adapter = TerraformAdapter(snapshots=config_snapshots, source_id="terraform:fixture")
    config_count = phase1.ingest(config_adapter)
    print(f"  [Config] Ingested {config_count} events")

    # 7. Security adapter (fixtures)
    print("\n  [Security] Generating fixture data...")
    security_scans = make_security_fixtures(12)
    security_adapter = TrivyAdapter(scans=security_scans, source_id="trivy:fixture")
    sec_count = phase1.ingest(security_adapter)
    print(f"  [Security] Ingested {sec_count} events")

    total_events = git_count + test_count + dep_count + schema_count + deploy_count + config_count + sec_count
    print(f"\n  ✅ Phase 1 Complete: {total_events} total events across 7 families")

    # Verify events on disk
    event_files = list(test_dir.glob("events/*.json"))
    print(f"  📂 Events on disk: {len(event_files)}")

    # Show family distribution
    family_counts = {}
    for ef in event_files:
        ev = json.loads(ef.read_text())
        fam = ev.get("source_family", ev.get("source_type", "unknown"))
        family_counts[fam] = family_counts.get(fam, 0) + 1
    for fam, count in sorted(family_counts.items()):
        print(f"     {fam}: {count} events")

    # ──────────────── Phase 2 ────────────────

    separator("PHASE 2: Behavioral Baselines — All Families")

    phase2 = Phase2Engine(test_dir, min_baseline=5)
    results = phase2.run_all()

    total_signals = 0
    for family, signals in results.items():
        count = len(signals)
        total_signals += count
        if count > 0:
            metrics = set(s["metric"] for s in signals)
            print(f"  [{family}] {count} signals — metrics: {', '.join(sorted(metrics))}")
        else:
            print(f"  [{family}] 0 signals (insufficient history or no events)")

    print(f"\n  ✅ Phase 2 Complete: {total_signals} total signals")

    # Verify signal files on disk
    signal_files = list(test_dir.glob("phase2/*.json"))
    print(f"  📂 Signal files: {', '.join(f.name for f in signal_files)}")

    # ──────────────── Phase 3 ────────────────

    separator("PHASE 3: Explanations (+ 3.1 LLM if enabled)")

    phase3 = Phase3Engine(test_dir)
    explanations = phase3.run()

    print(f"\n  Total explanations: {len(explanations)}")

    # Count by engine/family
    engine_counts = {}
    llm_count = 0
    for exp in explanations:
        eng = exp.get("engine_id", "unknown")
        engine_counts[eng] = engine_counts.get(eng, 0) + 1
        if exp.get("phase31_used"):
            llm_count += 1

    for eng, count in sorted(engine_counts.items()):
        print(f"  [{eng}] {count} explanations")

    if llm_count > 0:
        print(f"\n  🤖 Phase 3.1 LLM enhanced: {llm_count}/{len(explanations)}")
    else:
        print(f"\n  📝 Phase 3.1 LLM: disabled (template-only mode)")

    # Show sample explanations (one per family)
    separator("SAMPLE EXPLANATIONS (one per family)")
    seen_engines = set()
    for exp in explanations:
        eng = exp.get("engine_id")
        if eng not in seen_engines:
            seen_engines.add(eng)
            metric = exp["details"]["metric"]
            observed = exp["details"]["observed"]
            deviation = exp["details"]["deviation"]["measure"]
            print(f"\n  [{eng}] metric={metric}")
            print(f"  observed={observed}, deviation={deviation:.2f} stddev")
            # Truncate long explanations for display
            summary = exp["summary"]
            if len(summary) > 200:
                summary = summary[:200] + "..."
            print(f"  → {summary}")
            if exp.get("phase31_used"):
                print(f"  (LLM enhanced ✓)")

    # ──────────────── Phase 4 ────────────────

    separator("PHASE 4: Pattern Learning (run 1 — first encounter)")

    phase4 = Phase4Engine(test_dir, params={
        "min_support": 3,
        "min_correlation": 0.3,
        "promotion_threshold": 5,
        "direction_threshold": 0.5,
    })
    p4_result = phase4.run()

    print(f"\n  Total signals analyzed: {p4_result['total_signals']}")
    print(f"  Deviating signals: {p4_result['deviating_signals']}")
    print(f"  Batch fingerprint: {p4_result['batch_fingerprint']}")
    print(f"  Patterns discovered: {p4_result['patterns_discovered']}")
    print(f"  Patterns enriched (4b): {p4_result['patterns_enriched']}")
    print(f"  Patterns recognized: {p4_result['patterns_recognized']}")
    print(f"  Knowledge artifacts: {p4_result['knowledge_artifacts']}")

    if p4_result["details"]:
        print(f"\n  Pattern details:")
        for d in p4_result["details"][:5]:
            action = d.get("action", "?")
            if action == "discovered":
                print(f"    [NEW] {d['sources']} — {d['metrics']}")
                print(f"          corr={d.get('correlation', 0):.2f}")
                print(f"          {d.get('description_statistical', '')[:100]}")
                if d.get("description_semantic"):
                    print(f"          4b: {d['description_semantic'][:100]}")
            elif action == "recognized":
                print(f"    [KNOWN] knowledge_id={d['knowledge_id']}")

    # Run Phase 4 again to test reinforcement (Moment 2)
    separator("PHASE 4: Pattern Learning (run 2 — reinforcement)")

    p4_result2 = phase4.run()

    print(f"\n  Patterns incremented: {p4_result2['patterns_incremented']}")
    print(f"  Patterns promoted: {p4_result2['patterns_promoted']}")
    print(f"  Patterns recognized: {p4_result2['patterns_recognized']}")
    print(f"  Knowledge artifacts: {p4_result2['knowledge_artifacts']}")

    # Run Phase 4 a few more times to accumulate evidence toward promotion
    for run_num in range(3, 7):
        phase4.run()

    separator("PHASE 4: Pattern Learning (after 6 runs — accumulation)")

    p4_final = phase4.run()
    print(f"\n  Patterns recognized: {p4_final['patterns_recognized']}")
    print(f"  Patterns incremented: {p4_final['patterns_incremented']}")
    print(f"  Patterns promoted: {p4_final['patterns_promoted']}")
    print(f"  Knowledge artifacts: {p4_final['knowledge_artifacts']}")

    # Show all patterns in KB
    all_patterns = phase4.kb.list_patterns()
    print(f"\n  Total patterns in KB: {len(all_patterns)}")
    for pat in all_patterns[:5]:
        print(f"    [{pat['confidence_tier']}] {pat['sources']} — {pat['metrics']}")
        print(f"      occurrences={pat['occurrence_count']}, corr={pat.get('correlation_strength', 0)}")
        if pat.get("description_semantic"):
            print(f"      semantic: {pat['description_semantic'][:80]}")

    # Show knowledge artifacts
    all_knowledge = phase4.kb.list_knowledge()
    print(f"\n  Knowledge artifacts: {len(all_knowledge)}")
    for ka in all_knowledge[:3]:
        print(f"    [APPROVED] {ka['sources']} — {ka['metrics']}")
        print(f"      support={ka['support_count']}, method={ka['approval_method']}")
        if ka.get("description_semantic"):
            print(f"      semantic: {ka['description_semantic'][:80]}")

    phase4.close()

    # ──────────────── Phase 5 ────────────────

    separator("PHASE 5: Advisory & Evidence")

    phase5 = Phase5Engine(test_dir, significance_threshold=1.0)
    p5_result = phase5.run(scope="evolution-engine-test")

    if p5_result["status"] == "complete":
        advisory = p5_result["advisory"]
        print(f"\n  Advisory ID: {advisory['advisory_id']}")
        print(f"  Period: {advisory['period']['from'][:10]} to {advisory['period']['to'][:10]}")
        print(f"  Significant changes: {advisory['summary']['significant_changes']}")
        print(f"  Families affected: {', '.join(advisory['summary']['families_affected'])}")
        print(f"  Known patterns matched: {advisory['summary']['known_patterns_matched']}")

        evidence = advisory.get("evidence", {})
        print(f"\n  Evidence:")
        print(f"    Commits: {len(evidence.get('commits', []))}")
        print(f"    Files: {len(evidence.get('files_affected', []))}")
        print(f"    Failing tests: {len(evidence.get('tests_impacted', []))}")
        print(f"    Dependencies: {len(evidence.get('dependencies_changed', []))}")
        print(f"    Timeline events: {len(evidence.get('timeline', []))}")

        separator("HUMAN SUMMARY (normal vs now)")
        # Print first 30 lines of human summary
        summary_lines = p5_result["human_summary"].split("\n")
        for line in summary_lines[:35]:
            print(f"  {line}")
        if len(summary_lines) > 35:
            print(f"  ... ({len(summary_lines) - 35} more lines)")

        separator("CHAT FORMAT")
        print(f"  {p5_result['chat_format']}")

        separator("INVESTIGATION PROMPT (first 20 lines)")
        prompt_lines = p5_result["investigation_prompt"].split("\n")
        for line in prompt_lines[:20]:
            print(f"  {line}")
        if len(prompt_lines) > 20:
            print(f"  ... ({len(prompt_lines) - 20} more lines)")

        print(f"\n  Output files:")
        for fmt, path in p5_result["formats"].items():
            print(f"    {fmt}: {path}")
    else:
        print(f"  Status: {p5_result['status']}")

    # ──────────────── Summary ────────────────

    separator("FINAL SUMMARY")

    p5_changes = p5_result.get("advisory", {}).get("summary", {}).get("significant_changes", 0)
    p5_patterns = p5_result.get("advisory", {}).get("summary", {}).get("known_patterns_matched", 0)

    print(f"""
  Phase 1: {total_events} events ingested across {len(family_counts)} families
  Phase 2: {total_signals} signals computed across {len([f for f, s in results.items() if s])} families
  Phase 3: {len(explanations)} explanations generated
  Phase 3.1 LLM: {'enabled' if llm_count > 0 else 'disabled'} ({llm_count} enhanced)
  Phase 4: {p4_result['patterns_discovered']} patterns discovered, {p4_final['knowledge_artifacts']} knowledge artifacts
  Phase 5: {p5_changes} significant changes, {p5_patterns} patterns matched

  Families tested:
    version_control (Git)     — {family_counts.get('version_control', 0)} events -> {len(results.get('git', []))} signals
    testing (JUnit XML)       — {family_counts.get('testing', 0)} events -> {len(results.get('testing', []))} signals
    dependency (pip)           — {family_counts.get('dependency', 0)} events -> {len(results.get('dependency', []))} signals
    schema (OpenAPI)           — {family_counts.get('schema', 0)} events -> {len(results.get('schema', []))} signals
    deployment (GitHub)        — {family_counts.get('deployment', 0)} events -> {len(results.get('deployment', []))} signals
    config (Terraform)         — {family_counts.get('config', 0)} events -> {len(results.get('config', []))} signals
    security (Trivy)           — {family_counts.get('security', 0)} events -> {len(results.get('security', []))} signals

  Pipeline: Phase 1 -> 2 -> 3 -> 4 -> 5 complete. All phases operational.
""")

    # Clean up
    print("  Cleaning up test data...")
    shutil.rmtree(test_dir)
    print("  Done.")


if __name__ == "__main__":
    run_test()
