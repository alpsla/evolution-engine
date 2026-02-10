#!/usr/bin/env python3
"""
Format EE advisory or verification as a PR comment.

Called by the GitHub Action to produce markdown for `gh pr comment`.

Usage:
    python format_comment.py --advisory .evo/phase5/advisory.json --output comment.md
    python format_comment.py --verification .evo/phase5/verification.json --output comment.md
    python format_comment.py --advisory advisory.json --investigation investigation.json --output comment.md
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Format EE results as PR comment")
    parser.add_argument("--advisory", help="Path to advisory.json")
    parser.add_argument("--verification", help="Path to verification.json")
    parser.add_argument("--investigation", help="Path to investigation.json")
    parser.add_argument("--output", required=True, help="Output markdown file")
    args = parser.parse_args()

    # Import here to work even when installed as standalone script
    try:
        from evolution.pr_comment import format_pr_comment, format_verification_comment
    except ImportError:
        # Minimal fallback if evolution package isn't in path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from evolution.pr_comment import format_pr_comment, format_verification_comment

    if args.verification:
        verification_path = Path(args.verification)
        if not verification_path.exists():
            sys.exit(0)
        verification = json.loads(verification_path.read_text())
        comment = format_verification_comment(verification)
    elif args.advisory:
        advisory_path = Path(args.advisory)
        if not advisory_path.exists():
            sys.exit(0)
        advisory = json.loads(advisory_path.read_text())

        investigation = None
        if args.investigation:
            inv_path = Path(args.investigation)
            if inv_path.exists():
                investigation = json.loads(inv_path.read_text())

        comment = format_pr_comment(advisory, investigation=investigation)
    else:
        print("Either --advisory or --verification is required", file=sys.stderr)
        sys.exit(1)

    Path(args.output).write_text(comment)


if __name__ == "__main__":
    main()
