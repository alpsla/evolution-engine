"""
Cobertura XML Coverage Adapter

Emits canonical SourceEvent payloads for Cobertura XML coverage reports.
The Cobertura format is produced by pytest-cov, istanbul/nyc (JS),
JaCoCo (Java), gcov/gcovr (C/C++), and many other tools.

Accepts:
  - A path to a coverage.xml file, or
  - A list of pre-parsed coverage dicts (for testing / fixtures)
"""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


class CoberturaAdapter:
    source_family = "coverage"
    source_type = "coverage_xml"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, coverage_file: str = None, reports: list = None,
                 source_id: str = None):
        """
        Args:
            coverage_file: Path to a coverage.xml file
            reports: Pre-parsed list of coverage dicts (for fixtures/testing)
            source_id: Unique identifier for this adapter instance
        """
        self.coverage_file = Path(coverage_file) if coverage_file else None
        self._fixture_reports = reports
        self.source_id = source_id or f"coverage_xml:{coverage_file or 'fixture'}"

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _parse_xml(self, xml_path: Path) -> dict:
        """Parse a Cobertura XML report into a normalized coverage dict."""
        tree = ET.parse(xml_path)
        root = tree.getroot()
        return self._parse_root(root)

    @staticmethod
    def _parse_root(root) -> dict:
        """Extract coverage metrics from an ElementTree root."""
        line_rate = float(root.get("line-rate", "0"))
        branch_rate = float(root.get("branch-rate", "0"))
        lines_valid = int(root.get("lines-valid", "0"))
        lines_covered = int(root.get("lines-covered", "0"))
        branches_valid = int(root.get("branches-valid", "0"))
        branches_covered = int(root.get("branches-covered", "0"))

        packages = root.findall(".//package")

        return {
            "line_rate": round(line_rate, 4),
            "branch_rate": round(branch_rate, 4),
            "lines_covered": lines_covered,
            "lines_missing": lines_valid - lines_covered,
            "branches_covered": branches_covered,
            "branches_missing": branches_valid - branches_covered,
            "packages_covered": len(packages),
        }

    def iter_events(self):
        if self._fixture_reports is not None:
            reports = self._fixture_reports
        elif self.coverage_file and self.coverage_file.exists():
            reports = [self._parse_xml(self.coverage_file)]
        else:
            return

        for report in reports:
            report_hash = self._hash(json.dumps(report, sort_keys=True))

            payload = {
                "trigger": report.get("trigger", {}),
                "line_rate": report.get("line_rate", 0.0),
                "branch_rate": report.get("branch_rate", 0.0),
                "lines_covered": report.get("lines_covered", 0),
                "lines_missing": report.get("lines_missing", 0),
                "branches_covered": report.get("branches_covered", 0),
                "branches_missing": report.get("branches_missing", 0),
                "packages_covered": report.get("packages_covered", 0),
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "coverage_report",
                    "report_hash": report_hash,
                    "commit_sha": payload.get("trigger", {}).get("commit_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
