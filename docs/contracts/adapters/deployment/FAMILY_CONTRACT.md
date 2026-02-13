# Deployment / Release — Family Contract

> **Family Contract**
>
> This document defines the source‑family contract for **deployment and release
> systems**. It extends the universal `ADAPTER_CONTRACT.md` with deployment‑specific
> event semantics.
>
> All deployment adapters (GitHub Releases, ArgoCD, Kubernetes rollouts, etc.)
> must conform to this contract.

---

## 1. Source Family Identity

| Property | Value |
|----------|-------|
| **Family** | `deployment` |
| **Source Type** | Vendor‑specific (e.g., `github_releases`, `argocd`, `kubernetes`, `vercel`) |
| **Ordering Mode** | `temporal` |
| **Attestation Tier** | `medium` |

---

## 2. Atomic Event: Deployment Event

The atomic event for the Deployment family is the **deployment event** — a
version of the software shipped to a specific environment.

### Why Deployment Event (Not Release Tag or Artifact)
- A deployment represents **software reaching an environment** — it has a target, a version, and an outcome
- Release tags are version control artifacts (Git family handles those)
- Container images and artifacts are intermediate — deployments are when they become active
- Rollbacks are also deployment events (deploying a previous version)

---

## 3. Ordering: Temporal

Deployments are ordered **temporally** by deployment time.

The adapter MUST:
- emit events in chronological order
- include the deployed version reference (commit SHA or tag)
- use `ordering_mode: "temporal"`

Multiple deployments may occur concurrently (different environments, canary rollouts).

---

## 4. Attestation

| Property | Value |
|----------|-------|
| **Attestation type** | `deployment` |
| **Verifier** | Deployment ID + commit SHA + environment |
| **Trust tier** | `medium` |
| **Limitations** | Deployment records can be deleted; manual deployments may lack full metadata |

---

## 5. Required Payload Fields

```json
{
  "deployment_id": "<string>",
  "environment": "<string>",
  "trigger": {
    "type": "automated | manual | rollback | scheduled",
    "commit_sha": "<sha>",
    "ref": "<tag-or-branch>"
  },
  "status": "success | failure | in_progress | cancelled",
  "timing": {
    "initiated_at": "<ISO-8601>",
    "completed_at": "<ISO-8601>",
    "duration_seconds": <number>
  },
  "version": "<deployed version string or tag>"
}
```

### Field Notes
- `environment` identifies the deployment target (production, staging, preview, etc.)
- `trigger.type` distinguishes automated deploys from manual actions and rollbacks
- `trigger.commit_sha` links the deployment to a specific code version
- `status` is the final outcome — rollbacks are separate events with `trigger.type: "rollback"`
- `version` is the human‑readable version identifier (tag, semver, or short SHA)

---

## 6. Optional Payload Fields

| Field | Description |
|-------|-------------|
| `previous_version` | Version deployed immediately before this one |
| `is_rollback` | Boolean — true if this deployment reverts to a prior version |
| `artifact` | Deployed artifact identifier (container image, package URL) |
| `ci_run_ref` | Reference to the CI run that produced this deployment |
| `pr_number` | Pull request associated with this deployment |
| `canary_percentage` | Traffic percentage if canary/progressive rollout |
| `approver` | Who approved the deployment (if human‑gated) |

---

## 7. Phase 2 Metrics (Deployment Reference)

| Metric | Description | Derived From |
|--------|-------------|-------------|
| `deployment_frequency` | Deployments per time window | Event count per window |
| `failure_rate` | Fraction of deployments that failed | `payload.status` |
| `rollback_rate` | Fraction of deployments that are rollbacks | `payload.trigger.type == "rollback"` |
| `deploy_duration` | Time from initiation to completion | `payload.timing.duration_seconds` |
| `commit_lag` | Time between commit and deployment | `payload.timing.initiated_at - commit.authored_at` (cross‑source) |

---

## 8. Cross‑Source Correlation Anchors

| Anchor | Correlates With |
|--------|----------------|
| `trigger.commit_sha` | Git family (what code was deployed) |
| `ci_run_ref` | CI family (which build produced this deployment) |
| Rollbacks | Test family (did tests predict the failure?) |
| Deployment frequency | Git family (does commit velocity match deploy velocity?) |
| Failed deployments | Schema family (did a breaking change cause the failure?) |

---

## 9. Vendor Implementations

| Vendor | Source Type | Status | Notes |
|--------|-----------|--------|-------|
| GitHub Releases/Deployments | `github_releases` | Planned | Reference implementation |
| ArgoCD | `argocd` | Planned | GitOps deployment history |
| Kubernetes | `kubernetes` | Planned | Rollout history via kubectl/API |
| Vercel | `vercel` | Planned | Deployment API |
| AWS CodeDeploy | `aws_codedeploy` | Planned | |

---

## 10. Invariants

1. **One event per deployment** (not per artifact or container)
2. **Temporal ordering** (chronological by deployment time)
3. **Environment required** (production vs staging are different signals)
4. **Rollbacks are events** (not erasures — a rollback creates a new deployment event)
5. **Commit reference required** (enables cross‑source correlation)
6. **Same deployment record → same event** (determinism)

---

> **Summary:**
> A deployment event is a temporally ordered record of software reaching an environment.
> The Deployment adapter preserves what was shipped, where, and when — without
> evaluating whether the deployment was wise.
