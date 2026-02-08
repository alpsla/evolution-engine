# CI / Build Pipeline — Family Contract

> **Family Contract**
>
> This document defines the source‑family contract for **continuous integration
> and build pipeline systems**. It extends the universal `ADAPTER_CONTRACT.md`
> with CI‑specific event semantics, attestation rules, and payload requirements.
>
> All CI adapters (GitHub Actions, GitLab CI, Jenkins, CircleCI, etc.) must
> conform to this contract.

---

## 1. Source Family Identity

| Property | Value |
|----------|-------|
| **Family** | `ci` |
| **Source Type** | Vendor‑specific (e.g., `github_actions`, `gitlab_ci`, `jenkins`) |
| **Ordering Mode** | `temporal` |
| **Attestation Tier** | `medium` |

---

## 2. Atomic Event: Workflow Run

The atomic event for the CI family is the **workflow run** (also called pipeline run, build, or execution).

A workflow run represents one complete execution cycle triggered by a source event
(typically a commit, PR, or schedule).

### Why Workflow Run (Not Job, Not Step)
- A workflow run is the **smallest complete execution unit** — it has a trigger, a sequence of work, and a final outcome
- Jobs and steps are nested detail within the run, preserved in the payload
- A run has a clear start, end, and success/failure disposition
- Runs are the unit CI systems use for status reporting and attestation

### Why Not Job or Step as Atomic Event
- Jobs and steps lack independent triggers — they don't represent autonomous decisions
- Their meaning depends on the enclosing run (a failed step in a successful run differs from a failed step in a failed run)
- Treating steps as atomic events would create an explosion of low‑context events

---

## 3. Ordering: Temporal

CI runs are ordered **temporally** (by creation/start time), not causally.

Unlike commits, CI runs do not reference parent runs. Multiple runs may execute
concurrently for different commits or branches.

The adapter MUST:
- emit events in chronological order (oldest → newest)
- include the trigger reference (e.g., commit SHA) to enable cross‑source correlation
- use `ordering_mode: "temporal"`

The adapter MUST NOT:
- fabricate causal ordering between runs
- assume sequential execution

---

## 4. Attestation

CI systems provide **medium attestation**.

| Property | Value |
|----------|-------|
| **Attestation type** | `ci_run` |
| **Verifier** | Run ID + trigger commit SHA |
| **Trust tier** | `medium` |
| **Limitations** | Run IDs are sequential (not content‑addressed). Logs may be deleted. Runs may be re‑triggered. |

### Why Medium (Not Strong)
- CI run IDs are assigned by the CI system, not derived from content
- The same commit can trigger multiple runs with different outcomes
- CI logs and artifacts can be deleted or expired
- Re‑runs create new events for the same logical trigger

The system must handle `medium` trust gracefully — Phase 2 baselines remain valid,
but confidence annotations should reflect the lower attestation tier.

---

## 5. Required Payload Fields

Every CI adapter MUST include the following fields in the `SourceEvent.payload`:

```json
{
  "run_id": "<string|number>",
  "workflow_name": "<string>",
  "trigger": {
    "type": "push | pull_request | schedule | manual | workflow_dispatch",
    "ref": "<branch-or-tag>",
    "commit_sha": "<sha>"
  },
  "status": "success | failure | cancelled | skipped",
  "timing": {
    "created_at": "<ISO-8601>",
    "started_at": "<ISO-8601>",
    "completed_at": "<ISO-8601>",
    "duration_seconds": <number>
  },
  "jobs": [
    {
      "name": "<string>",
      "status": "success | failure | cancelled | skipped",
      "duration_seconds": <number>
    }
  ]
}
```

### Field Notes
- `run_id` is the CI system's identifier for this execution
- `trigger.commit_sha` links the run to a version control event (enables cross‑source correlation in Phase 4)
- `status` is the final outcome of the entire workflow
- `timing` uses wall‑clock timestamps — these are factual metadata, not used for causal ordering
- `jobs` is an ordered list of jobs within the run — this provides structural detail without making jobs separate events
- `duration_seconds` is measured by the CI system, not computed by the adapter

---

## 6. Optional Payload Fields

CI adapters MAY include:

| Field | Description |
|-------|-------------|
| `run_attempt` | Attempt number if re‑triggered |
| `runner` | Execution environment (OS, labels, self‑hosted flag) |
| `steps` | Nested step‑level detail within jobs |
| `artifacts` | List of produced artifacts (names, sizes) |
| `logs_available` | Boolean — whether logs are still retrievable |
| `pr_number` | Pull request number if triggered by PR |
| `branch` | Branch name |

Optional fields MUST NOT be required by Phase 2 metrics.
Phase 2 metrics MUST function correctly with only the required fields.

---

## 7. Phase 2 Metrics (CI Reference)

The following metrics are defined for the CI family.
Phase 2 implementations MUST support at least these metrics:

| Metric | Description | Derived From |
|--------|-------------|-------------|
| `run_duration` | Total workflow run duration in seconds | `payload.timing.duration_seconds` |
| `failure_rate` | Binary success/failure (1.0 or 0.0) per run | `payload.status` |
| `job_count` | Number of jobs in the workflow | `payload.jobs` |
| `job_topology_hash` | Hash of job names and order (detects structural changes) | `payload.jobs[].name` |

### Metric Notes

**`run_duration`** — Baseline: rolling mean and stddev of run durations. Deviation detects builds that are significantly slower or faster than normal. Slowdowns may indicate growing test suites, dependency issues, or infrastructure degradation.

**`failure_rate`** — Baseline: rolling failure rate (0.0 to 1.0). Deviation detects spikes in failure frequency. A sustained failure rate increase is a strong signal.

**`job_count`** — Baseline: typical number of jobs per run. Deviation detects workflow expansion or contraction. Sudden increases may indicate CI configuration changes.

**`job_topology_hash`** — Baseline: hash stability. A change in topology (new jobs, removed jobs, reordered jobs) is a structural deviation. This metric detects CI pipeline evolution.

Additional metrics MAY be added. Existing metrics MUST NOT be removed
without architectural review.

---

## 8. Cross‑Source Correlation Anchor

The CI family has a natural correlation anchor with the Version Control family:

```
CI Event → trigger.commit_sha → Git Event → attestation.commit_hash
```

This enables Phase 4 to correlate:
- "When broad commits happen, do builds take longer?"
- "When co‑change novelty is high, do failure rates increase?"
- "When dispersion spikes, does job topology change?"

The adapter MUST include `trigger.commit_sha` to enable this correlation.
The adapter MUST NOT perform the correlation itself.

---

## 9. Vendor Implementations

| Vendor | Source Type | Adapter | Status | Notes |
|--------|-----------|---------|--------|-------|
| GitHub Actions | `github_actions` | — | 🚧 Next | Reference implementation |
| GitLab CI | `gitlab_ci` | — | Planned | |
| Jenkins | `jenkins` | — | Planned | |
| CircleCI | `circleci` | — | Planned | |
| Azure Pipelines | `azure_pipelines` | — | Planned | |

All vendor adapters within this family MUST emit payloads conforming to
Section 5. Vendor‑specific data belongs in optional fields only.

---

## 10. Invariants

1. **One event per workflow run** (not per job or step)
2. **Temporal ordering** (no fabricated causal chains)
3. **Medium attestation** (run ID + commit SHA, not content‑addressed)
4. **Trigger reference required** (enables cross‑source correlation)
5. **No derived data in payload** (durations are measured, not computed)
6. **Same API response → same events** (determinism)

---

## 11. Differences from Git Family

| Aspect | Git | CI |
|--------|-----|-----|
| Atomic event | Commit | Workflow run |
| Ordering | Causal (DAG) | Temporal (chronological) |
| Attestation | Strong (content‑addressed) | Medium (system‑assigned) |
| Identity | Commit hash (immutable) | Run ID (mutable — re‑runs possible) |
| Trigger | Author action | Automated (push, PR, schedule) |
| Cross‑ref | Self‑contained | Links to commit via `trigger.commit_sha` |

These differences are expected and handled by the architecture.
Phase 2, Phase 3, and Phase 4 are designed to work with any ordering mode
and any attestation tier.

---

> **Summary:**
> A CI workflow run is a temporally ordered, system‑attested, trigger‑linked fact.
> The CI adapter preserves execution outcomes without interpreting success or failure.
