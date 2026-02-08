# Version Control — Git Family Contract

> **Family Contract**
>
> This document defines the source‑family contract for **version control systems**
> accessed through Git. It extends the universal `ADAPTER_CONTRACT.md` with
> Git‑specific event semantics, attestation rules, and payload requirements.
>
> All Git‑compatible adapters (bare Git, GitHub, GitLab, Bitbucket, etc.) must
> conform to this contract.

---

## 1. Source Family Identity

| Property | Value |
|----------|-------|
| **Family** | `version_control` |
| **Source Type** | `git` |
| **Ordering Mode** | `causal` (commit graph) |
| **Attestation Tier** | `strong` |

---

## 2. Atomic Event: Commit

The atomic event for the Git family is the **commit object**.

A commit represents one coherent, author‑attested change to the repository.

### Why Commit (Not File, Not PR)
- A commit is the smallest **author‑intended unit of change**
- It carries its own attestation (content‑addressable hash)
- It preserves causal ordering via parent references
- Pull requests and branches are workflow constructs, not structural facts

---

## 3. Ordering: Causal

Git commits form a **directed acyclic graph (DAG)**.

Each commit references zero or more parent commits, establishing causal ordering
without dependence on wall‑clock time.

The adapter MUST:
- emit events in topological order (parents before children)
- include parent commit references in `predecessor_refs`
- handle merge commits (multiple parents) correctly

---

## 4. Attestation

Git provides **strong attestation** via content‑addressable hashing.

| Property | Value |
|----------|-------|
| **Attestation type** | `git_commit` |
| **Verifier** | SHA‑1 / SHA‑256 commit hash |
| **Trust tier** | `strong` |
| **Guarantee** | Hash changes if any content, metadata, or ancestry changes |

The commit hash serves as both identifier and integrity proof.

---

## 5. Required Payload Fields

Every Git adapter MUST include the following fields in the `SourceEvent.payload`:

```json
{
  "commit_hash": "<sha>",
  "parent_commits": ["<sha>", ...],
  "author": {
    "name": "<string>",
    "email": "<string>"
  },
  "committer": {
    "name": "<string>",
    "email": "<string>"
  },
  "authored_at": "<ISO-8601>",
  "committed_at": "<ISO-8601>",
  "message": "<string>",
  "tree_hash": "<sha>",
  "files": ["<path>", ...]
}
```

### Field Notes
- `author` and `committer` MAY differ (e.g., cherry‑picks, rebases)
- `authored_at` and `committed_at` are factual timestamps from Git objects — they are not used for ordering (causal ordering uses the commit graph)
- `files` lists paths modified in this commit relative to its parent(s)
- `message` is preserved verbatim — it is a fact, not an interpretation

---

## 6. Optional Payload Fields

Git adapters MAY include:

| Field | Description |
|-------|-------------|
| `is_merge` | Boolean — true if commit has multiple parents |
| `branch_refs` | Branch names pointing at this commit at time of ingestion |
| `tags` | Tags pointing at this commit |
| `stats` | Insertion/deletion counts per file (if available without cost) |

Optional fields MUST NOT be required by Phase 2 metrics.
Phase 2 metrics MUST function correctly with only the required fields.

---

## 7. Phase 2 Metrics (Git Reference)

The following metrics are defined for the Git family.
Phase 2 implementations MUST support at least these metrics:

| Metric | Description | Derived From |
|--------|-------------|-------------|
| `files_touched` | Number of unique file paths modified | `payload.files` |
| `dispersion` | Entropy of changes across directory hierarchy | `payload.files` |
| `cochange_novelty_ratio` | Fraction of file pairs not seen together before | `payload.files` (across window) |
| `change_locality` | Overlap with recently modified files | `payload.files` (across window) |

Additional metrics MAY be added. Existing metrics MUST NOT be removed
without architectural review.

---

## 8. Vendor Implementations

| Vendor | Adapter | Status | Notes |
|--------|---------|--------|-------|
| Bare Git | `evolution/adapters/git/git_adapter.py` | ✅ Implemented | Reference implementation |
| GitHub | — | Planned | May enrich with PR metadata (optional fields) |
| GitLab | — | Planned | |
| Bitbucket | — | Planned | |

All vendor adapters within this family MUST emit identical `SourceEvent` payloads
for the same repository state. Vendor‑specific metadata belongs in optional fields only.

---

## 9. Invariants

1. **Same repository state → same events** (determinism)
2. **Commit hash is the attestation** (non‑negotiable)
3. **Causal ordering via parent refs** (no wall‑clock dependence)
4. **No derived data in payload** (files list is factual, not computed)

---

> **Summary:**
> A Git commit is a content‑addressed, causally ordered, author‑attested fact.
> The Git adapter preserves these properties without interpretation.
