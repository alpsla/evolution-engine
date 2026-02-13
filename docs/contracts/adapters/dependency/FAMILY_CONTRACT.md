# Dependency Graph / SBOM — Family Contract

> **Family Contract**
>
> This document defines the source‑family contract for **dependency graph and
> software bill of materials (SBOM) systems**. It extends the universal
> `ADAPTER_CONTRACT.md` with dependency‑specific event semantics.
>
> All dependency adapters (npm, pip, cargo, SBOM generators, etc.) must conform
> to this contract.

---

## 1. Source Family Identity

| Property | Value |
|----------|-------|
| **Family** | `dependency` |
| **Source Type** | Vendor‑specific (e.g., `npm`, `pip`, `cargo`, `cyclonedx`) |
| **Ordering Mode** | `temporal` |
| **Attestation Tier** | `medium` |

---

## 2. Atomic Event: Dependency Snapshot

The atomic event for the Dependency family is the **dependency snapshot** — the
complete resolved dependency graph at a point in time, as recorded in a lock file
or SBOM.

### Why Snapshot (Not Individual Dependency Change)
- A lock file represents the **complete resolved state** — all dependencies and their transitive tree
- Individual dependency additions/removals lack context (adding one dep may pull in 30 transitive deps)
- Snapshots enable diffing: "what changed between this state and the last?"
- Lock files are committed artifacts — they are the system of record

---

## 3. Ordering: Temporal

Dependency snapshots are ordered **temporally**, tied to the commit that changed them.

The adapter MUST:
- emit events in chronological order
- include the commit SHA that introduced the snapshot change
- use `ordering_mode: "temporal"`

The adapter SHOULD:
- emit events only when the dependency graph actually changes (skip identical snapshots)

---

## 4. Attestation

Dependency snapshots provide **medium attestation**.

| Property | Value |
|----------|-------|
| **Attestation type** | `dependency_snapshot` |
| **Verifier** | Lock file hash + commit SHA |
| **Trust tier** | `medium` |
| **Limitations** | Lock files can be regenerated; transitive resolution depends on registry state at resolve time |

---

## 5. Required Payload Fields

```json
{
  "ecosystem": "<npm | pip | cargo | go | ...>",
  "manifest_file": "<path to lock file>",
  "trigger": {
    "commit_sha": "<sha>"
  },
  "snapshot": {
    "direct_count": <number>,
    "transitive_count": <number>,
    "total_count": <number>,
    "max_depth": <number>
  },
  "dependencies": [
    {
      "name": "<package-name>",
      "version": "<resolved-version>",
      "direct": <boolean>,
      "depth": <number>
    }
  ]
}
```

### Field Notes
- `ecosystem` identifies the package manager (npm, pip, cargo, etc.)
- `manifest_file` is the lock file path relative to the repo root
- `snapshot` provides aggregate statistics without requiring full dependency enumeration
- `dependencies` lists all resolved packages (direct and transitive)
- `direct` distinguishes explicitly declared dependencies from pulled‑in transitive ones
- `depth` is the shortest path from a direct dependency to this package (1 = direct)

---

## 6. Optional Payload Fields

| Field | Description |
|-------|-------------|
| `removed` | Dependencies present in previous snapshot but absent in this one |
| `added` | Dependencies absent in previous snapshot but present in this one |
| `version_changes` | Dependencies whose version changed (with old and new version) |
| `license` | License identifier per dependency |
| `source_registry` | Registry URL (npmjs.org, pypi.org, etc.) |

---

## 7. Phase 2 Metrics (Dependency Reference)

| Metric | Description | Derived From |
|--------|-------------|-------------|
| `dependency_count` | Total resolved dependencies | `payload.snapshot.total_count` |
| `direct_count` | Number of directly declared dependencies | `payload.snapshot.direct_count` |
| `churn_rate` | Fraction of dependencies that changed since last snapshot | `payload.dependencies` diff across window |
| `new_dependency_ratio` | Fraction of dependencies not seen in prior window | `payload.dependencies[].name` across window |
| `max_depth` | Maximum transitive dependency depth | `payload.snapshot.max_depth` |
| `major_version_bump_count` | Count of major version changes | `payload.dependencies[].version` diff |

---

## 8. Cross‑Source Correlation Anchors

| Anchor | Correlates With |
|--------|----------------|
| `trigger.commit_sha` | Git family (which commit changed dependencies) |
| New dependencies | Security family (new deps may introduce vulnerabilities) |
| `dependency_count` trend | Git family (code complexity vs dependency complexity) |
| Major version bumps | Test family (do major bumps correlate with test failures?) |

---

## 9. Vendor Implementations

| Vendor | Source Type | Status | Notes |
|--------|-----------|--------|-------|
| npm | `npm` | Planned | Parse `package-lock.json` |
| pip | `pip` | Planned | Parse `requirements.txt` / `poetry.lock` / `Pipfile.lock` |
| Cargo | `cargo` | Planned | Parse `Cargo.lock` |
| Go modules | `go_mod` | Planned | Parse `go.sum` |
| CycloneDX | `cyclonedx` | Planned | Universal SBOM format |
| SPDX | `spdx` | Planned | Universal SBOM format |

---

## 10. Invariants

1. **One event per snapshot change** (not per dependency)
2. **Temporal ordering** (tied to commit chronology)
3. **Complete graph required** (direct + transitive, not just direct)
4. **Commit reference required** (enables cross‑source correlation)
5. **Same lock file → same event** (determinism)
6. **No vulnerability data in payload** (that belongs to the Security family)

---

> **Summary:**
> A dependency snapshot is a temporally ordered, commit‑anchored record of what
> the system depends on. The Dependency adapter preserves the full resolved graph
> without assessing risk or quality.
