#!/usr/bin/env python3
"""Generate sample reports for the website with rich demo data.

Produces:
  website/sample-report.html          (EN analyze)
  website/sample-report-verify.html   (EN verify)
  website/sample-report-de.html       (DE analyze)
  website/sample-report-verify-de.html(DE verify)
  website/sample-report-es.html       (ES analyze)
  website/sample-report-verify-es.html(ES verify)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evolution.report_generator import _render_html
from evolution.i18n import load_translations


def _demo_advisory():
    return {
        "advisory_id": "evo-demo-2026-03-14",
        "scope": "demo-repo",
        "generated_at": "2026-03-14T09:30:00Z",
        "period": {
            "from": "2025-12-01T00:00:00Z",
            "to": "2026-03-14T09:30:00Z",
        },
        "summary": {
            "significant_changes": 5,
            "families_affected": ["git", "ci", "deployment", "dependency"],
            "known_patterns_matched": 4,
            "candidate_patterns_matched": 1,
            "event_groups": 3,
            "new_observations": 5,
            "events_analyzed": 1842,
            "signals_computed": 487,
        },
        "changes": [
            {
                "family": "git",
                "metric": "files_touched",
                "normal": {"mean": 4.2, "stddev": 3.1, "median": 3.0, "mad": 1.5},
                "current": 47,
                "deviation_stddev": 19.8,
                "deviation_unit": "modified_zscore",
                "description": "This commit touched 47 files across 12 directories.",
                "event_ref": "abc001",
                "trigger_commit": "e4f49b1a3c2d5e6f7a8b9c0d1e2f3a4b5c6d7e8f",
                "commit_message": "feat: migrate authentication to OAuth2 + add rate limiting",
            },
            {
                "family": "git",
                "metric": "dispersion",
                "normal": {"mean": 0.22, "stddev": 0.15, "median": 0.18, "mad": 0.08},
                "current": 0.94,
                "deviation_stddev": 6.41,
                "deviation_unit": "modified_zscore",
                "description": "Changes spread across unrelated areas of the codebase.",
                "event_ref": "abc001",
                "trigger_commit": "e4f49b1a3c2d5e6f7a8b9c0d1e2f3a4b5c6d7e8f",
                "commit_message": "feat: migrate authentication to OAuth2 + add rate limiting",
            },
            {
                "family": "ci",
                "metric": "run_duration",
                "normal": {"mean": 180.0, "stddev": 45.0, "median": 165.0, "mad": 30.0},
                "current": 892,
                "deviation_stddev": 16.33,
                "deviation_unit": "modified_zscore",
                "description": "CI pipeline took 14m 52s, well above the typical 2m 45s.",
                "event_ref": "abc002",
                "trigger_commit": "e4f49b1a3c2d5e6f7a8b9c0d1e2f3a4b5c6d7e8f",
                "commit_message": "feat: migrate authentication to OAuth2 + add rate limiting",
            },
            {
                "family": "deployment",
                "metric": "release_cadence_hours",
                "normal": {"mean": 168.0, "stddev": 48.0, "median": 160.0, "mad": 36.0},
                "current": 18.5,
                "deviation_stddev": -2.65,
                "deviation_unit": "modified_zscore",
                "description": "Release deployed 18.5 hours after the previous one — much faster than the typical weekly cadence.",
                "event_ref": "abc003",
                "trigger_commit": "113a54f2c8b9d0e1f2a3b4c5d6e7f8a9b0c1d2e3",
                "commit_message": "feat: add WebSocket support for real-time notifications",
            },
            {
                "family": "dependency",
                "metric": "dependency_count",
                "normal": {"mean": 87.0, "stddev": 5.0, "median": 86.0, "mad": 3.0},
                "current": 104,
                "deviation_stddev": 4.05,
                "deviation_unit": "modified_zscore",
                "description": "18 new dependencies added in a single commit.",
                "event_ref": "abc001",
                "trigger_commit": "e4f49b1a3c2d5e6f7a8b9c0d1e2f3a4b5c6d7e8f",
                "commit_message": "feat: migrate authentication to OAuth2 + add rate limiting",
            },
        ],
        "pattern_matches": [
            {
                "pattern_id": "pm-001",
                "sources": ["git", "ci"],
                "families": ["git", "ci"],
                "metrics": ["files_touched", "run_duration"],
                "correlation_strength": 0.78,
                "correlation_direction": "positive",
                "description_statistical": "Files touched positively correlates with CI run duration (r=0.78).",
                "description_semantic": "When many files change in a single commit, CI build times increase proportionally due to broader test coverage being triggered.",
                "occurrences": 24,
                "first_seen": "2025-06-15T00:00:00Z",
            },
            {
                "pattern_id": "pm-002",
                "sources": ["git", "deployment"],
                "families": ["git", "deployment"],
                "metrics": ["dispersion", "release_cadence_hours"],
                "correlation_strength": -0.62,
                "correlation_direction": "negative",
                "description_statistical": "Code dispersion negatively correlates with release cadence (r=-0.62).",
                "description_semantic": "When code changes are scattered across many directories, releases tend to be pushed out faster — possibly to ship hotfixes before the next planned release.",
                "occurrences": 15,
                "first_seen": "2025-09-01T00:00:00Z",
            },
            {
                "pattern_id": "pm-003",
                "sources": ["git", "dependency"],
                "families": ["git", "dependency"],
                "metrics": ["files_touched", "dependency_count"],
                "correlation_strength": 0.55,
                "correlation_direction": "positive",
                "description_statistical": "Files touched correlates with dependency count changes (r=0.55).",
                "description_semantic": "Large commits that touch many files tend to also introduce new dependencies, suggesting feature branches that bundle dependency additions with implementation.",
                "occurrences": 11,
                "first_seen": "2025-11-20T00:00:00Z",
            },
            {
                "pattern_id": "pm-004",
                "sources": ["ci", "deployment"],
                "families": ["ci", "deployment"],
                "metrics": ["run_duration", "release_cadence_hours"],
                "correlation_strength": -0.48,
                "correlation_direction": "negative",
                "description_statistical": "CI duration negatively correlates with release cadence (r=-0.48).",
                "description_semantic": "When CI pipelines run longer, the time between releases shortens — teams may be rushing releases to meet deadlines despite slower builds.",
                "occurrences": 9,
                "first_seen": "2025-12-05T00:00:00Z",
            },
        ],
        "candidate_patterns": [
            {
                "pattern_id": "cp-001",
                "sources": ["dependency", "ci"],
                "families": ["dependency", "ci"],
                "metrics": ["dependency_count", "run_duration"],
                "correlation_strength": 0.41,
                "correlation_direction": "positive",
                "description_statistical": "Dependency count changes correlate with CI duration (r=0.41).",
                "description_semantic": "Adding dependencies increases CI build time as package installation and resolution steps take longer.",
                "occurrences": 4,
                "first_seen": "2026-01-10T00:00:00Z",
            },
        ],
    }


def _demo_evidence():
    return {
        "evidence_id": "ev-demo-001",
        "advisory_ref": "evo-demo-2026-03-14",
        "commits": [
            {
                "sha": "e4f49b1a3c2d",
                "message": "feat: migrate authentication to OAuth2 + add rate limiting\n\nReplaces legacy session-based auth with OAuth2 PKCE flow.\nAdds Redis-backed rate limiting middleware.",
                "author": {"name": "Sarah Chen", "email": "sarah@demo-repo.dev"},
                "timestamp": "2026-03-13T16:30:00Z",
                "files_changed": [
                    "src/auth/oauth2.py", "src/auth/middleware.py", "src/auth/tokens.py",
                    "src/api/routes.py", "src/api/rate_limiter.py",
                    "tests/test_auth.py", "tests/test_rate_limiter.py",
                    "config/auth.yaml", "config/redis.yaml",
                    "requirements.txt", "pyproject.toml",
                ],
            },
            {
                "sha": "3b90e72f1d4a",
                "message": "fix: resolve N+1 query in dashboard endpoint\n\nPrefetch related objects to avoid repeated DB hits.",
                "author": {"name": "Marcus Rodriguez", "email": "marcus@demo-repo.dev"},
                "timestamp": "2026-03-12T14:15:00Z",
                "files_changed": [
                    "src/api/dashboard.py", "src/models/queries.py",
                    "tests/test_dashboard.py",
                ],
            },
            {
                "sha": "608ead0b5e7c",
                "message": "chore: upgrade React to v19, update bundler config",
                "author": {"name": "Sarah Chen", "email": "sarah@demo-repo.dev"},
                "timestamp": "2026-03-11T09:45:00Z",
                "files_changed": [
                    "frontend/package.json", "frontend/package-lock.json",
                    "frontend/vite.config.ts", "frontend/tsconfig.json",
                ],
            },
            {
                "sha": "113a54f2c8b9",
                "message": "feat: add WebSocket support for real-time notifications",
                "author": {"name": "Alex Kim", "email": "alex@demo-repo.dev"},
                "timestamp": "2026-03-10T11:20:00Z",
                "files_changed": [
                    "src/websocket/handler.py", "src/websocket/channels.py",
                    "src/api/notifications.py", "frontend/src/hooks/useWebSocket.ts",
                    "tests/test_websocket.py",
                ],
            },
            {
                "sha": "4a0a9c5d6e1f",
                "message": "ci: add parallel test execution and coverage reporting",
                "author": {"name": "Marcus Rodriguez", "email": "marcus@demo-repo.dev"},
                "timestamp": "2026-03-09T08:00:00Z",
                "files_changed": [
                    ".github/workflows/test.yml", ".github/workflows/coverage.yml",
                    "Makefile", "pytest.ini",
                ],
            },
        ],
        "files_affected": [
            {"path": "src/auth/oauth2.py", "change_type": "added"},
            {"path": "src/auth/middleware.py", "change_type": "modified"},
            {"path": "src/auth/tokens.py", "change_type": "added"},
            {"path": "src/api/routes.py", "change_type": "modified"},
            {"path": "src/api/rate_limiter.py", "change_type": "added"},
            {"path": "src/api/dashboard.py", "change_type": "modified"},
            {"path": "src/models/queries.py", "change_type": "modified"},
            {"path": "src/websocket/handler.py", "change_type": "added"},
            {"path": "src/websocket/channels.py", "change_type": "added"},
            {"path": "frontend/package.json", "change_type": "modified"},
            {"path": "requirements.txt", "change_type": "modified"},
            {"path": "pyproject.toml", "change_type": "modified"},
            {"path": "config/auth.yaml", "change_type": "added"},
            {"path": "config/redis.yaml", "change_type": "added"},
            {"path": ".github/workflows/test.yml", "change_type": "modified"},
        ],
        "dependencies_changed": [
            {"name": "redis", "from": None, "to": "5.0.1", "action": "added"},
            {"name": "authlib", "from": None, "to": "1.3.0", "action": "added"},
            {"name": "pyjwt", "from": "2.6.0", "to": "2.8.0", "action": "upgraded"},
        ],
        "timeline": [
            {"family": "git", "event_text": "Commit e4f49b1: feat: migrate auth to OAuth2", "timestamp": "2026-03-13T16:30:00Z"},
            {"family": "ci", "event_text": "CI run #847: 14m 52s (failed → passed on retry)", "timestamp": "2026-03-13T16:45:00Z"},
            {"family": "deployment", "event_text": "Release v2.4.0 deployed to production", "timestamp": "2026-03-13T17:00:00Z"},
            {"family": "git", "event_text": "Commit 3b90e72: fix: resolve N+1 query", "timestamp": "2026-03-12T14:15:00Z"},
            {"family": "git", "event_text": "Commit 608ead0: chore: upgrade React to v19", "timestamp": "2026-03-11T09:45:00Z"},
        ],
    }


def _demo_verification():
    return {
        "resolved": [
            {
                "family": "git",
                "metric": "dispersion",
                "was_deviation": 6.41,
                "was_value": 0.94,
                "now_deviation": 0.8,
                "current": 0.25,
                "normal": {"median": 0.18},
            },
            {
                "family": "deployment",
                "metric": "release_cadence_hours",
                "was_deviation": -2.65,
                "was_value": 18.5,
                "now_deviation": -0.3,
                "current": 145,
                "normal": {"median": 160.0},
            },
        ],
        "persisting": [
            {
                "family": "git",
                "metric": "files_touched",
                "was_deviation": 19.8,
                "was_value": 47,
                "now_deviation": 2.1,
                "current": 8,
                "normal": {"median": 3.0},
                "improved": True,
            },
            {
                "family": "ci",
                "metric": "run_duration",
                "was_deviation": 16.33,
                "was_value": 892,
                "now_deviation": 3.9,
                "current": 340,
                "normal": {"median": 165.0},
                "improved": True,
            },
            {
                "family": "dependency",
                "metric": "dependency_count",
                "was_deviation": 4.05,
                "was_value": 104,
                "now_deviation": 4.05,
                "current": 104,
                "normal": {"median": 86.0},
                "improved": False,
                "latest_deviation": 4.05,
                "latest_value": 104,
            },
        ],
        "new": [],
    }


def _demo_sources():
    connected = [
        {"family": "version_control", "adapter": "git", "status": "active", "tier": 1,
         "event_count": 1542, "signal_count": 380},
        {"family": "ci", "adapter": "github_actions", "status": "active", "tier": 2,
         "event_count": 200, "signal_count": 52},
        {"family": "deployment", "adapter": "github_releases", "status": "active", "tier": 2,
         "event_count": 48, "signal_count": 25},
        {"family": "dependency", "adapter": "pip", "status": "active", "tier": 1,
         "event_count": 52, "signal_count": 30},
        {"family": "security", "adapter": "github_security", "status": "connected_no_deviations", "tier": 2,
         "event_count": 0, "signal_count": 0},
    ]
    detected = [
        {"family": "testing", "adapter": "junit_xml", "status": "not_connected", "tier": 1},
        {"family": "coverage", "adapter": "cobertura_xml", "status": "not_connected", "tier": 1},
        {"family": "error_tracking", "adapter": "sentry", "status": "not_connected", "tier": 2},
    ]
    return {
        "connected": connected,
        "detected": detected,
        "connected_families": [c["family"] for c in connected],
    }


def _demo_verify_advisory():
    """Advisory for the verification report — reflects post-fix state.

    2 resolved (dispersion, release_cadence), 2 improving (files_touched,
    run_duration), 1 not improving (dependency_count).
    Only show changes that are still deviating.
    """
    base = _demo_advisory()
    base["advisory_id"] = "evo-demo-2026-03-21"
    base["generated_at"] = "2026-03-21T10:00:00Z"
    base["period"]["to"] = "2026-03-21T10:00:00Z"
    # Post-fix: only 3 changes still deviating (2 improving + 1 not improving)
    base["changes"] = [
        {
            "family": "git",
            "metric": "files_touched",
            "normal": {"mean": 4.2, "stddev": 3.1, "median": 3.0, "mad": 1.5},
            "current": 8,
            "deviation_stddev": 2.1,
            "deviation_unit": "modified_zscore",
            "description": "This commit touched 8 files — down from 47 but still above typical.",
            "event_ref": "fix001",
            "trigger_commit": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            "commit_message": "refactor: split auth migration into focused modules",
        },
        {
            "family": "ci",
            "metric": "run_duration",
            "normal": {"mean": 180.0, "stddev": 45.0, "median": 165.0, "mad": 30.0},
            "current": 340,
            "deviation_stddev": 3.9,
            "deviation_unit": "modified_zscore",
            "description": "CI pipeline took 5m 40s — improved from 14m 52s but still above typical 2m 45s.",
            "event_ref": "fix002",
            "trigger_commit": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            "commit_message": "refactor: split auth migration into focused modules",
        },
        {
            "family": "dependency",
            "metric": "dependency_count",
            "normal": {"mean": 87.0, "stddev": 5.0, "median": 86.0, "mad": 3.0},
            "current": 104,
            "deviation_stddev": 4.05,
            "deviation_unit": "modified_zscore",
            "description": "18 dependencies still above baseline — review if all are needed.",
            "event_ref": "fix001",
            "trigger_commit": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            "commit_message": "refactor: split auth migration into focused modules",
        },
    ]
    base["summary"]["significant_changes"] = 3
    base["summary"]["families_affected"] = ["git", "ci", "dependency"]
    return base


def _demo_verify_evidence():
    """Evidence for the verification report — reflects post-fix commits."""
    return {
        "evidence_id": "ev-demo-fix-001",
        "advisory_ref": "evo-demo-2026-03-21",
        "commits": [
            {
                "sha": "a1b2c3d4e5f6",
                "message": "refactor: split auth migration into focused modules\n\nBroke the monolithic OAuth2 migration into smaller, targeted changes.",
                "author": {"name": "Sarah Chen", "email": "sarah@demo-repo.dev"},
                "timestamp": "2026-03-20T14:00:00Z",
                "files_changed": [
                    "src/auth/oauth2.py", "src/auth/middleware.py",
                    "src/auth/tokens.py", "src/api/routes.py",
                    "tests/test_auth.py", "requirements.txt",
                    "config/auth.yaml", "pyproject.toml",
                ],
            },
            {
                "sha": "b2c3d4e5f6a7",
                "message": "fix: optimize CI pipeline caching for auth deps",
                "author": {"name": "Marcus Rodriguez", "email": "marcus@demo-repo.dev"},
                "timestamp": "2026-03-19T11:30:00Z",
                "files_changed": [
                    ".github/workflows/test.yml", "requirements.txt",
                ],
            },
        ],
        "files_affected": [
            {"path": "src/auth/oauth2.py", "change_type": "modified"},
            {"path": "src/auth/middleware.py", "change_type": "modified"},
            {"path": ".github/workflows/test.yml", "change_type": "modified"},
            {"path": "requirements.txt", "change_type": "modified"},
        ],
        "dependencies_changed": [],
        "timeline": [
            {"family": "git", "event_text": "Commit a1b2c3d: refactor: split auth migration", "timestamp": "2026-03-20T14:00:00Z"},
            {"family": "ci", "event_text": "CI run #855: 5m 40s (passed)", "timestamp": "2026-03-20T14:15:00Z"},
            {"family": "git", "event_text": "Commit b2c3d4e: fix: optimize CI pipeline caching", "timestamp": "2026-03-19T11:30:00Z"},
        ],
    }


def generate(lang, verify=False):
    load_translations(lang)
    sources = _demo_sources()
    verification = _demo_verification() if verify else None

    if verify:
        advisory = _demo_verify_advisory()
        evidence = _demo_verify_evidence()
    else:
        advisory = _demo_advisory()
        evidence = _demo_evidence()

    html = _render_html(
        advisory, evidence,
        title="Evolution Advisory",
        remote_url="https://github.com/demo-org/demo-repo",
        verification=verification,
        sources_info=sources,
        is_pro=True,
    )
    return html


def main():
    out_dir = PROJECT_ROOT / "website"
    configs = [
        ("en", False, "sample-report.html"),
        ("en", True,  "sample-report-verify.html"),
        ("de", False, "sample-report-de.html"),
        ("de", True,  "sample-report-verify-de.html"),
        ("es", False, "sample-report-es.html"),
        ("es", True,  "sample-report-verify-es.html"),
    ]
    for lang, verify, filename in configs:
        html = generate(lang, verify)
        path = out_dir / filename
        path.write_text(html, encoding="utf-8")
        size_kb = len(html) / 1024
        print(f"  {filename} ({size_kb:.0f} KB)")

    print(f"\nAll 6 sample reports written to {out_dir}/")


if __name__ == "__main__":
    main()
