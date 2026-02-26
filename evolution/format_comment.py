#!/usr/bin/env python3
"""
Format EE advisory or verification as a PR/MR comment.

Called by CI pipelines to produce markdown for posting as a comment.
Can be invoked as:
    python -m evolution.format_comment --advisory advisory.json --output comment.md

Usage:
    python -m evolution.format_comment --advisory .evo/phase5/advisory.json --output comment.md
    python -m evolution.format_comment --verification .evo/phase5/verification.json --output comment.md
    python -m evolution.format_comment --advisory advisory.json --sources sources.json --prompt prompt.txt --ci-provider gitlab --output comment.md
    python -m evolution.format_comment --advisory advisory.json --accepted-by username --output comment.md
"""

import argparse
import json
import sys
from pathlib import Path

from evolution.pr_comment import (
    format_pr_comment,
    format_verification_comment,
    format_accepted_comment,
)


def main():
    parser = argparse.ArgumentParser(description="Format EE results as PR/MR comment")
    parser.add_argument("--advisory", help="Path to advisory.json")
    parser.add_argument("--verification", help="Path to verification.json")
    parser.add_argument("--investigation", help="Path to investigation.json")
    parser.add_argument("--sources", help="Path to sources.json (from evo sources --json)")
    parser.add_argument("--prompt", help="Path to investigation prompt text file")
    parser.add_argument("--residual-prompt", help="Path to residual prompt text file")
    parser.add_argument("--report-url", help="URL to the HTML report artifact")
    parser.add_argument("--accepted-by", help="Username who accepted findings")
    parser.add_argument("--scope", help="Acceptance scope: this-pr or permanent", default="this-pr")
    parser.add_argument("--diagnostics", help="Path to diagnostics.json (adapter diagnostics)")
    parser.add_argument("--ci-provider", help="CI platform: github or gitlab", default="github")
    parser.add_argument("--output", required=True, help="Output markdown file")
    args = parser.parse_args()

    # Accepted flow — renders accepted state and exits
    if args.accepted_by and args.advisory:
        advisory_path = Path(args.advisory)
        if not advisory_path.exists():
            sys.exit(0)
        advisory = json.loads(advisory_path.read_text())
        comment = format_accepted_comment(
            advisory,
            accepted_by=args.accepted_by,
            scope=args.scope,
            ci_provider=args.ci_provider,
        )
        Path(args.output).write_text(comment)
        return

    # Load optional data files
    diagnostics = None
    if args.diagnostics:
        diag_path = Path(args.diagnostics)
        if diag_path.exists():
            diagnostics = json.loads(diag_path.read_text())

    sources_info = None
    if args.sources:
        sources_path = Path(args.sources)
        if sources_path.exists():
            sources_info = json.loads(sources_path.read_text())

    investigation_prompt = None
    if args.prompt:
        prompt_path = Path(args.prompt)
        if prompt_path.exists():
            investigation_prompt = prompt_path.read_text().strip()

    residual_prompt = None
    if args.residual_prompt:
        rp_path = Path(args.residual_prompt)
        if rp_path.exists():
            residual_prompt = rp_path.read_text().strip()

    report_url = args.report_url

    if args.verification:
        verification_path = Path(args.verification)
        if not verification_path.exists():
            sys.exit(0)
        verification = json.loads(verification_path.read_text())
        comment = format_verification_comment(
            verification,
            residual_prompt=residual_prompt,
            report_url=report_url,
            ci_provider=args.ci_provider,
        )
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

        comment = format_pr_comment(
            advisory,
            investigation=investigation,
            sources_info=sources_info,
            investigation_prompt=investigation_prompt,
            report_url=report_url,
            ci_provider=args.ci_provider,
            diagnostics=diagnostics,
        )
    else:
        print("Either --advisory or --verification is required", file=sys.stderr)
        sys.exit(1)

    Path(args.output).write_text(comment)


if __name__ == "__main__":
    main()
