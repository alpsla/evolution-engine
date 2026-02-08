"""
GitHub Security Advisories Source Adapter

Emits canonical SourceEvent payloads for GitHub Dependabot alerts
and security advisories.
Conforms to:
  - docs/ADAPTER_CONTRACT.md (universal)
  - docs/adapters/security/FAMILY_CONTRACT.md (security family)

Supports:
  - API mode: Fetches Dependabot alerts from GitHub API (requires token)
  - Fixture mode: Pre-parsed scan dicts (for testing)

Note: Dependabot alerts require repo admin access on private repos,
but are available on public repos with the correct Accept header.
"""

import hashlib
import json
import os
from datetime import datetime

from evolution.adapters.github_client import GitHubClient


class GitHubSecurityAdapter:
    source_family = "security"
    source_type = "github_dependabot"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, *, owner: str = None, repo: str = None,
                 token: str = None, client: GitHubClient = None,
                 scans: list = None, source_id: str = None):
        """
        Args:
            owner: GitHub repo owner (API mode)
            repo: GitHub repo name (API mode)
            token: GitHub token (API mode)
            client: Shared GitHubClient instance
            scans: Pre-parsed list of scan dicts (fixture mode)
            source_id: Unique identifier
        """
        self._fixture_scans = scans
        self.source_id = source_id or (
            f"github_security:{owner}/{repo}" if owner else "github_security:fixture"
        )

        if scans is None:
            if client:
                self._client = client
            elif owner and repo:
                self._client = GitHubClient(owner, repo, token)
            else:
                raise RuntimeError("Provide owner+repo, client, or scans.")
        else:
            self._client = None

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _severity_normalize(self, severity: str) -> str:
        """Normalize GitHub severity to our standard levels."""
        mapping = {
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "moderate": "medium",
            "low": "low",
        }
        return mapping.get(severity.lower(), "info") if severity else "info"

    def _fetch_dependabot_alerts(self) -> list:
        """Fetch Dependabot alerts from GitHub API."""
        try:
            alerts = self._client.get_paginated(
                "/dependabot/alerts",
                per_page=100,
            )
        except Exception:
            # Dependabot alerts may not be available (permissions, disabled)
            return []

        alerts.sort(key=lambda a: a.get("created_at", ""))
        return alerts

    def _alerts_to_scan(self, alerts: list) -> dict:
        """Convert a batch of Dependabot alerts into a security scan result."""
        findings = []
        summary = {"total": 0, "critical": 0, "high": 0,
                    "medium": 0, "low": 0, "info": 0}

        for alert in alerts:
            advisory = alert.get("security_advisory", {})
            vuln = alert.get("security_vulnerability", {})
            severity = self._severity_normalize(
                advisory.get("severity", vuln.get("severity", ""))
            )

            summary[severity] = summary.get(severity, 0) + 1
            summary["total"] += 1

            pkg = vuln.get("package", {})
            findings.append({
                "id": advisory.get("ghsa_id", advisory.get("cve_id", "unknown")),
                "severity": severity,
                "package": pkg.get("name", "unknown"),
                "installed_version": vuln.get("vulnerable_version_range", "unknown"),
                "fixed_version": vuln.get("first_patched_version", {}).get("identifier"),
                "title": advisory.get("summary", ""),
                "state": alert.get("state", "open"),
            })

        # Count fixable
        fixable = sum(1 for f in findings if f.get("fixed_version"))

        return {
            "scanner": "github_dependabot",
            "scanner_version": "api",
            "scan_target": f"{self._client.owner}/{self._client.repo}" if self._client else "fixture",
            "trigger": {"type": "automated", "commit_sha": ""},
            "execution": {
                "started_at": alerts[0].get("created_at", "") if alerts else "",
                "completed_at": alerts[-1].get("updated_at", "") if alerts else "",
            },
            "summary": {
                **summary,
                "fixable": fixable,
                "fixable_ratio": fixable / summary["total"] if summary["total"] > 0 else 0,
            },
            "findings": findings,
        }

    def iter_events(self):
        if self._fixture_scans is not None:
            scans = self._fixture_scans
        else:
            alerts = self._fetch_dependabot_alerts()
            if not alerts:
                return
            scans = [self._alerts_to_scan(alerts)]

        for scan in scans:
            content_hash = self._hash(json.dumps(scan, sort_keys=True))

            payload = {
                "scanner": scan.get("scanner", "github_dependabot"),
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
