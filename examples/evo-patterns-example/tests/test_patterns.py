"""Tests for evo-patterns-example."""

import json
from pathlib import Path


def test_patterns_json_valid():
    """Verify patterns.json is valid JSON with expected structure."""
    patterns_path = Path(__file__).parent.parent / "evo_patterns_example" / "patterns.json"
    assert patterns_path.exists(), "patterns.json must exist"

    patterns = json.loads(patterns_path.read_text())
    assert isinstance(patterns, list), "patterns.json must be a list"
    assert len(patterns) == 27, "Must have 27 patterns"

    for p in patterns:
        assert "fingerprint" in p, "Pattern must have fingerprint"
        assert "sources" in p, "Pattern must have sources"
        assert "metrics" in p, "Pattern must have metrics"
        assert "pattern_type" in p, "Pattern must have pattern_type"
        assert "discovery_method" in p, "Pattern must have discovery_method"
        assert p.get("scope") in ("community", "universal"), "Scope must be community or universal"
        assert p.get("correlation_strength") is not None, "Must have correlation_strength"


def test_register():
    """Verify register() entry point loads patterns."""
    from evo_patterns_example import register

    patterns = register()
    assert isinstance(patterns, list)
    assert len(patterns) == 27
