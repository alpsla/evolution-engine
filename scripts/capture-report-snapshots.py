#!/usr/bin/env python3
"""
Capture HTML report as viewport screenshots for VHS demo injection.

VHS records the terminal only — can't scroll a browser. This script captures
the report at scroll positions (top → bottom) so the tape can display them
sequentially via chafa/viu, simulating a scroll.

Usage:
  python scripts/capture-report-snapshots.py .evo/report.html
  python scripts/capture-report-snapshots.py http://127.0.0.1:8485/TOKEN

Output: .evo/demo-report-1.png, demo-report-2.png, ... (in same dir as report)
Requires: pip install playwright && playwright install chromium
"""

import sys
from pathlib import Path

# Add project root for evolution imports if needed
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def capture_snapshots(source: str, out_dir: Path, count: int = 5, viewport_h: int = 700) -> list[Path]:
    """Capture N viewport screenshots at scroll positions. Returns list of PNG paths."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install: pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1200, "height": viewport_h})
        page = context.new_page()

        if source.startswith("http://") or source.startswith("https://"):
            page.goto(source, wait_until="networkidle", timeout=15000)
        else:
            path = Path(source).resolve()
            if not path.exists():
                print(f"Report not found: {path}", file=sys.stderr)
                sys.exit(1)
            page.goto(path.as_uri(), wait_until="networkidle", timeout=10000)

        total_height = page.evaluate("document.documentElement.scrollHeight")
        viewport_height = viewport_h
        max_scroll = max(0, total_height - viewport_height)

        for i in range(count):
            # Scroll position: 0, 25%, 50%, 75%, 100%
            y = int(max_scroll * i / (count - 1)) if count > 1 else 0
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(200)  # Let render settle

            out_path = out_dir / f"demo-report-{i + 1}.png"
            page.screenshot(path=str(out_path))
            paths.append(out_path)

        browser.close()

    return paths


def main():
    if len(sys.argv) < 2:
        print("Usage: capture-report-snapshots.py <report.html|URL> [--count N]", file=sys.stderr)
        sys.exit(1)

    source = sys.argv[1]
    count = 5
    if "--count" in sys.argv:
        idx = sys.argv.index("--count")
        if idx + 1 < len(sys.argv):
            count = int(sys.argv[idx + 1])

    if source.startswith("http"):
        out_dir = Path(".evo")  # CWD when running from demo-repo
    else:
        report_path = Path(source).resolve()
        out_dir = report_path.parent

    paths = capture_snapshots(source, out_dir, count=count)
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
