"""Tests for JUnit XML parsing and testing family integration."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.adapters.git.git_history_walker import GitHistoryWalker
from evolution.adapters.testing.junit_adapter import JUnitXMLAdapter


# ──────────────── JUnit XML Fixtures ────────────────

BASIC_JUNIT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="MyTests" tests="4" failures="1" errors="0" skipped="1" time="2.5">
  <testcase name="test_add" classname="math_tests" time="0.5"/>
  <testcase name="test_sub" classname="math_tests" time="1.0">
    <failure message="AssertionError">Expected 3 got 4</failure>
  </testcase>
  <testcase name="test_mul" classname="math_tests" time="0.8"/>
  <testcase name="test_div" classname="math_tests" time="0.2">
    <skipped message="division not implemented"/>
  </testcase>
</testsuite>
"""

TESTSUITES_JUNIT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="AllTests">
  <testsuite name="Suite1" tests="2" failures="0">
    <testcase name="test_a" classname="s1" time="0.1"/>
    <testcase name="test_b" classname="s1" time="0.2"/>
  </testsuite>
  <testsuite name="Suite2" tests="1" failures="1">
    <testcase name="test_c" classname="s2" time="0.3">
      <failure message="fail">oops</failure>
    </testcase>
  </testsuite>
</testsuites>
"""

EMPTY_JUNIT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Empty" tests="0" failures="0" errors="0"/>
"""

ERROR_JUNIT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="ErrorSuite" tests="2">
  <testcase name="test_ok" classname="errs" time="0.1"/>
  <testcase name="test_crash" classname="errs" time="0.5">
    <error message="NullPointerException">stack trace here</error>
  </testcase>
</testsuite>
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

class TestParseJunitXmlBasic:
    """Test the walker's _parse_junit_xml_content with a basic <testsuite> root."""

    def test_parse_junit_xml_basic(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["testing"])
        result = walker._parse_junit_xml_content(BASIC_JUNIT_XML, "abc123", "junit.xml")

        assert result is not None
        assert result["suite_name"] == "MyTests"
        assert result["summary"]["total"] == 4
        assert result["summary"]["passed"] == 2
        assert result["summary"]["failed"] == 1
        assert result["summary"]["skipped"] == 1
        assert result["summary"]["errored"] == 0
        assert result["execution"]["duration_seconds"] == 2.5
        assert result["trigger"]["commit_sha"] == "abc123"


class TestParseJunitXmlTestsuitesRoot:
    """Test parser handles <testsuites> wrapper."""

    def test_parse_junit_xml_testsuites_root(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["testing"])
        result = walker._parse_junit_xml_content(TESTSUITES_JUNIT_XML, "def456")

        assert result is not None
        assert result["summary"]["total"] == 3
        assert result["summary"]["passed"] == 2
        assert result["summary"]["failed"] == 1
        assert result["execution"]["duration_seconds"] == 0.6


class TestParseJunitXmlEmpty:
    """Test parser handles empty testsuite (no testcases)."""

    def test_parse_junit_xml_empty(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["testing"])
        result = walker._parse_junit_xml_content(EMPTY_JUNIT_XML, "empty1")

        assert result is not None
        assert result["summary"]["total"] == 0
        assert result["summary"]["passed"] == 0
        assert result["summary"]["failed"] == 0


class TestParseJunitXmlErrorElement:
    """Test parser counts <error> elements as errored."""

    def test_parse_junit_xml_error_element(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["testing"])
        result = walker._parse_junit_xml_content(ERROR_JUNIT_XML, "err1")

        assert result is not None
        assert result["summary"]["total"] == 2
        assert result["summary"]["passed"] == 1
        assert result["summary"]["errored"] == 1
        assert result["summary"]["failed"] == 0


class TestParseJunitXmlDuration:
    """Test that suite duration is summed from testcase times."""

    def test_parse_junit_xml_duration(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["testing"])
        result = walker._parse_junit_xml_content(BASIC_JUNIT_XML, "dur1")

        # 0.5 + 1.0 + 0.8 + 0.2 = 2.5
        assert result["execution"]["duration_seconds"] == 2.5


class TestParseJunitXmlMalformed:
    """Test graceful handling of invalid XML."""

    def test_parse_junit_xml_malformed(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["testing"])
        result = walker._parse_junit_xml_content(MALFORMED_XML, "bad1")

        assert result is None


class TestWalkerFindsJunitXml:
    """Test that the walker processes committed junit.xml files."""

    def test_walker_finds_junit_xml(self, git_repo):
        walker = GitHistoryWalker(repo_path=str(git_repo), target_families=["testing"])

        # Mock commit with junit.xml in tree
        mock_blob = MagicMock()
        mock_blob.data_stream.read.return_value = BASIC_JUNIT_XML.encode("utf-8")

        mock_tree = MagicMock()
        mock_tree.__truediv__ = MagicMock(return_value=mock_blob)

        mock_commit = MagicMock()
        mock_commit.hexsha = "aaa111"
        mock_commit.committed_date = 1700000000
        mock_commit.tree = mock_tree

        results = walker._process_commit(mock_commit)

        # Should find at least one testing result
        testing_results = [(f, a, t) for f, a, t in results if f == "testing"]
        assert len(testing_results) >= 1

        family, adapter, ts = testing_results[0]
        assert family == "testing"
        assert isinstance(adapter, JUnitXMLAdapter)

        # Verify the adapter emits events
        events = list(adapter.iter_events())
        assert len(events) == 1
        assert events[0]["source_family"] == "testing"
        assert events[0]["payload"]["summary"]["total"] == 4


class TestPhase2TestingMetrics:
    """Test Phase 2 emits signals for testing events."""

    def test_phase2_testing_metrics(self, tmp_path):
        from evolution.phase1_engine import Phase1Engine
        from evolution.phase2_engine import Phase2Engine

        evo_dir = tmp_path / "evo"
        evo_dir.mkdir()

        # Ingest testing events via Phase 1
        phase1 = Phase1Engine(evo_dir)

        for i in range(10):
            total = 100 + i
            failed = i % 3
            skipped = i % 2
            adapter = JUnitXMLAdapter(
                runs=[{
                    "suite_name": "TestSuite",
                    "trigger": {"commit_sha": f"{i:040x}"},
                    "execution": {
                        "started_at": f"2026-01-{10+i:02d}T10:00:00Z",
                        "completed_at": f"2026-01-{10+i:02d}T10:01:00Z",
                        "duration_seconds": 60.0 + i,
                    },
                    "summary": {
                        "total": total,
                        "passed": total - failed - skipped,
                        "failed": failed,
                        "skipped": skipped,
                    },
                    "cases": [],
                }],
                source_id="junit_xml:test",
            )
            phase1.ingest(adapter)

        # Run Phase 2
        phase2 = Phase2Engine(evo_dir, window_size=5, min_baseline=3)
        signals = phase2.run_testing()

        # Should produce signals
        assert len(signals) > 0

        # Check signal structure
        for signal in signals:
            assert signal["engine_id"] == "testing"
            assert signal["source_type"] == "junit_xml"
            assert signal["metric"] in ("total_tests", "failure_rate", "skip_rate", "suite_duration")
            assert "observed" in signal
            assert "baseline" in signal
            assert "deviation" in signal

        # Verify all four metrics are represented
        metric_names = {s["metric"] for s in signals}
        assert "total_tests" in metric_names
        assert "failure_rate" in metric_names
        assert "suite_duration" in metric_names
