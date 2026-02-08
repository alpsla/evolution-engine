"""
CLI entry point for report generator.

Usage:
    python -m evolution.report --advisory PATH --output PATH [--open]
"""

import argparse
import sys
import webbrowser
from pathlib import Path

from .generator import ReportGenerator


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate HTML/PDF reports from Evolution Engine advisories"
    )
    parser.add_argument(
        "--advisory",
        type=Path,
        required=True,
        help="Path to Phase 5 advisory.json file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for HTML report"
    )
    parser.add_argument(
        "--template",
        type=Path,
        help="Custom Jinja2 template directory (optional)"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open report in browser after generation"
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.advisory.exists():
        print(f"❌ Error: Advisory file not found: {args.advisory}", file=sys.stderr)
        sys.exit(1)

    # Generate report
    try:
        generator = ReportGenerator(template_dir=args.template)
        generator.generate(
            advisory_path=args.advisory,
            output_path=args.output
        )

        # Open in browser if requested
        if args.open:
            webbrowser.open(f"file://{args.output.absolute()}")
            print(f"🌐 Opened in browser: {args.output}")

    except Exception as e:
        print(f"❌ Error generating report: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
