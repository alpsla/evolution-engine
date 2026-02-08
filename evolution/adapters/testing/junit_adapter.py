"""
JUnit XML Source Adapter (Testing Reference)

Emits canonical SourceEvent payloads for JUnit XML test reports.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/testing/FAMILY_CONTRACT.md (testing family)

Accepts:
  - A directory of JUnit XML files, or
  - A list of pre-parsed test run dicts (for testing / fixtures)
"""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


class JUnitXMLAdapter:
    source_family = "testing"
    source_type = "junit_xml"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, report_dir: str = None, runs: list = None, source_id: str = None):
        """
        Args:
            report_dir: Path to directory containing JUnit XML files
            runs: Pre-parsed list of test run dicts (for fixtures/testing)
            source_id: Unique identifier for this adapter instance
        """
        self.report_dir = Path(report_dir) if report_dir else None
        self._fixture_runs = runs
        self.source_id = source_id or f"junit_xml:{report_dir or 'fixture'}"

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _parse_xml(self, xml_path: Path) -> dict:
        """Parse a JUnit XML report into a normalized test run dict."""
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Handle both <testsuites> and <testsuite> root elements
        if root.tag == "testsuites":
            suites = list(root)
        else:
            suites = [root]

        cases = []
        total = passed = failed = skipped = errored = 0
        total_time = 0.0

        for suite in suites:
            suite_name = suite.get("name", "unknown")
            for tc in suite.findall("testcase"):
                name = tc.get("name", "unknown")
                classname = tc.get("classname", "")
                duration = float(tc.get("time", "0"))
                total_time += duration

                if tc.find("failure") is not None:
                    status = "failed"
                    failed += 1
                elif tc.find("error") is not None:
                    status = "errored"
                    errored += 1
                elif tc.find("skipped") is not None:
                    status = "skipped"
                    skipped += 1
                else:
                    status = "passed"
                    passed += 1

                total += 1
                cases.append({
                    "name": name,
                    "classname": classname,
                    "status": status,
                    "duration_seconds": round(duration, 3),
                })

        return {
            "suite_name": suites[0].get("name", "unknown") if suites else "unknown",
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errored": errored,
            },
            "execution": {
                "duration_seconds": round(total_time, 3),
            },
            "cases": cases,
        }

    def _iter_from_files(self):
        """Parse JUnit XML files from report_dir."""
        xml_files = sorted(self.report_dir.glob("*.xml"))
        for xml_path in xml_files:
            run = self._parse_xml(xml_path)
            yield run

    def iter_events(self):
        if self._fixture_runs is not None:
            runs = self._fixture_runs
        elif self.report_dir and self.report_dir.exists():
            runs = list(self._iter_from_files())
        else:
            return

        # Sort by execution time (temporal ordering)
        runs.sort(key=lambda r: r.get("execution", {}).get("started_at", ""))

        for run in runs:
            # Build attestation verifier from report content
            report_hash = self._hash(json.dumps(run, sort_keys=True))

            payload = {
                "suite_name": run.get("suite_name", "unknown"),
                "trigger": run.get("trigger", {
                    "commit_sha": run.get("commit_sha", ""),
                    "branch": run.get("branch", ""),
                }),
                "execution": {
                    "started_at": run.get("execution", {}).get("started_at", ""),
                    "completed_at": run.get("execution", {}).get("completed_at", ""),
                    "duration_seconds": run.get("execution", {}).get("duration_seconds", 0.0),
                },
                "summary": run.get("summary", {}),
                "cases": run.get("cases", []),
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "test_run",
                    "report_hash": report_hash,
                    "commit_sha": payload["trigger"].get("commit_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
