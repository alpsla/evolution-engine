# Security Scanning — Family Contract

> **Family Contract**
>
> This document defines the source‑family contract for **security scanning and
> vulnerability assessment systems**. It extends the universal `ADAPTER_CONTRACT.md`
> with security‑scan‑specific event semantics.
>
> All security adapters (Dependabot, Snyk, Trivy, Grype, SonarQube, etc.)
> must conform to this contract.

---

## 1. Source Family Identity

| Property | Value |
|----------|-------|
| **Family** | `security` |
| **Source Type** | Vendor‑specific (e.g., `dependabot`, `snyk`, `trivy`, `sonarqube`) |
| **Ordering Mode** | `temporal` |
| **Attestation Tier** | `medium` |

---

## 2. Atomic Event: Scan Result

The atomic event for the Security family is the **scan result** — a complete
vulnerability assessment report produced by a security scanning tool at a
point in time.

### Why Scan Result (Not Individual Vulnerability)
- A scan result represents the **complete vulnerability inventory** at one moment — the full exposure picture
- Individual vulnerabilities lack context (10 lows may matter less than 1 critical)
- Scan results are the unit of comparison: "are we better or worse than last scan?"
- New vulnerabilities may appear without any code change (external CVE disclosure)

---

## 3. Ordering: Temporal

Scan results are ordered **temporally** by scan execution time.

The adapter MUST:
- emit events in chronological order
- include the commit SHA when the scan targets a specific code version
- use `ordering_mode: "temporal"`

Security scans may be triggered by:
- code changes (commit‑driven)
- scheduled scans (no commit reference)
- external events (new CVE published)

When no commit SHA is available, `trigger.commit_sha` MAY be null.

---

## 4. Attestation

| Property | Value |
|----------|-------|
| **Attestation type** | `security_scan` |
| **Verifier** | Scan ID + tool version + commit SHA (when available) |
| **Trust tier** | `medium` |
| **Limitations** | Scan coverage varies by tool; false positives are common; not all vulnerabilities are detectable |

---

## 5. Required Payload Fields

```json
{
  "scanner": "<tool-name>",
  "scanner_version": "<string>",
  "scan_target": "<string>",
  "trigger": {
    "type": "commit | schedule | manual | advisory",
    "commit_sha": "<sha or null>"
  },
  "execution": {
    "started_at": "<ISO-8601>",
    "completed_at": "<ISO-8601>"
  },
  "summary": {
    "total": <number>,
    "critical": <number>,
    "high": <number>,
    "medium": <number>,
    "low": <number>,
    "info": <number>
  },
  "findings": [
    {
      "id": "<CVE or finding ID>",
      "severity": "critical | high | medium | low | info",
      "package": "<affected package>",
      "installed_version": "<version>",
      "fixed_version": "<version or null>",
      "title": "<short description>"
    }
  ]
}
```

### Field Notes
- `scanner` identifies the scanning tool
- `scan_target` identifies what was scanned (repo path, container image, lock file)
- `trigger.type` distinguishes code‑driven scans from scheduled or advisory‑driven scans
- `summary` provides severity‑bucketed counts without requiring finding‑level analysis
- `findings` preserves individual vulnerability details for evolution tracking
- `findings[].fixed_version` being null means no fix is available yet

---

## 6. Optional Payload Fields

| Field | Description |
|-------|-------------|
| `resolved_since_last` | Findings present in previous scan but absent in this one |
| `new_since_last` | Findings absent in previous scan but present in this one |
| `suppressed` | Findings explicitly suppressed or accepted (with reason) |
| `ci_run_ref` | Reference to the CI run that executed this scan |
| `cvss_scores` | CVSS score per finding |
| `exploitability` | Known‑exploited status per finding (KEV catalog) |

---

## 7. Phase 2 Metrics (Security Reference)

| Metric | Description | Derived From |
|--------|-------------|-------------|
| `vulnerability_count` | Total findings | `payload.summary.total` |
| `critical_count` | Critical severity findings | `payload.summary.critical` |
| `new_finding_rate` | Newly introduced findings per scan | `payload.findings` diff across window |
| `resolution_rate` | Findings resolved since last scan | `resolved_since_last` count |
| `mean_finding_age` | Average age of unresolved findings (in scans, not days) | Finding persistence across window |
| `fixable_ratio` | Fraction of findings with available fixes | `findings[].fixed_version != null` |

---

## 8. Cross‑Source Correlation Anchors

| Anchor | Correlates With |
|--------|----------------|
| `trigger.commit_sha` | Git family (which code change introduced vulnerabilities) |
| `ci_run_ref` | CI family (security scan as part of pipeline) |
| `findings[].package` | Dependency family (which dependency introduced the vulnerability) |
| New critical findings | Deployment family (should deployment be reconsidered?) |
| `vulnerability_count` trend | Git family (does rapid development increase exposure?) |

---

## 9. Vendor Implementations

| Vendor | Source Type | Status | Notes |
|--------|-----------|--------|-------|
| GitHub Dependabot | `dependabot` | Planned | GitHub Security Advisories API — reference implementation |
| Snyk | `snyk` | Planned | Snyk API or CLI JSON output |
| Trivy | `trivy` | Planned | JSON output format |
| Grype | `grype` | Planned | JSON output format |
| SonarQube | `sonarqube` | Planned | Security hotspots and vulnerabilities API |
| OWASP ZAP | `owasp_zap` | Planned | Dynamic scanning results |

---

## 10. Invariants

1. **One event per scan execution** (not per finding)
2. **Temporal ordering** (by scan execution time)
3. **Severity summary required** (bucketed counts)
4. **Finding‑level detail preserved** (individual CVEs in payload)
5. **Commit reference when available** (enables cross‑source correlation)
6. **No remediation advice in payload** (the adapter observes, not recommends)
7. **Same scan output → same event** (determinism)

---

## 11. Important Distinction

The Security family observes **vulnerability inventory evolution** — how the set
of known vulnerabilities changes over time. It does NOT:
- recommend patches
- block deployments
- assess overall security posture
- assign risk scores

These belong to Phase 4 (pattern learning) and Phase 5 (advisory) layers.

---

> **Summary:**
> A scan result is a temporally ordered inventory of known vulnerabilities.
> The Security adapter preserves what was found and when — without deciding
> what to do about it.
