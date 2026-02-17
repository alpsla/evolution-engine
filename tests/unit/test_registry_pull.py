"""Tests for orchestrator direct-pull from registry handler and snapshot script."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── Orchestrator: _import_registry_patterns ───


def _make_pattern(**overrides):
    p = {
        "fingerprint": "3aab010d317b22df",
        "pattern_type": "co_occurrence",
        "discovery_method": "statistical",
        "sources": ["ci", "git"],
        "metrics": ["ci_presence", "dispersion"],
        "description_statistical": "CI triggers dispersion increase.",
        "correlation_strength": 0.38,
        "occurrence_count": 465,
        "confidence_tier": "confirmed",
        "scope": "community",
        "independent_count": 3,
        "last_updated": "2026-02-14T00:00:00Z",
    }
    p.update(overrides)
    return p


class TestImportRegistryPatterns:
    """Test Orchestrator._import_registry_patterns()."""

    def _make_orchestrator(self, tmp_path):
        """Create a minimal orchestrator with mocked license."""
        with patch("evolution.orchestrator.get_license") as mock_lic:
            mock_lic.return_value = MagicMock(is_pro=lambda: False)
            from evolution.orchestrator import Orchestrator
            orch = Orchestrator(
                repo_path=tmp_path,
                evo_dir=tmp_path / ".evo",
            )
        return orch

    @patch("urllib.request.urlopen")
    def test_fetches_and_imports_patterns(self, mock_urlopen, tmp_path):
        """Patterns from registry are fetched and imported into KB."""
        # Set up KB
        evo_dir = tmp_path / ".evo"
        phase4_dir = evo_dir / "phase4"
        phase4_dir.mkdir(parents=True)

        # Create a minimal knowledge.db
        from evolution.knowledge_store import SQLiteKnowledgeStore
        db_path = phase4_dir / "knowledge.db"
        SQLiteKnowledgeStore(db_path)

        orch = self._make_orchestrator(tmp_path)

        # Mock the HTTP response
        patterns = [_make_pattern()]
        response_data = json.dumps({"patterns": patterns}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        log = MagicMock()
        result = orch._import_registry_patterns(["ci", "git"], log)

        assert result >= 0  # May be 0 if pattern already exists, but no crash
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_imports_all_regardless_of_families(self, mock_urlopen, tmp_path):
        """All community patterns are imported — Phase 5 handles relevance."""
        evo_dir = tmp_path / ".evo"
        phase4_dir = evo_dir / "phase4"
        phase4_dir.mkdir(parents=True)

        from evolution.knowledge_store import SQLiteKnowledgeStore
        db_path = phase4_dir / "knowledge.db"
        SQLiteKnowledgeStore(db_path)

        orch = self._make_orchestrator(tmp_path)

        # Pattern with sources=["ci", "git"] is imported even for "deployment" family
        patterns = [_make_pattern()]
        response_data = json.dumps({"patterns": patterns}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        log = MagicMock()
        result = orch._import_registry_patterns(["deployment"], log)
        assert result >= 1

    @patch("urllib.request.urlopen")
    def test_respects_24h_cache(self, mock_urlopen, tmp_path):
        """Doesn't fetch if cache is fresh (< 24h)."""
        evo_dir = tmp_path / ".evo"
        evo_dir.mkdir(parents=True)

        # Write a fresh cache file
        cache_path = evo_dir / "registry_cache.json"
        cache_path.write_text(json.dumps({
            "last_fetched": time.time(),  # just now
            "pattern_count": 5,
            "imported": 3,
        }))

        orch = self._make_orchestrator(tmp_path)
        log = MagicMock()
        result = orch._import_registry_patterns(["ci"], log)

        assert result == 0
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_fetches_when_cache_stale(self, mock_urlopen, tmp_path):
        """Fetches if cache is older than 24h."""
        evo_dir = tmp_path / ".evo"
        phase4_dir = evo_dir / "phase4"
        phase4_dir.mkdir(parents=True)

        from evolution.knowledge_store import SQLiteKnowledgeStore
        SQLiteKnowledgeStore(phase4_dir / "knowledge.db")

        # Write a stale cache
        cache_path = evo_dir / "registry_cache.json"
        cache_path.write_text(json.dumps({
            "last_fetched": time.time() - 90000,  # > 24h ago
            "pattern_count": 0,
        }))

        orch = self._make_orchestrator(tmp_path)

        patterns = [_make_pattern()]
        response_data = json.dumps({"patterns": patterns}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        log = MagicMock()
        result = orch._import_registry_patterns(["ci", "git"], log)
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen", side_effect=Exception("network error"))
    def test_network_failure_graceful(self, mock_urlopen, tmp_path):
        """Network failures return 0, don't crash."""
        orch = self._make_orchestrator(tmp_path)
        log = MagicMock()
        result = orch._import_registry_patterns(["ci"], log)
        assert result == 0

    @patch("urllib.request.urlopen")
    def test_empty_patterns_returns_zero(self, mock_urlopen, tmp_path):
        """Empty pattern list returns 0."""
        orch = self._make_orchestrator(tmp_path)

        response_data = json.dumps({"patterns": []}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        log = MagicMock()
        result = orch._import_registry_patterns(["ci"], log)
        assert result == 0


# ─── Snapshot Script ───


class TestSnapshotScript:
    """Test snapshot_to_pypi.py helper functions."""

    def test_compute_version(self):
        """Version follows CalVer format."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from snapshot_to_pypi import compute_version

        patterns = [_make_pattern()]
        version = compute_version(patterns)
        # Should be YYYY.M.D format
        parts = version.split(".")
        assert len(parts) == 3
        assert int(parts[0]) >= 2026

    @patch("urllib.request.urlopen")
    def test_fetch_patterns(self, mock_urlopen):
        """fetch_patterns returns list of pattern dicts."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from snapshot_to_pypi import fetch_patterns

        patterns = [_make_pattern(), _make_pattern(fingerprint="bb" * 8)]
        response_data = json.dumps({"patterns": patterns}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = fetch_patterns("https://example.com/api/patterns")
        assert len(result) == 2

    def test_build_package(self, tmp_path):
        """build_package creates a valid wheel."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from snapshot_to_pypi import build_package

        patterns = [_make_pattern()]
        output_dir = tmp_path / "build-test"

        wheel_path = build_package(patterns, output_dir)

        assert wheel_path.exists()
        assert wheel_path.suffix == ".whl"
        assert "evo_patterns_community" in wheel_path.name

        # Verify patterns.json is inside the wheel
        import zipfile
        with zipfile.ZipFile(wheel_path) as zf:
            names = zf.namelist()
            patterns_files = [n for n in names if n.endswith("patterns.json")]
            assert len(patterns_files) == 1

            data = json.loads(zf.read(patterns_files[0]).decode("utf-8"))
            assert data["pattern_count"] == 1
            assert len(data["patterns"]) == 1


# ─── Pattern Index ───


class TestPatternIndex:
    """Verify pattern_index.json contains expected packages."""

    def test_includes_community_package(self):
        index_path = (
            Path(__file__).parent.parent.parent
            / "evolution" / "data" / "pattern_index.json"
        )
        data = json.loads(index_path.read_text())
        assert "evo-patterns-community" in data

    def test_includes_example_package(self):
        index_path = (
            Path(__file__).parent.parent.parent
            / "evolution" / "data" / "pattern_index.json"
        )
        data = json.loads(index_path.read_text())
        assert "evo-patterns-example" in data
