"""
evo-patterns-example — Example Evolution Engine pattern pack.

27 universal cross-family patterns calibrated from 43 open-source repos.
"""

import json
from pathlib import Path


def register():
    """Entry point for local development. Loads patterns from patterns.json."""
    patterns_path = Path(__file__).parent / "patterns.json"
    if not patterns_path.exists():
        return []
    return json.loads(patterns_path.read_text())
