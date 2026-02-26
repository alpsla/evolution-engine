#!/usr/bin/env python3
"""Generate 4 HTML reports for diagnostic scenario testing.

Each scenario uses different diagnostics + sources_info to simulate
GitHub Free/Pro and GitLab Free/Pro configurations. The advisory is
enriched with 4 active deviations for visual review.

Usage:
    .venv/bin/python scripts/gen_diagnostic_reports.py
"""

import copy
import json
import shutil
import sys
import webbrowser
from pathlib import Path
from unittest.mock import patch

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evolution.report_generator import (
    _detect_remote_url,
    _render_html,
)

EVO_DIR = ROOT / ".evo"
OUTPUT_DIR = ROOT / ".calibration" / "diagnostic_reports"

# ---------------------------------------------------------------------------
# Extra changes to inject so the report has 4 active deviations
# (the real advisory only has 1 after 3 were accepted)
# ---------------------------------------------------------------------------

EXTRA_CHANGES = [
    {
        "family": "git",
        "metric": "files_touched",
        "normal": {"mean": 8.2, "stddev": 5.1, "median": 6.0, "mad": 3.5},
        "current": 47,
        "deviation_stddev": 7.89,
        "deviation_unit": "modified_zscore",
        "description": (
            "This change touches 47 files \u2014 about 7.8\u00d7 more than usual "
            "(typically around 6). Large changes increase the risk of unintended "
            "side effects and make code review harder."
        ),
        "event_ref": "9f906a15ef70f3d464f18c77dc26c37a4ff71dcdfdc31a238776cf3e3b8e9005",
        "trigger_commit": "ebb63a8a1d7f5b7a7b00cf7531bca18c6e52209a",
        "commit_message": "feat: data quality overhaul\n",
        "observed_at": "2026-02-09T14:30:19Z",
        "trigger_files": [
            "evolution/phase2_engine.py",
            "evolution/phase3_engine.py",
            "evolution/phase4_engine.py",
            "evolution/phase5_engine.py",
        ],
        "latest_deviation": 2.1,
        "latest_value": 12,
        "latest_event_ref": "b9f56d55d209487c95840ca82ede68d31764d05aa128d0653e4fbae6835e1378",
        "is_latest_event": False,
    },
    {
        "family": "git",
        "metric": "change_locality",
        "normal": {"mean": 0.72, "stddev": 0.18, "median": 0.78, "mad": 0.12},
        "current": 0.23,
        "deviation_stddev": -3.09,
        "deviation_unit": "modified_zscore",
        "description": (
            "Changes are scattered across unrelated directories \u2014 locality "
            "is 0.23 vs the usual 0.78. This pattern often indicates a broad "
            "refactor or an AI tool drifting across concerns."
        ),
        "event_ref": "9f906a15ef70f3d464f18c77dc26c37a4ff71dcdfdc31a238776cf3e3b8e9005",
        "trigger_commit": "ebb63a8a1d7f5b7a7b00cf7531bca18c6e52209a",
        "commit_message": "feat: data quality overhaul\n",
        "observed_at": "2026-02-09T14:30:19Z",
        "trigger_files": [
            "evolution/phase2_engine.py",
            "evolution/phase3_engine.py",
        ],
        "latest_deviation": -0.5,
        "latest_value": 0.71,
        "latest_event_ref": "b9f56d55d209487c95840ca82ede68d31764d05aa128d0653e4fbae6835e1378",
        "is_latest_event": False,
    },
    {
        "family": "git",
        "metric": "cochange_novelty_ratio",
        "normal": {"mean": 0.15, "stddev": 0.11, "median": 0.10, "mad": 0.08},
        "current": 0.67,
        "deviation_stddev": 4.81,
        "deviation_unit": "modified_zscore",
        "description": (
            "67% of files changed together have never been co-modified before "
            "\u2014 normally only 10%. Novel co-changes suggest the AI is "
            "creating unexpected couplings between previously independent modules."
        ),
        "event_ref": "9f906a15ef70f3d464f18c77dc26c37a4ff71dcdfdc31a238776cf3e3b8e9005",
        "trigger_commit": "ebb63a8a1d7f5b7a7b00cf7531bca18c6e52209a",
        "commit_message": "feat: data quality overhaul\n",
        "observed_at": "2026-02-09T14:30:19Z",
        "trigger_files": [
            "evolution/phase2_engine.py",
            "evolution/phase5_engine.py",
        ],
        "latest_deviation": 1.2,
        "latest_value": 0.18,
        "latest_event_ref": "b9f56d55d209487c95840ca82ede68d31764d05aa128d0653e4fbae6835e1378",
        "is_latest_event": False,
    },
]


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "key": "1-github-free",
        "title": "Scenario 1: GitHub Free",
        "check": "3x purple 'Pro' badges (CI, Deployment, Security)",
        "diagnostics": {
            "ci": {"status": "no_license", "message": "Requires Evolution Engine Pro."},
            "deployment": {"status": "no_license", "message": "Requires Evolution Engine Pro."},
            "security": {"status": "no_license", "message": "Requires Evolution Engine Pro."},
            "version_control": {"status": "active", "message": ""},
            "dependency": {"status": "active", "message": ""},
            "testing": {"status": "active", "message": ""},
        },
        "sources_info": {
            "connected": [
                {"family": "version_control", "adapter": "git", "tier": 1, "source_file": ".git"},
                {"family": "dependency", "adapter": "pip", "tier": 1, "source_file": "pyproject.toml"},
                {"family": "ci", "adapter": "github_actions_local", "tier": 1, "source_file": ".github/workflows/test.yml"},
                {"family": "ci", "adapter": "github_actions", "tier": 2, "source_file": None},
                {"family": "deployment", "adapter": "github_releases", "tier": 2, "source_file": None},
                {"family": "security", "adapter": "github_security", "tier": 2, "source_file": None},
                {"family": "testing", "adapter": "pytest_cov", "tier": 3, "source_file": "coverage.xml"},
            ],
            "detected": [],
            "connected_families": ["ci", "dependency", "deployment", "security", "testing", "version_control"],
        },
    },
    {
        "key": "2-github-pro",
        "title": "Scenario 2: GitHub Pro",
        "check": "1x blue 'No Data' badge (CI), others connected",
        "diagnostics": {
            "ci": {"status": "no_data", "message": "No CI runs found in the last 30 days."},
            "deployment": {"status": "active", "message": ""},
            "security": {"status": "active", "message": ""},
            "version_control": {"status": "active", "message": ""},
            "dependency": {"status": "active", "message": ""},
            "testing": {"status": "active", "message": ""},
        },
        "sources_info": {
            "connected": [
                {"family": "version_control", "adapter": "git", "tier": 1, "source_file": ".git"},
                {"family": "dependency", "adapter": "pip", "tier": 1, "source_file": "pyproject.toml"},
                {"family": "ci", "adapter": "github_actions_local", "tier": 1, "source_file": ".github/workflows/test.yml"},
                {"family": "ci", "adapter": "github_actions", "tier": 2, "source_file": None},
                {"family": "deployment", "adapter": "github_releases", "tier": 2, "source_file": None},
                {"family": "security", "adapter": "github_security", "tier": 2, "source_file": None},
                {"family": "testing", "adapter": "pytest_cov", "tier": 3, "source_file": "coverage.xml"},
            ],
            "detected": [],
            "connected_families": ["ci", "dependency", "deployment", "security", "testing", "version_control"],
        },
    },
    {
        "key": "3-gitlab-free",
        "title": "Scenario 3: GitLab Free (GitHub remote)",
        "check": "3x purple 'Pro' badges (CI, Deployment, Security)",
        "diagnostics": {
            "ci": {"status": "no_license", "message": "Requires Evolution Engine Pro."},
            "deployment": {"status": "no_license", "message": "Requires Evolution Engine Pro."},
            "security": {"status": "no_license", "message": "Requires Evolution Engine Pro."},
            "version_control": {"status": "active", "message": ""},
            "dependency": {"status": "active", "message": ""},
        },
        "sources_info": {
            "connected": [
                {"family": "version_control", "adapter": "git", "tier": 1, "source_file": ".git"},
                {"family": "dependency", "adapter": "pip", "tier": 1, "source_file": "pyproject.toml"},
                {"family": "ci", "adapter": "gitlab_pipelines", "tier": 2, "source_file": None},
                {"family": "deployment", "adapter": "gitlab_releases", "tier": 2, "source_file": None},
                {"family": "security", "adapter": "github_security", "tier": 2, "source_file": None},
            ],
            "detected": [],
            "connected_families": ["ci", "dependency", "deployment", "security", "version_control"],
        },
    },
    {
        "key": "4-gitlab-pro",
        "title": "Scenario 4: GitLab Pro (GitHub remote)",
        "check": "2x orange 'Platform Mismatch' badges (CI, Deployment)",
        "diagnostics": {
            "ci": {
                "status": "platform_mismatch",
                "message": "GITLAB_TOKEN is set but remote points to github.com.",
                "token_key": "GITLAB_TOKEN",
                "detected_platform": "github",
            },
            "deployment": {
                "status": "platform_mismatch",
                "message": "GITLAB_TOKEN is set but remote points to github.com.",
                "token_key": "GITLAB_TOKEN",
                "detected_platform": "github",
            },
            "version_control": {"status": "active", "message": ""},
            "dependency": {"status": "active", "message": ""},
        },
        "sources_info": {
            "connected": [
                {"family": "version_control", "adapter": "git", "tier": 1, "source_file": ".git"},
                {"family": "dependency", "adapter": "pip", "tier": 1, "source_file": "pyproject.toml"},
                {"family": "ci", "adapter": "gitlab_pipelines", "tier": 2, "source_file": None},
                {"family": "deployment", "adapter": "gitlab_releases", "tier": 2, "source_file": None},
            ],
            "detected": [],
            "connected_families": ["ci", "dependency", "deployment", "version_control"],
        },
    },
]


EXTRA_PATTERNS = [
    {
        "pattern_id": "extra_ft_001",
        "correlation": 0.52,
        "families": ["git"],
        "metrics": ["files_touched"],
        "sources": ["version_control", "dependency"],
        "description": (
            "When dependency events occur, git.files_touched is systematically "
            "increased (effect size d=0.52, treated=2400, control=800)."
        ),
        "repo_count": 0,
    },
    {
        "pattern_id": "extra_cl_001",
        "correlation": -0.41,
        "families": ["git"],
        "metrics": ["change_locality"],
        "sources": ["version_control", "ci"],
        "description": (
            "When CI events occur, git.change_locality is systematically "
            "decreased (effect size d=-0.41, treated=1200, control=4500)."
        ),
        "repo_count": 0,
    },
    {
        "pattern_id": "extra_cn_001",
        "correlation": 0.67,
        "families": ["git"],
        "metrics": ["cochange_novelty_ratio"],
        "sources": ["version_control", "deployment"],
        "description": (
            "When deployment events occur, git.cochange_novelty_ratio is "
            "systematically increased (effect size d=0.67, treated=900, control=3200)."
        ),
        "repo_count": 0,
    },
]


def build_advisory(original: dict, accept_metrics: list[str] = None) -> dict:
    """Return a copy of the advisory with 4 deviations.

    Args:
        original: The real advisory to enrich.
        accept_metrics: List of metric names to mark as accepted
                        (e.g. ["files_touched"]). Default: none accepted.
    """
    accept_metrics = accept_metrics or []
    adv = copy.deepcopy(original)

    # Start with all 4 changes (1 original + 3 extra)
    all_changes = list(adv["changes"]) + copy.deepcopy(EXTRA_CHANGES)

    # Split into active vs accepted
    active = [c for c in all_changes if c["metric"] not in accept_metrics]
    accepted = [c for c in all_changes if c["metric"] in accept_metrics]

    adv["changes"] = active

    # Add matching patterns for the extra deviations
    adv["pattern_matches"].extend(copy.deepcopy(EXTRA_PATTERNS))

    # Update summary
    adv["summary"]["significant_changes"] = len(active)
    adv["summary"]["accepted_changes"] = len(accepted)
    adv["summary"]["accepted_metrics"] = [
        f'{c["family"]}/{c["metric"]}' for c in accepted
    ]
    adv["summary"]["known_patterns_matched"] = len(adv["pattern_matches"])

    # Update event_groups to include active changes only
    if adv.get("event_groups"):
        eg = adv["event_groups"][0]
        eg["changes"] = copy.deepcopy(active)
        eg["signal_count"] = len(active)
        eg["families"] = ["git"]

    return adv


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Clean up old reports
    for old in OUTPUT_DIR.glob("report-*.html"):
        old.unlink()
        print(f"Removed old: {old.name}")

    # Load source data
    advisory = json.loads((EVO_DIR / "phase5" / "advisory.json").read_text())
    evidence_path = EVO_DIR / "phase5" / "evidence.json"
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    remote_url = _detect_remote_url(ROOT)

    # Build enriched advisory with 4 deviations
    enriched = build_advisory(advisory)

    # Generate all 4 reports
    generated = []
    for scenario in SCENARIOS:
        key = scenario["key"]
        title = scenario["title"]
        print(f"\nGenerating: {title}")

        html = _render_html(
            advisory=enriched,
            evidence=evidence,
            title=title,
            remote_url=remote_url,
            sources_info=scenario["sources_info"],
            evo_dir=EVO_DIR,
            diagnostics=scenario["diagnostics"],
        )

        out_path = OUTPUT_DIR / f"report-{key}.html"
        out_path.write_text(html)
        print(f"  Saved: {out_path.name}  ({len(html):,} bytes)")
        generated.append((scenario, out_path))

    # Open one at a time
    print(f"\n{'='*60}")
    for i, (scenario, path) in enumerate(generated, 1):
        print(f"\n--- [{i}/4] {scenario['title']} ---")
        print(f"    Check: {scenario['check']}")
        print(f"    Also:  4 active deviations, pattern dedup, layout")
        webbrowser.open(f"file://{path}")

        if i < len(generated):
            input(f"\n    Press ENTER to open next report...")

    print(f"\n{'='*60}")
    print("All 4 reports opened. Review complete.")


if __name__ == "__main__":
    main()
