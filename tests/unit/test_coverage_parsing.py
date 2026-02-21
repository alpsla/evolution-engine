"""Tests for Cobertura XML coverage parsing and coverage family integration."""

import subprocess
from unittest.mock import MagicMock

import pytest

from evolution.adapters.git.git_history_walker import GitHistoryWalker
from evolution.adapters.testing.coverage_adapter import CoberturaAdapter


# ──────────────── Cobertura XML Fixtures ────────────────

BASIC_COBERTURA_XML = """\
<?xml version="1.0" ?>
<coverage version="5.5" timestamp="1700000000" lines-valid="200" lines-covered="170"
         branches-valid="50" branches-covered="40" line-rate="0.85" branch-rate="0.80"
         complexity="0">
  <packages>
    <package name="myapp" line-rate="0.90" branch-rate="0.85" complexity="0">
      <classes>
        <class name="myapp.core" filename="myapp/core.py" line-rate="0.90" branch-rate="0.85">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="1"/>
            <line number="3" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
    <package name="myapp.utils" line-rate="0.80" branch-rate="0.75" complexity="0">
      <classes/>
    </package>
  </packages>
</coverage>
"""

ZERO_COVERAGE_XML = """\
<?xml version="1.0" ?>
<coverage version="5.5" lines-valid="100" lines-covered="0"
         branches-valid="20" branches-covered="0" line-rate="0.0" branch-rate="0.0">
  <packages/>
</coverage>
"""

FULL_COVERAGE_XML = """\
<?xml version="1.0" ?>
<coverage version="5.5" lines-valid="100" lines-covered="100"
         branches-valid="20" branches-covered="20" line-rate="1.0" branch-rate="1.0">
  <packages>
    <package name="app" line-rate="1.0" branch-rate="1.0" complexity="0">
      <classes/>
    </package>
  </packages>
</coverage>
"""

MALFORMED_XML = """<not valid xml <<<>>>"""


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repo for walker tests."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=str(tmp_path), capture_output=True, check=True,
        env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com",
             "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"},
    )
    return tmp_path


# ──────────────── Parser Tests ────────────────

class TestParseCoberturaBasic:
    """Test the walker's Cobertura XML parser."""

    def test_parse_basic(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["coverage"])
        result = walker._parse_cobertura_xml_content(BASIC_COBERTURA_XML, "abc123")

        assert result is not None
        assert result["line_rate"] == 0.85
        assert result["branch_rate"] == 0.80
        assert result["lines_covered"] == 170
        assert result["lines_missing"] == 30  # 200 - 170
        assert result["branches_covered"] == 40
        assert result["branches_missing"] == 10  # 50 - 40
        assert result["packages_covered"] == 2
        assert result["trigger"]["commit_sha"] == "abc123"


class TestParseCoberturaZero:
    """Test parser handles zero coverage."""

    def test_parse_zero_coverage(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["coverage"])
        result = walker._parse_cobertura_xml_content(ZERO_COVERAGE_XML, "zero1")

        assert result is not None
        assert result["line_rate"] == 0.0
        assert result["branch_rate"] == 0.0
        assert result["lines_covered"] == 0
        assert result["lines_missing"] == 100


class TestParseCoberturaFull:
    """Test parser handles full coverage."""

    def test_parse_full_coverage(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["coverage"])
        result = walker._parse_cobertura_xml_content(FULL_COVERAGE_XML, "full1")

        assert result is not None
        assert result["line_rate"] == 1.0
        assert result["branch_rate"] == 1.0
        assert result["lines_missing"] == 0
        assert result["packages_covered"] == 1


class TestParseCoberturaMalformed:
    """Test graceful handling of invalid XML."""

    def test_parse_malformed(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["coverage"])
        result = walker._parse_cobertura_xml_content(MALFORMED_XML, "bad1")

        assert result is None


class TestWalkerFindsCoverage:
    """Test that the walker processes committed coverage.xml files."""

    def test_walker_finds_coverage_xml(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["coverage"])

        mock_blob = MagicMock()
        mock_blob.data_stream.read.return_value = BASIC_COBERTURA_XML.encode("utf-8")

        mock_tree = MagicMock()
        mock_tree.__truediv__ = MagicMock(return_value=mock_blob)

        mock_commit = MagicMock()
        mock_commit.hexsha = "cov111"
        mock_commit.committed_date = 1700000000
        mock_commit.tree = mock_tree

        results = walker._process_commit(mock_commit)

        coverage_results = [(f, a, t) for f, a, t in results if f == "coverage"]
        assert len(coverage_results) >= 1

        family, adapter, ts = coverage_results[0]
        assert family == "coverage"
        assert isinstance(adapter, CoberturaAdapter)

        events = list(adapter.iter_events())
        assert len(events) == 1
        assert events[0]["source_family"] == "coverage"
        assert events[0]["payload"]["line_rate"] == 0.85


class TestCoberturaAdapterEvents:
    """Test the CoberturaAdapter event emission."""

    def test_adapter_emits_correct_event(self):
        adapter = CoberturaAdapter(
            reports=[{
                "trigger": {"commit_sha": "abc123"},
                "line_rate": 0.92,
                "branch_rate": 0.85,
                "lines_covered": 460,
                "lines_missing": 40,
                "branches_covered": 170,
                "branches_missing": 30,
                "packages_covered": 5,
            }],
            source_id="coverage_xml:test",
        )

        events = list(adapter.iter_events())
        assert len(events) == 1

        event = events[0]
        assert event["source_family"] == "coverage"
        assert event["source_type"] == "coverage_xml"
        assert event["payload"]["line_rate"] == 0.92
        assert event["payload"]["branch_rate"] == 0.85
        assert event["payload"]["lines_covered"] == 460

    def test_adapter_empty_reports(self):
        adapter = CoberturaAdapter(reports=[], source_id="test")
        events = list(adapter.iter_events())
        assert len(events) == 0

    def test_adapter_no_source(self):
        adapter = CoberturaAdapter(source_id="test")
        events = list(adapter.iter_events())
        assert len(events) == 0


class TestPhase2CoverageMetrics:
    """Test Phase 2 emits signals for coverage events."""

    def test_phase2_coverage_metrics(self, tmp_path):
        from evolution.phase1_engine import Phase1Engine
        from evolution.phase2_engine import Phase2Engine

        evo_dir = tmp_path / "evo"
        evo_dir.mkdir()

        phase1 = Phase1Engine(evo_dir)

        # Simulate coverage trending down over 10 commits
        for i in range(10):
            line_rate = 0.95 - (i * 0.02)  # 0.95 → 0.77
            branch_rate = 0.90 - (i * 0.01)
            adapter = CoberturaAdapter(
                reports=[{
                    "trigger": {"commit_sha": f"{i:040x}"},
                    "line_rate": round(line_rate, 4),
                    "branch_rate": round(branch_rate, 4),
                    "lines_covered": int(500 * line_rate),
                    "lines_missing": 500 - int(500 * line_rate),
                    "branches_covered": int(200 * branch_rate),
                    "branches_missing": 200 - int(200 * branch_rate),
                    "packages_covered": 5,
                }],
                source_id="coverage_xml:test",
            )
            phase1.ingest(adapter)

        phase2 = Phase2Engine(evo_dir, window_size=5, min_baseline=3)
        signals = phase2.run_coverage()

        assert len(signals) > 0

        for signal in signals:
            assert signal["engine_id"] == "coverage"
            assert signal["source_type"] == "coverage_xml"
            assert signal["metric"] in ("line_rate", "branch_rate")

        metric_names = {s["metric"] for s in signals}
        assert "line_rate" in metric_names
        assert "branch_rate" in metric_names
