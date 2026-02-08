"""
Trivy Security Scanner Source Adapter (Security Reference)

Emits canonical SourceEvent payloads for Trivy vulnerability scan results.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/security/FAMILY_CONTRACT.md (security family)

Accepts:
  - A Trivy JSON report file, or
  - A list of pre-parsed scan result dicts (for testing / fixtures)
"""

import hashlib
import json
from pathlib import Path


class TrivyAdapter:
    source_family = "security"
    source_type = "trivy"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, report_file: str = None, scans: list = None,
                 source_id: str = None):
        """
        Args:
            report_file: Path to a Trivy JSON report
            scans: Pre-parsed list of scan result dicts (for fixtures)
            source_id: Unique identifier for this adapter instance
        """
        self.report_file = Path(report_file) if report_file else None
        self._fixture_scans = scans
        self.source_id = source_id or f"trivy:{report_file or 'fixture'}"

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _parse_trivy(self, path: Path) -> dict:
        """Parse a Trivy JSON report into a normalized scan result."""
        data = json.loads(path.read_text(encoding="utf-8"))

        findings = []
        summary = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}

        results = data.get("Results", [])
        for result in results:
            for vuln in result.get("Vulnerabilities", []):
                severity = vuln.get("Severity", "UNKNOWN").lower()
                if severity not in summary:
                    severity = "info"

                summary[severity] += 1
                summary["total"] += 1

                findings.append({
                    "id": vuln.get("VulnerabilityID", "unknown"),
                    "severity": severity,
                    "package": vuln.get("PkgName", "unknown"),
                    "installed_version": vuln.get("InstalledVersion", "unknown"),
                    "fixed_version": vuln.get("FixedVersion"),
                    "title": vuln.get("Title", ""),
                })

        return {
            "scanner": "trivy",
            "scanner_version": data.get("SchemaVersion", "unknown"),
            "scan_target": data.get("ArtifactName", "unknown"),
            "summary": summary,
            "findings": findings,
        }

    def iter_events(self):
        if self._fixture_scans is not None:
            scans = self._fixture_scans
        elif self.report_file and self.report_file.exists():
            parsed = self._parse_trivy(self.report_file)
            scans = [{
                **parsed,
                "trigger": {"type": "manual", "commit_sha": ""},
                "execution": {"started_at": "", "completed_at": ""},
            }]
        else:
            return

        for scan in scans:
            content_hash = self._hash(json.dumps(scan, sort_keys=True))

            payload = {
                "scanner": scan.get("scanner", "trivy"),
                "scanner_version": scan.get("scanner_version", ""),
                "scan_target": scan.get("scan_target", "unknown"),
                "trigger": scan.get("trigger", {}),
                "execution": scan.get("execution", {}),
                "summary": scan.get("summary", {}),
                "findings": scan.get("findings", []),
            }

            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "security_scan",
                    "scan_hash": content_hash,
                    "commit_sha": payload["trigger"].get("commit_sha", ""),
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": None,
                "payload": payload,
            }
