#!/usr/bin/env python3
"""
Snapshot community patterns from registry to a PyPI-publishable wheel.

Reads aggregated patterns from GET /api/patterns, builds an
evo-patterns-community package, and optionally uploads via twine.

Usage:
    # Build only (creates dist/evo_patterns_community-*.whl)
    python scripts/snapshot_to_pypi.py --build

    # Build and upload to PyPI
    python scripts/snapshot_to_pypi.py --build --upload

    # Build and upload to Test PyPI
    python scripts/snapshot_to_pypi.py --build --upload --test-pypi

    # Dry run: fetch and show stats without building
    python scripts/snapshot_to_pypi.py
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = "https://codequal.dev/api/patterns"
PACKAGE_NAME = "evo-patterns-community"
PACKAGE_DIR_NAME = "evo_patterns_community"


def fetch_patterns(url: str) -> list[dict]:
    """Fetch all patterns from the registry handler."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode("utf-8"))
    return data.get("patterns", [])


def compute_version(patterns: list[dict]) -> str:
    """Compute a version string from current date + pattern count.

    Format: YYYY.MM.DD (CalVer) so each snapshot gets a unique version.
    """
    now = datetime.now(timezone.utc)
    return f"{now.year}.{now.month}.{now.day}"


def build_package(patterns: list[dict], output_dir: Path) -> Path:
    """Build a pip-installable wheel from the fetched patterns."""
    pkg_dir = output_dir / PACKAGE_DIR_NAME
    version = compute_version(patterns)

    # Clean and create package directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    pkg_dir.mkdir(parents=True)

    # patterns.json
    patterns_data = {
        "version": version,
        "generated_by": "scripts/snapshot_to_pypi.py",
        "snapshot_time": datetime.now(timezone.utc).isoformat(),
        "pattern_count": len(patterns),
        "patterns": patterns,
    }
    (pkg_dir / "patterns.json").write_text(json.dumps(patterns_data, indent=2))

    # __init__.py
    (pkg_dir / "__init__.py").write_text(textwrap.dedent(f'''\
        """
        {PACKAGE_NAME} — Community-aggregated Evolution Engine patterns.

        Auto-generated snapshot from the community registry.
        Version: {version} ({len(patterns)} patterns)
        """

        import json
        from pathlib import Path


        def register():
            """Entry point for pattern loading."""
            patterns_path = Path(__file__).parent / "patterns.json"
            if not patterns_path.exists():
                return []
            data = json.loads(patterns_path.read_text())
            if isinstance(data, dict):
                return data.get("patterns", [])
            return data
    '''))

    # pyproject.toml
    (output_dir / "pyproject.toml").write_text(textwrap.dedent(f'''\
        [build-system]
        requires = ["setuptools>=68.0"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "{PACKAGE_NAME}"
        version = "{version}"
        description = "Evolution Engine community patterns — aggregated from the community registry"
        license = {{text = "MIT"}}
        requires-python = ">=3.9"
        authors = [{{name = "CodeQual", email = "info@codequal.dev"}}]
        classifiers = [
            "Development Status :: 4 - Beta",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: MIT License",
            "Programming Language :: Python :: 3",
        ]

        [project.urls]
        Homepage = "https://codequal.dev"
        Repository = "https://github.com/codequaldev/evolution-engine"

        [project.entry-points."evo.patterns"]
        {PACKAGE_NAME} = "{PACKAGE_DIR_NAME}:register"

        [tool.setuptools.package-data]
        {PACKAGE_DIR_NAME} = ["patterns.json"]
    '''))

    # README.md
    families = set()
    for p in patterns:
        for s in p.get("sources", []):
            families.add(s)

    (output_dir / "README.md").write_text(textwrap.dedent(f"""\
        # {PACKAGE_NAME}

        Community-aggregated patterns for [Evolution Engine](https://codequal.dev).

        - **{len(patterns)}** patterns across **{len(families)}** families
        - Families: {', '.join(sorted(families))}
        - Auto-generated from the community registry

        ## Usage

        This package is auto-fetched by `evo analyze`. No manual install needed.

        To add manually:
        ```bash
        evo patterns add {PACKAGE_NAME}
        ```
    """))

    # Build the wheel
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", str(output_dir)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Build failed:\n{result.stderr}")
        sys.exit(1)

    # Find the built wheel
    dist_dir = output_dir / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    if not wheels:
        print("No wheel found after build")
        sys.exit(1)

    return wheels[0]


def upload_wheel(wheel_path: Path, test_pypi: bool = False):
    """Upload wheel to PyPI via twine."""
    cmd = [sys.executable, "-m", "twine", "upload"]
    if test_pypi:
        cmd.extend(["--repository", "testpypi"])
    cmd.append(str(wheel_path))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Upload failed:\n{result.stderr}")
        sys.exit(1)
    print(f"Uploaded {wheel_path.name}")


def main():
    parser = argparse.ArgumentParser(description="Snapshot registry patterns to PyPI")
    parser.add_argument("--url", default=DEFAULT_URL, help="Registry endpoint URL")
    parser.add_argument("--build", action="store_true", help="Build wheel")
    parser.add_argument("--upload", action="store_true", help="Upload to PyPI (requires --build)")
    parser.add_argument("--test-pypi", action="store_true", help="Upload to Test PyPI instead")
    parser.add_argument("--output-dir", default=None, help="Build output directory")
    args = parser.parse_args()

    print(f"Fetching patterns from {args.url}...")
    patterns = fetch_patterns(args.url)
    print(f"  {len(patterns)} patterns fetched")

    if not patterns:
        print("No patterns available. Nothing to do.")
        return

    # Show stats
    families = set()
    confirmed = 0
    for p in patterns:
        for s in p.get("sources", []):
            families.add(s)
        if p.get("confidence_tier") == "confirmed":
            confirmed += 1

    print(f"  {len(families)} families: {', '.join(sorted(families))}")
    print(f"  {confirmed} confirmed, {len(patterns) - confirmed} emerging")

    if not args.build:
        print("\nUse --build to create a wheel, --upload to publish.")
        return

    output_dir = Path(args.output_dir) if args.output_dir else Path("build") / "patterns-snapshot"
    print(f"\nBuilding wheel in {output_dir}...")
    wheel_path = build_package(patterns, output_dir)
    print(f"  Built: {wheel_path}")

    if args.upload:
        print(f"\nUploading to {'Test PyPI' if args.test_pypi else 'PyPI'}...")
        upload_wheel(wheel_path, test_pypi=args.test_pypi)


if __name__ == "__main__":
    main()
