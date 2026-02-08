#!/usr/bin/env python3
"""
Phase 4b Model Comparison — Haiku vs Sonnet 4.5

Runs the pipeline through Phase 1-3, discovers patterns with Phase 4a,
then interprets the same patterns with two different models to compare
the quality of semantic descriptions.

Usage:
    python tests/test_4b_model_comparison.py
"""

import json
import os
import random
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.phase3_engine import Phase3Engine
from evolution.phase4_engine import Phase4Engine, signals_to_components, compute_fingerprint
from evolution.llm_openrouter import OpenRouterClient
from evolution.validation_gate import ValidationGate

# Reuse fixture generators
from test_all_families import (
    make_testing_fixtures, make_dependency_fixtures, make_schema_fixtures,
    make_deployment_fixtures, make_config_fixtures, make_security_fixtures,
)
from evolution.adapters.testing import JUnitXMLAdapter
from evolution.adapters.dependency import PipDependencyAdapter
from evolution.adapters.schema import OpenAPIAdapter
from evolution.adapters.deployment import GitHubReleasesAdapter
from evolution.adapters.config import TerraformAdapter
from evolution.adapters.security import TrivyAdapter
from evolution.adapters.git import GitSourceAdapter

RANDOM_SEED = 42
random.seed(RANDOM_SEED)


def separator(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def run_pipeline(test_dir, repo_root):
    """Run Phase 1-3, return path for Phase 4."""
    # Phase 1
    phase1 = Phase1Engine(test_dir)
    try:
        git_adapter = GitSourceAdapter(str(repo_root))
        phase1.ingest(git_adapter)
    except Exception:
        pass

    for adapter_cls, fixtures_fn, kwargs in [
        (JUnitXMLAdapter, make_testing_fixtures, {"source_id": "junit_xml:fixture"}),
        (PipDependencyAdapter, make_dependency_fixtures, {"source_id": "pip:fixture"}),
        (OpenAPIAdapter, make_schema_fixtures, {"source_id": "openapi:fixture"}),
        (GitHubReleasesAdapter, make_deployment_fixtures, {"source_id": "github_releases:fixture"}),
        (TerraformAdapter, make_config_fixtures, {"source_id": "terraform:fixture"}),
        (TrivyAdapter, make_security_fixtures, {"source_id": "trivy:fixture"}),
    ]:
        data = fixtures_fn()
        key = "runs" if "runs" in adapter_cls.__init__.__code__.co_varnames else \
              "snapshots" if "snapshots" in adapter_cls.__init__.__code__.co_varnames else \
              "versions" if "versions" in adapter_cls.__init__.__code__.co_varnames else \
              "deployments" if "deployments" in adapter_cls.__init__.__code__.co_varnames else \
              "scans"
        adapter = adapter_cls(**{key: data, **kwargs})
        phase1.ingest(adapter)

    # Phase 2
    phase2 = Phase2Engine(test_dir, min_baseline=5)
    phase2.run_all()

    # Phase 3 (templates only, no LLM for speed)
    os.environ["PHASE31_ENABLED"] = "false"
    phase3 = Phase3Engine(test_dir)
    phase3.run()
    os.environ["PHASE31_ENABLED"] = "true"  # Restore


def interpret_with_model(model_name, patterns, explanations_by_ref, gate):
    """Run Phase 4b interpretation with a specific model."""
    try:
        llm = OpenRouterClient(model_name)
    except Exception as e:
        print(f"  Could not initialize {model_name}: {e}")
        return {}

    results = {}
    import re

    for pat in patterns:
        # Build prompt (same as Phase4Engine._interpret_pattern)
        signal_explanations = []
        for ref in pat.get("signal_refs", [])[:5]:
            exp = explanations_by_ref.get(ref)
            if exp:
                signal_explanations.append(f"- {exp.get('summary', '')}")

        if not signal_explanations:
            continue

        prompt = (
            "You are analyzing a set of co-occurring software evolution signals.\n\n"
            f"Statistical finding: {pat.get('description_statistical', '')}\n\n"
            "Signal explanations:\n"
            + "\n".join(signal_explanations)
            + "\n\n"
            "Describe the structural theme these signals represent in ONE sentence.\n"
            "Do not add judgment, recommendations, or speculation.\n"
            "Do not use words like \"risk\", \"danger\", \"should\", or \"needs\".\n"
            "Describe only what is structurally happening."
        )

        try:
            t0 = time.time()
            candidate = llm.generate(prompt)
            elapsed = time.time() - t0

            # Strip preamble
            candidate = re.sub(
                r"^(?:(?:Here(?:'s| is) (?:a |the )?(?:description|sentence)[^:]*:|Description:)\s*\n?)",
                "", candidate, flags=re.IGNORECASE,
            ).strip()

            valid = gate.no_forbidden_language(candidate)
            sentences = [s.strip() for s in candidate.split(".") if s.strip()]

            results[pat["fingerprint"]] = {
                "description": candidate,
                "valid": valid,
                "sentence_count": len(sentences),
                "elapsed_ms": round(elapsed * 1000),
            }
        except Exception as e:
            results[pat["fingerprint"]] = {
                "description": f"ERROR: {e}",
                "valid": False,
                "elapsed_ms": 0,
            }

    return results


def main():
    test_dir = Path(__file__).resolve().parent / "test_4b_compare"
    repo_root = Path(__file__).resolve().parent.parent

    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True)

    separator("Running Pipeline (Phase 1-3)")
    run_pipeline(test_dir, repo_root)
    print("  Pipeline complete.")

    # Run Phase 4a to discover patterns (no LLM)
    separator("Phase 4a: Discovering Patterns")
    os.environ["PHASE4B_ENABLED"] = "false"
    phase4 = Phase4Engine(test_dir, params={
        "min_support": 3,
        "min_correlation": 0.5,  # Higher bar for cleaner comparison
        "promotion_threshold": 10,
        "direction_threshold": 0.5,
    })
    result = phase4.run()
    print(f"  Patterns discovered: {result['patterns_discovered']}")

    # Get the top patterns (strongest correlation)
    all_patterns = phase4.kb.list_patterns()
    # Sort by correlation strength descending
    all_patterns.sort(key=lambda p: abs(p.get("correlation_strength", 0)), reverse=True)

    # Pick top 5 most interesting patterns (cross-family, strong correlation)
    test_patterns = all_patterns[:5]
    print(f"\n  Selected {len(test_patterns)} patterns for comparison:")
    for p in test_patterns:
        print(f"    {p['sources']} — {p['metrics']}, corr={p.get('correlation_strength', 0):.2f}")

    # Load Phase 3 explanations — index by both signal_ref AND engine_id+metric
    exp_file = test_dir / "phase3" / "explanations.json"
    with open(exp_file) as f:
        explanations = json.load(f)
    explanations_by_ref = {}
    for e in explanations:
        ref = e.get("signal_ref")
        if ref:
            explanations_by_ref[ref] = e
        # Also index by engine+metric for cross-family lookup
        key = f"{e.get('engine_id')}:{e.get('details', {}).get('metric', '')}"
        if key not in explanations_by_ref:
            explanations_by_ref[key] = e

    # Patch signal_refs on patterns to use engine:metric keys so LLM can find explanations
    for p in test_patterns:
        synth_refs = []
        for src in p.get("sources", []):
            for met in p.get("metrics", []):
                key = f"{src}:{met}"
                if key in explanations_by_ref:
                    synth_refs.append(key)
        p["signal_refs"] = synth_refs

    gate = ValidationGate()

    # ── Model A: Haiku ──
    separator("Model A: claude-3.5-haiku")
    haiku_results = interpret_with_model(
        "anthropic/claude-3.5-haiku", test_patterns, explanations_by_ref, gate
    )

    for fp, r in haiku_results.items():
        pat = next(p for p in test_patterns if p["fingerprint"] == fp)
        print(f"\n  [{pat['sources']}] {pat['metrics']}")
        print(f"  Statistical: {pat.get('description_statistical', '')[:100]}")
        print(f"  Haiku ({r['elapsed_ms']}ms): {r['description']}")
        print(f"  Valid: {r['valid']}")

    # ── Model B: Sonnet 4.5 ──
    separator("Model B: claude-sonnet-4-5-20250514")
    sonnet_results = interpret_with_model(
        "anthropic/claude-sonnet-4.5", test_patterns, explanations_by_ref, gate
    )

    for fp, r in sonnet_results.items():
        pat = next(p for p in test_patterns if p["fingerprint"] == fp)
        print(f"\n  [{pat['sources']}] {pat['metrics']}")
        print(f"  Statistical: {pat.get('description_statistical', '')[:100]}")
        print(f"  Sonnet 4.5 ({r['elapsed_ms']}ms): {r['description']}")
        print(f"  Valid: {r['valid']}")

    # ── Side-by-side ──
    separator("SIDE-BY-SIDE COMPARISON")

    haiku_valid = 0
    sonnet_valid = 0
    haiku_total_ms = 0
    sonnet_total_ms = 0

    for fp in haiku_results:
        pat = next(p for p in test_patterns if p["fingerprint"] == fp)
        h = haiku_results.get(fp, {})
        s = sonnet_results.get(fp, {})

        print(f"\n  Pattern: {pat['sources']} — {pat['metrics']} (corr={pat.get('correlation_strength', 0):.2f})")
        print(f"  Haiku:     {h.get('description', 'N/A')}")
        print(f"  Sonnet:    {s.get('description', 'N/A')}")
        print(f"  Time:      Haiku {h.get('elapsed_ms', 0)}ms vs Sonnet {s.get('elapsed_ms', 0)}ms")

        if h.get("valid"):
            haiku_valid += 1
        if s.get("valid"):
            sonnet_valid += 1
        haiku_total_ms += h.get("elapsed_ms", 0)
        sonnet_total_ms += s.get("elapsed_ms", 0)

    separator("VERDICT")
    n = len(haiku_results)
    print(f"""
  Patterns compared: {n}
  Validation pass rate: Haiku {haiku_valid}/{n}, Sonnet {sonnet_valid}/{n}
  Total latency:        Haiku {haiku_total_ms}ms, Sonnet {sonnet_total_ms}ms
  Avg latency:          Haiku {haiku_total_ms // max(n, 1)}ms, Sonnet {sonnet_total_ms // max(n, 1)}ms
""")

    phase4.close()
    shutil.rmtree(test_dir)
    print("  Cleanup complete.")


if __name__ == "__main__":
    main()
