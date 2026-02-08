# Configuration / IaC — Family Contract

> **Family Contract**
>
> This document defines the source‑family contract for **configuration and
> infrastructure‑as‑code systems**. It extends the universal `ADAPTER_CONTRACT.md`
> with configuration‑specific event semantics.
>
> All config adapters (Terraform, Kubernetes manifests, Helm charts, Ansible, etc.)
> must conform to this contract.

---

## 1. Source Family Identity

| Property | Value |
|----------|-------|
| **Family** | `config` |
| **Source Type** | Vendor‑specific (e.g., `terraform`, `kubernetes`, `helm`, `ansible`) |
| **Ordering Mode** | `temporal` |
| **Attestation Tier** | `medium` to `weak` |

---

## 2. Atomic Event: Configuration Snapshot

The atomic event for the Config family is the **configuration snapshot** — the
declared state of infrastructure or application configuration at a point in time.

### Why Snapshot (Not Individual Setting Change)
- Configuration files declare **desired state** — the complete picture matters, not individual deltas
- A single setting change may cascade to many resources
- Snapshots enable drift detection: "does the actual state match the declared state?"
- Config files are committed artifacts — they are versioned systems of record

---

## 3. Ordering: Temporal

Configuration snapshots are ordered **temporally**, tied to commits or apply events.

The adapter MUST:
- emit events in chronological order
- include the commit SHA when the config is version‑controlled
- use `ordering_mode: "temporal"`

---

## 4. Attestation

| Property | Value |
|----------|-------|
| **Attestation type** | `config_snapshot` |
| **Verifier** | Config file hash + commit SHA (or apply event ID) |
| **Trust tier** | `medium` (version‑controlled) or `weak` (runtime‑only state) |
| **Limitations** | Manual edits may bypass version control; drift between declared and applied state |

### Attestation Tier Guidance
- **Medium:** Config files committed to Git (Terraform `.tf`, K8s manifests, Helm values)
- **Weak:** Runtime state dumps not backed by version control (kubectl get, Terraform state without GitOps)

---

## 5. Required Payload Fields

```json
{
  "config_scope": "<string>",
  "config_format": "terraform | kubernetes | helm | ansible | cloudformation | generic",
  "trigger": {
    "commit_sha": "<sha>",
    "apply_id": "<string>"
  },
  "structure": {
    "resource_count": <number>,
    "resource_types": <number>,
    "file_count": <number>
  },
  "diff": {
    "resources_added": <number>,
    "resources_removed": <number>,
    "resources_modified": <number>
  }
}
```

### Field Notes
- `config_scope` identifies what is being configured (e.g., "production-cluster", "staging-vpc", "app-settings")
- `config_format` identifies the configuration system
- `trigger.commit_sha` links to the version control event (when available)
- `trigger.apply_id` links to the apply/deploy event (when config is applied separately from commit)
- `structure` provides a structural summary of the current configuration state
- `diff` summarizes what changed from the previous snapshot

### Format‑Specific Mapping

| Config Format | Resource → | Resource Type → |
|--------------|-----------|----------------|
| Terraform | Managed resource | Resource type (aws_instance, etc.) |
| Kubernetes | K8s object | Kind (Deployment, Service, etc.) |
| Helm | Release resource | Chart template type |
| Ansible | Managed host/task | Module type |

---

## 6. Optional Payload Fields

| Field | Description |
|-------|-------------|
| `drift_detected` | Boolean — does applied state differ from declared state? |
| `environments` | List of environments this config targets |
| `secrets_referenced` | Count of secret/sensitive value references (not values) |
| `resource_names` | List of managed resource identifiers |
| `plan_summary` | Terraform plan or equivalent (add/change/destroy counts) |

---

## 7. Phase 2 Metrics (Config Reference)

| Metric | Description | Derived From |
|--------|-------------|-------------|
| `resource_count` | Total managed resources | `payload.structure.resource_count` |
| `resource_type_count` | Distinct resource types | `payload.structure.resource_types` |
| `config_churn` | Total additions + removals + modifications | `payload.diff` |
| `growth_rate` | Net resource additions per snapshot | `diff.added - diff.removed` |
| `file_count` | Number of config files | `payload.structure.file_count` |

---

## 8. Cross‑Source Correlation Anchors

| Anchor | Correlates With |
|--------|----------------|
| `trigger.commit_sha` | Git family (which commit changed the config) |
| `trigger.apply_id` | Deployment family (config applied as part of deployment) |
| Resource growth | Dependency family (does infra grow with dependencies?) |
| Config churn | CI family (does config instability correlate with build failures?) |
| Drift detection | Security family (unmanaged drift may introduce vulnerabilities) |

---

## 9. Vendor Implementations

| Vendor | Source Type | Status | Notes |
|--------|-----------|--------|-------|
| Terraform | `terraform` | Planned | Parse `.tf` files + state — reference implementation |
| Kubernetes | `kubernetes` | Planned | Parse manifest files or cluster state |
| Helm | `helm` | Planned | Parse chart templates + values |
| Ansible | `ansible` | Planned | Parse playbooks and inventory |
| CloudFormation | `cloudformation` | Planned | Parse templates |

---

## 10. Invariants

1. **One event per snapshot change** (not per resource)
2. **Temporal ordering** (by commit or apply time)
3. **Structural summary required** (resource counts and types)
4. **Diff from previous snapshot required** (additions, removals, modifications)
5. **No secret values in payload** (reference counts only, never actual secrets)
6. **Same config files → same event** (determinism)

---

> **Summary:**
> A configuration snapshot is a temporally ordered record of declared infrastructure state.
> The Config adapter preserves what is configured and how it changes — without
> evaluating whether the configuration is correct or secure.
