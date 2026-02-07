import json
import os
from datetime import datetime
from pathlib import Path

EVOLUTION_DIR = ".evolution"
SUBDIRS = ["events", "diffs", "index", "logs"]


def init_repo(repo_path: str = "."):
    repo = Path(repo_path).resolve()
    evo_dir = repo / EVOLUTION_DIR

    if evo_dir.exists():
        print("⚠️  .evolution directory already exists. Nothing to do.")
        return

    # Create base directory
    evo_dir.mkdir()
    for sub in SUBDIRS:
        (evo_dir / sub).mkdir()

    metadata = {
        "engine_version": "0.1.0",
        "repo_path": str(repo),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "platform": "git",
        "notes": "Immutable evolution record"
    }

    with open(evo_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("✅ Initialized .evolution directory")
    print("⚠️  Note: .evolution is ignored by default. Track it only if you know why.")
