# Adapter Contracts — Source Family Registry

> This directory organizes **source‑family contracts** for the Evolution Engine.
>
> Each subdirectory represents a **source family** — a category of truth sources
> that share the same atomic event model and Phase 2 metric structure,
> even though their vendor APIs and data formats differ.

---

## The World Map

The Evolution Engine observes the **entire software development lifecycle**
through 8 source families:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SOFTWARE DEVELOPMENT LIFECYCLE                       │
│                                                                         │
│  ┌────────────────┐   ┌────────────────┐   ┌────────────────────────┐  │
│  │ 1. VERSION     │──▶│ 2. CI / BUILD  │──▶│ 3. TEST EXECUTION      │  │
│  │    CONTROL     │   │    PIPELINE    │   │                        │  │
│  │    git/        │   │    ci/         │   │    testing/            │  │
│  └───────┬────────┘   └───────┬────────┘   └───────────┬────────────┘  │
│          │                    │                         │               │
│          ▼                    ▼                         ▼               │
│  ┌────────────────┐   ┌────────────────┐   ┌────────────────────────┐  │
│  │ 4. DEPENDENCY  │   │ 5. SCHEMA /    │   │ 6. DEPLOYMENT /        │  │
│  │    GRAPH       │   │    API         │   │    RELEASE             │  │
│  │    dependency/ │   │    schema/     │   │    deployment/         │  │
│  └────────────────┘   └────────────────┘   └────────────────────────┘  │
│                                                                         │
│  ┌────────────────┐   ┌────────────────┐                               │
│  │ 7. CONFIG /    │   │ 8. SECURITY    │                               │
│  │    IaC         │   │    SCANNING    │                               │
│  │    config/     │   │    security/   │                               │
│  └────────────────┘   └────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
docs/adapters/
 ├── README.md                         ← You are here
 ├── git/FAMILY_CONTRACT.md            ← Version Control
 ├── ci/FAMILY_CONTRACT.md             ← CI / Build Pipeline
 ├── testing/FAMILY_CONTRACT.md        ← Test Execution
 ├── dependency/FAMILY_CONTRACT.md     ← Dependency Graph / SBOM
 ├── schema/FAMILY_CONTRACT.md         ← Schema / API Evolution
 ├── deployment/FAMILY_CONTRACT.md     ← Deployment / Release
 ├── config/FAMILY_CONTRACT.md         ← Configuration / IaC
 └── security/FAMILY_CONTRACT.md       ← Security Scanning
```

---

## Family Summary

| # | Family | Directory | Atomic Event | Ordering | Trust | Reference Adapter | Status |
|---|--------|-----------|-------------|----------|-------|-------------------|--------|
| 1 | Version Control | `git/` | Commit | Causal | Strong | Git | ✅ Implemented |
| 2 | CI / Build Pipeline | `ci/` | Workflow run | Temporal | Medium | GitHub Actions | 🚧 Adapter ready |
| 3 | Test Execution | `testing/` | Test suite run | Temporal | Medium | JUnit XML | 📋 Contract defined |
| 4 | Dependency Graph | `dependency/` | Dependency snapshot | Temporal | Medium | npm / pip | 📋 Contract defined |
| 5 | Schema / API | `schema/` | Schema version | Temporal/Causal | Medium | OpenAPI | 📋 Contract defined |
| 6 | Deployment / Release | `deployment/` | Deployment event | Temporal | Medium | GitHub Releases | 📋 Contract defined |
| 7 | Configuration / IaC | `config/` | Config snapshot | Temporal | Medium–Weak | Terraform | 📋 Contract defined |
| 8 | Security Scanning | `security/` | Scan result | Temporal | Medium | Dependabot | 📋 Contract defined |

---

## Cross‑Source Correlation Map

All families share a universal correlation anchor: **`commit_sha`**.

```
                          commit_sha
                             │
     ┌──────────┬────────────┼────────────┬──────────────┐
     ▼          ▼            ▼            ▼              ▼
   Git ◄─────► CI ◄──────► Tests      Schema       Deploy
     │          │            │            │              │
     │          └────────────┼────────────┘              │
     │       "CI fails when  │  "Schema change           │
     │        tests flake"   │   before test failure"    │
     │                       │                           │
     └───────────────────────┼───────────────────────────┘
     "Broad commits          │              "Deploys after
      correlate with         │               vuln spikes"
      slow builds"           │
                        Dependency ◄──────── Security
                        "New deps introduce vulnerabilities"
                             │
                          Config
                        "Infra grows with dependencies"
```

Phase 4 (Pattern Learning) discovers these correlations automatically.
No family needs to know about any other family.

---

## Relationship to Universal Adapter Contract

The **universal contract** (`docs/ADAPTER_CONTRACT.md`) defines what *all* adapters must do.
Family contracts define what adapters *within that family* must additionally guarantee.

```
Universal Adapter Contract (ADAPTER_CONTRACT.md)
     │
     ├── git/FAMILY_CONTRACT.md
     │    └── Vendors: Git (✅), GitHub, GitLab, Bitbucket
     │
     ├── ci/FAMILY_CONTRACT.md
     │    └── Vendors: GitHub Actions (🚧), GitLab CI, Jenkins, CircleCI
     │
     ├── testing/FAMILY_CONTRACT.md
     │    └── Vendors: JUnit XML, pytest, Jest, Go test, TAP
     │
     ├── dependency/FAMILY_CONTRACT.md
     │    └── Vendors: npm, pip, cargo, go_mod, CycloneDX, SPDX
     │
     ├── schema/FAMILY_CONTRACT.md
     │    └── Vendors: OpenAPI, GraphQL, Protobuf, Avro, DB Migrations
     │
     ├── deployment/FAMILY_CONTRACT.md
     │    └── Vendors: GitHub Releases, ArgoCD, Kubernetes, Vercel
     │
     ├── config/FAMILY_CONTRACT.md
     │    └── Vendors: Terraform, Kubernetes, Helm, Ansible, CloudFormation
     │
     └── security/FAMILY_CONTRACT.md
          └── Vendors: Dependabot, Snyk, Trivy, Grype, SonarQube
```

---

## Adding a New Vendor to an Existing Family

1. Read the family's `FAMILY_CONTRACT.md`
2. Implement the `SourceAdapter` interface for the new vendor
3. The adapter must emit events conforming to the family's payload specification
4. Place the implementation in `evolution/adapters/<family>/`
5. Phase 2 metrics defined for the family apply automatically

---

## Adding a New Source Family

1. Create a new directory under `docs/adapters/`
2. Write a `FAMILY_CONTRACT.md` that defines:
   - Atomic event type
   - Ordering mode (causal or temporal)
   - Attestation tier and verification method
   - Required and optional payload fields
   - Phase 2 reference metrics
   - Cross‑source correlation anchors
3. Create matching `evolution/adapters/<family>/` directory
4. Implement at least one vendor adapter
5. Update this README and `docs/ADAPTER_CONTRACT.md`

---

## What Is NOT a Family (And Why)

| Candidate | Decision | Reason |
|-----------|----------|--------|
| Code Quality / Linting | Git Phase 2 metrics | Linter results are derived from code — they're a *view* of Git data, not an independent source |
| Documentation | Git Phase 2 metrics | Doc files change via commits; doc coverage is a Git metric |
| Project Management / Issues | Excluded (for now) | Issues describe human process, not system structure |
| Container / Artifact Registry | Under Deployment | Images are deployment artifacts; image evolution is a Deployment metric |
| Runtime Telemetry | Excluded (Architecture Vision) | Explicitly a non‑goal — not a system of record |

---

## Implementation Priority

| Priority | Family | Rationale |
|----------|--------|-----------|
| 1 | Version Control | ✅ Done — reference implementation |
| 2 | CI / Build Pipeline | 🚧 Unlocks Phase 4 (correlation requires 2+ engines) |
| 3 | Test Execution | Strongest cross‑correlation with CI + Git |
| 4 | Dependency Graph | Critical for AI‑influenced development (dep sprawl detection) |
| 5 | Schema / API | Data flow evolution — how interfaces change |
| 6 | Security Scanning | Natural extension of dependency monitoring |
| 7 | Deployment / Release | Completes the delivery pipeline picture |
| 8 | Configuration / IaC | Important but lower urgency for most users |

---

> **Guiding Principle:**
> Each new adapter extends the system's observability without requiring changes to Phase 2, 3, or 4.
> The family structure ensures that adding a new vendor is incremental, not architectural.
