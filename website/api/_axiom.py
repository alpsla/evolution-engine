"""
Shared Axiom ingest helper for Vercel serverless functions.

Sends structured events directly to Axiom's HTTP ingest API.
Works on Vercel Hobby plan (no log drain required).

Environment variables:
  AXIOM_TOKEN   — Axiom API token (create at axiom.co → Settings → API Tokens)
  AXIOM_DATASET — Dataset name (default: "evo")

No-op when AXIOM_TOKEN is not set (safe for local dev).
"""

import json
import os
import urllib.request


_AXIOM_URL = "https://api.axiom.co/v1/datasets/{dataset}/ingest"


def send(event: dict) -> None:
    """Fire-and-forget: send a single event to Axiom. Never raises."""
    token = os.environ.get("AXIOM_TOKEN")
    if not token:
        return

    dataset = os.environ.get("AXIOM_DATASET", "evo")
    url = _AXIOM_URL.format(dataset=dataset)

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps([event]).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # Never block the response
