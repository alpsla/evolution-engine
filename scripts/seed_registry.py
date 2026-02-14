#!/usr/bin/env python3
"""
Seed the pattern registry with calibration patterns.

Reads universal_patterns.json and POSTs them to the registry handler.

Usage:
    python scripts/seed_registry.py [--url URL]

Default URL: https://codequal.dev/api/patterns
"""

import argparse
import hashlib
import json
import secrets
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://codequal.dev/api/patterns"
PATTERNS_FILE = Path(__file__).parent.parent / "evolution" / "data" / "universal_patterns.json"

# Generate a stable seed instance ID (distinct from real user instances)
SEED_INSTANCE_ID = hashlib.sha256(b"evo-seed-calibration").hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser(description="Seed the pattern registry")
    parser.add_argument("--url", default=DEFAULT_URL, help="Registry endpoint URL")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending")
    args = parser.parse_args()

    if not PATTERNS_FILE.exists():
        print(f"Error: {PATTERNS_FILE} not found")
        sys.exit(1)

    data = json.loads(PATTERNS_FILE.read_text())
    patterns = data.get("patterns", [])
    print(f"Loaded {len(patterns)} patterns from {PATTERNS_FILE.name}")

    # Strip fields that are local to calibration (repos_observed)
    clean = []
    for p in patterns:
        cp = {k: v for k, v in p.items() if k != "repos_observed"}
        # Add a seed attestation
        cp["attestations"] = [{
            "instance_id": SEED_INSTANCE_ID,
            "signature": "0" * 64,  # placeholder — seed doesn't have a real secret
            "timestamp": int(time.time()),
            "ee_version": "seed",
        }]
        clean.append(cp)

    payload = {
        "level": 2,
        "instance_id": SEED_INSTANCE_ID,
        "patterns": clean,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if args.dry_run:
        print(json.dumps(payload, indent=2)[:2000])
        print(f"\n... ({len(json.dumps(payload))} bytes total)")
        return

    body = json.dumps(payload).encode("utf-8")
    print(f"Posting {len(body)} bytes to {args.url}")

    req = urllib.request.Request(
        args.url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode("utf-8"))
        print(f"Response: {json.dumps(result, indent=2)}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {body}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
