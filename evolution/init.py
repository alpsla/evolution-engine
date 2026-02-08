"""
Evolution Engine — Repository Initialization

Creates the .evolution directory structure for a monitored repository.
"""

import json
from datetime import datetime
from pathlib import Path

EVOLUTION_DIR = ".evolution"
SUBDIRS = ["events", "index", "phase2", "phase3"]


def init_repo(repo_path: str = "."):
    repo = Path(repo_path).resolve()
    evo_dir = repo / EVOLUTION_DIR

    if evo_dir.exists():
        print(".evolution directory already exists. Nothing to do.")
        return

    # Create base directory and subdirectories
    evo_dir.mkdir()
    for sub in SUBDIRS:
        (evo_dir / sub).mkdir()

    metadata = {
        "engine_version": "0.2.0",
        "repo_path": str(repo),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "source_families": [],
        "notes": "Immutable evolution record — all source families supported",
    }

    with open(evo_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("Initialized .evolution directory")
    print(f"  Location: {evo_dir}")
    print(f"  Subdirectories: {', '.join(SUBDIRS)}")
