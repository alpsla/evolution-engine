#!/usr/bin/env python3
"""
Format EE advisory or verification as a PR comment.

Called by the GitHub Action to produce markdown for `gh pr comment`.
Delegates to evolution.format_comment which is the canonical implementation.

Usage:
    python format_comment.py --advisory .evo/phase5/advisory.json --output comment.md
    python format_comment.py --verification .evo/phase5/verification.json --output comment.md
    python format_comment.py --advisory advisory.json --sources sources.json --prompt prompt.txt --report-url URL --output comment.md
    python format_comment.py --advisory advisory.json --accepted-by username --output comment.md
"""

import sys
from pathlib import Path

try:
    from evolution.format_comment import main
except ImportError:
    # Fallback if evolution package isn't in path (GitHub Action context)
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from evolution.format_comment import main


if __name__ == "__main__":
    main()
