"""
Phase 1 — Git Ingestion (Contract‑Compliant)

This module implements Phase 1 of the Evolution Engine for Git repositories.
It observes git commits as immutable source events and persists them
without interpretation, metrics, or semantic judgment.

Conforms to ARCHITECTURE_VISION.md and the Evolution Engine Core Contract.
"""

from pathlib import Path
import json
import hashlib
from datetime import datetime
from git import Repo

EVOLUTION_DIR = ".evolution"
EVENTS_DIR = "events"
INDEX_DIR = "index"


def _content_hash(data: dict) -> str:
    """Deterministically hash JSON‑serializable content."""
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ingest_git_repo(repo_path: str = "."):
    repo_path = Path(repo_path).resolve()
    evo_dir = repo_path / EVOLUTION_DIR

    if not evo_dir.exists():
        raise RuntimeError(".evolution directory not found. Run `evolution init` first.")

    repo = Repo(repo_path)

    events_path = evo_dir / EVENTS_DIR
    events_path.mkdir(parents=True, exist_ok=True)

    index_path = evo_dir / INDEX_DIR / "commit_to_event.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            commit_to_event = json.load(f)
    else:
        commit_to_event = {}

    commits = list(repo.iter_commits(rev="HEAD"))
    commits.reverse()  # oldest → newest

    ingested = 0

    for commit in commits:
        commit_hash = commit.hexsha

        if commit_hash in commit_to_event:
            continue

        # ---- Phase 1 Payload (Git‑native facts only) ----
        payload = {
            "commit_hash": commit_hash,
            "parent_commits": [p.hexsha for p in commit.parents],
            "author": {
                "name": commit.author.name,
                "email": commit.author.email,
            },
            "committer": {
                "name": commit.committer.name,
                "email": commit.committer.email,
            },
            "authored_at": datetime.utcfromtimestamp(commit.authored_date).isoformat() + "Z",
            "committed_at": datetime.utcfromtimestamp(commit.committed_date).isoformat() + "Z",
            "message": commit.message,
            "tree_hash": commit.tree.hexsha,
        }

        attestation = {
            "type": "git_commit",
            "commit_hash": commit_hash,
            "trust_tier": "strong",
        }

        predecessor_refs = [commit_to_event[p] for p in payload["parent_commits"] if p in commit_to_event]

        source_event = {
            "source_type": "git",
            "source_id": str(repo_path),
            "attestation": attestation,
            "predecessor_refs": predecessor_refs or None,
            "observed_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }

        event_id = _content_hash(source_event)
        source_event["event_id"] = event_id

        # Persist event
        event_file = events_path / f"{event_id}.json"
        with open(event_file, "w", encoding="utf-8") as ef:
            json.dump(source_event, ef, indent=2)

        commit_to_event[commit_hash] = event_id
        ingested += 1

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(commit_to_event, f, indent=2)

    print(f"✅ Phase 1 complete: ingested {ingested} git events")
