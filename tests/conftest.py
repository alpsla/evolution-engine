"""Shared fixtures for Evolution Engine test suite."""

import json
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine

# ──────────────── Constants ────────────────

RANDOM_SEED = 42
BASE_TIME = datetime(2026, 1, 1, 10, 0, 0)
COMMIT_SHAS = [f"{i:040x}" for i in range(100, 120)]


# ──────────────── Core Fixtures ────────────────


@pytest.fixture
def evo_dir(tmp_path):
    """Provide a clean temporary evo directory."""
    d = tmp_path / "evo"
    d.mkdir()
    return d


@pytest.fixture
def seeded_rng():
    """Reset random seed for reproducibility."""
    random.seed(RANDOM_SEED)
    return random


# ──────────────── Event Generators ────────────────


def make_git_events(n: int = 20) -> list[dict]:
    """Generate n git commit events."""
    events = []
    for i in range(n):
        t = BASE_TIME + timedelta(hours=i * 2)
        files = [f"src/module_{j}.py" for j in range(random.randint(1, 10))]
        events.append({
            "event_id": f"git-{i:04d}",
            "source_type": "git",
            "source_family": "version_control",
            "observed_at": t.isoformat() + "Z",
            "payload": {
                "commit_hash": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                "committed_at": t.isoformat() + "Z",
                "authored_at": t.isoformat() + "Z",
                "message": f"commit {i}",
                "author": "test@example.com",
                "files": files,
            },
            "attestation": {
                "commit_hash": COMMIT_SHAS[i % len(COMMIT_SHAS)],
            },
        })
    return events


def make_ci_events(n: int = 15) -> list[dict]:
    """Generate n CI run events."""
    events = []
    for i in range(n):
        t = BASE_TIME + timedelta(hours=i * 3)
        duration = random.uniform(60, 600)
        conclusion = random.choice(["success", "success", "success", "failure"])
        events.append({
            "event_id": f"ci-{i:04d}",
            "source_type": "github_actions",
            "source_family": "ci",
            "observed_at": t.isoformat() + "Z",
            "payload": {
                "trigger": {
                    "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                },
                "timing": {
                    "created_at": t.isoformat() + "Z",
                    "started_at": t.isoformat() + "Z",
                    "completed_at": (t + timedelta(seconds=duration)).isoformat() + "Z",
                    "duration_seconds": round(duration, 1),
                },
                "conclusion": conclusion,
            },
        })
    return events


def make_dependency_events(n: int = 12) -> list[dict]:
    """Generate n dependency snapshot events."""
    events = []
    base_count = 25
    for i in range(n):
        t = BASE_TIME + timedelta(hours=i * 4)
        total = base_count + random.randint(-3, 5)
        events.append({
            "event_id": f"dep-{i:04d}",
            "source_type": "pip",
            "source_family": "dependency",
            "observed_at": t.isoformat() + "Z",
            "payload": {
                "ecosystem": "pip",
                "trigger": {
                    "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                },
                "snapshot": {
                    "total_count": total,
                    "direct_count": 10,
                    "max_depth": random.randint(1, 4),
                },
                "dependencies": [
                    {"name": f"pkg-{j}", "version": "1.0.0", "direct": j < 10, "depth": 1}
                    for j in range(total)
                ],
            },
        })
    return events


def make_deployment_events(n: int = 10) -> list[dict]:
    """Generate n deployment/release events."""
    events = []
    for i in range(n):
        t = BASE_TIME + timedelta(days=i * 3, hours=random.randint(0, 12))
        prev_t = BASE_TIME + timedelta(days=(i - 1) * 3) if i > 0 else None
        events.append({
            "event_id": f"deploy-{i:04d}",
            "source_type": "github_releases",
            "source_family": "deployment",
            "observed_at": t.isoformat() + "Z",
            "payload": {
                "trigger": {
                    "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                },
                "timing": {
                    "initiated_at": t.isoformat() + "Z",
                    "completed_at": t.isoformat() + "Z",
                    "since_previous_seconds": (t - prev_t).total_seconds() if prev_t else None,
                },
                "is_prerelease": random.random() < 0.2,
                "asset_count": random.randint(0, 5),
                "version": f"v1.{i}.0",
            },
        })
    return events


def make_testing_events(n: int = 15) -> list[dict]:
    """Generate n test suite run events."""
    events = []
    for i in range(n):
        t = BASE_TIME + timedelta(hours=i * 6)
        total = 120 + random.randint(-5, 10)
        failed = random.randint(0, max(1, total // 10))
        skipped = random.randint(0, 5)
        duration = random.uniform(30, 180)
        events.append({
            "event_id": f"test-{i:04d}",
            "source_type": "junit_xml",
            "source_family": "testing",
            "observed_at": t.isoformat() + "Z",
            "payload": {
                "trigger": {
                    "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                },
                "execution": {
                    "started_at": t.isoformat() + "Z",
                    "completed_at": (t + timedelta(seconds=duration)).isoformat() + "Z",
                    "duration_seconds": round(duration, 3),
                },
                "summary": {
                    "total": total,
                    "passed": total - failed - skipped,
                    "failed": failed,
                    "skipped": skipped,
                },
                "cases": [],
            },
        })
    return events


def make_security_events(n: int = 10) -> list[dict]:
    """Generate n security scan events."""
    events = []
    for i in range(n):
        t = BASE_TIME + timedelta(days=i * 3)
        total = 15 + random.randint(-3, 5)
        critical = random.randint(0, 2)
        high = random.randint(1, 5)
        medium = random.randint(3, 8)
        low = max(0, total - critical - high - medium)
        findings = [
            {
                "id": f"CVE-2026-{j:04d}",
                "severity": "critical" if j < critical else "high" if j < critical + high else "medium",
                "package": f"pkg-{j}",
                "fixed_version": f"1.{j}.0" if random.random() < 0.6 else None,
            }
            for j in range(total)
        ]
        events.append({
            "event_id": f"sec-{i:04d}",
            "source_type": "trivy",
            "source_family": "security",
            "observed_at": t.isoformat() + "Z",
            "payload": {
                "trigger": {
                    "commit_sha": COMMIT_SHAS[i % len(COMMIT_SHAS)],
                },
                "execution": {
                    "started_at": t.isoformat() + "Z",
                    "completed_at": (t + timedelta(seconds=30)).isoformat() + "Z",
                },
                "summary": {
                    "total": total,
                    "critical": critical,
                    "high": high,
                    "medium": medium,
                    "low": low,
                },
                "findings": findings,
            },
        })
    return events


# ──────────────── Populated Evo Dir Fixture ────────────────


@pytest.fixture
def populated_evo_dir(evo_dir, seeded_rng):
    """Evo directory pre-loaded with Phase 1 events from multiple families."""
    phase1 = Phase1Engine(evo_dir)

    all_events = (
        make_git_events(20)
        + make_ci_events(15)
        + make_dependency_events(12)
        + make_deployment_events(10)
        + make_testing_events(15)
        + make_security_events(10)
    )

    events_dir = evo_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    for ev in all_events:
        path = events_dir / f"{ev['event_id']}.json"
        path.write_text(json.dumps(ev, indent=2))

    return evo_dir


@pytest.fixture
def populated_through_phase2(populated_evo_dir):
    """Evo directory with Phase 1 events and Phase 2 signals computed."""
    phase2 = Phase2Engine(populated_evo_dir, window_size=10, min_baseline=3)
    phase2.run_all()
    return populated_evo_dir
