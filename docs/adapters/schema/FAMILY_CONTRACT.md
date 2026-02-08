# Schema / API Evolution — Family Contract

> **Family Contract**
>
> This document defines the source‑family contract for **schema and API
> definition systems**. It extends the universal `ADAPTER_CONTRACT.md` with
> schema‑specific event semantics.
>
> All schema adapters (OpenAPI, GraphQL, Protobuf, database migrations, etc.)
> must conform to this contract.

---

## 1. Source Family Identity

| Property | Value |
|----------|-------|
| **Family** | `schema` |
| **Source Type** | Vendor‑specific (e.g., `openapi`, `graphql`, `protobuf`, `db_migration`) |
| **Ordering Mode** | `temporal` (or `causal` for migration chains) |
| **Attestation Tier** | `medium` |

---

## 2. Atomic Event: Schema Version

The atomic event for the Schema family is the **schema version** — a specific
revision of a data contract (API specification, message schema, or database
migration).

### Why Schema Version (Not Field Change)
- A schema version represents a **coherent contract state** — all endpoints, types, and fields at one point in time
- Individual field changes lack context (adding a field may be paired with removing another)
- Schema versions are the unit of compatibility assessment
- Versioned specs and ordered migrations are the systems of record

---

## 3. Ordering

Schema events may use **either ordering mode**:

- **Temporal:** For schema files versioned by commit (OpenAPI specs, GraphQL SDL)
- **Causal:** For migration chains where each migration references its predecessor (database migrations)

The adapter MUST declare which mode applies and use it consistently.

---

## 4. Attestation

| Property | Value |
|----------|-------|
| **Attestation type** | `schema_version` |
| **Verifier** | Schema file hash + commit SHA (or migration sequence ID) |
| **Trust tier** | `medium` |
| **Limitations** | Schema files can be manually edited; migration order can be ambiguous in branching workflows |

---

## 5. Required Payload Fields

```json
{
  "schema_name": "<string>",
  "schema_format": "openapi | graphql | protobuf | avro | db_migration",
  "version": "<string or sequence number>",
  "trigger": {
    "commit_sha": "<sha>"
  },
  "structure": {
    "endpoint_count": <number>,
    "type_count": <number>,
    "field_count": <number>
  },
  "diff": {
    "endpoints_added": <number>,
    "endpoints_removed": <number>,
    "fields_added": <number>,
    "fields_removed": <number>,
    "types_added": <number>,
    "types_removed": <number>
  }
}
```

### Field Notes
- `schema_name` identifies the API or schema (e.g., "user-service-api", "events-schema")
- `schema_format` identifies the specification format
- `version` is the schema's own version identifier (semver, sequence number, or commit-derived)
- `structure` provides a structural summary of the current schema state
- `diff` summarizes structural changes from the previous version
- For database migrations: `endpoint_count` maps to table count, `field_count` maps to column count

### Format‑Specific Mapping

| Schema Format | Endpoint → | Type → | Field → |
|--------------|------------|--------|---------|
| OpenAPI | API paths | Schema objects | Object properties |
| GraphQL | Query/Mutation fields | Types | Type fields |
| Protobuf | Service methods | Messages | Message fields |
| DB Migration | Tables | — | Columns |

---

## 6. Optional Payload Fields

| Field | Description |
|-------|-------------|
| `breaking_changes` | List of changes classified as breaking (removed required fields, type changes) |
| `deprecations` | Newly deprecated endpoints or fields |
| `endpoints` | Full list of endpoint/path names |
| `types` | Full list of type/schema names |
| `migration_sql` | Raw migration content (for DB migrations, truncated) |

---

## 7. Phase 2 Metrics (Schema Reference)

| Metric | Description | Derived From |
|--------|-------------|-------------|
| `endpoint_count` | Total API endpoints or tables | `payload.structure.endpoint_count` |
| `field_count` | Total fields across all types | `payload.structure.field_count` |
| `schema_churn` | Total additions + removals normalized by size | `payload.diff` |
| `breaking_change_rate` | Fraction of versions with breaking changes | `payload.diff.*_removed` |
| `growth_rate` | Net endpoint/field additions per version | `diff.added - diff.removed` |

---

## 8. Cross‑Source Correlation Anchors

| Anchor | Correlates With |
|--------|----------------|
| `trigger.commit_sha` | Git family (which commit changed the schema) |
| Breaking changes | Test family (do breaking changes correlate with test failures?) |
| `endpoint_count` growth | CI family (does API growth slow builds?) |
| Schema churn | Deployment family (does high churn correlate with rollbacks?) |

---

## 9. Vendor Implementations

| Vendor | Source Type | Status | Notes |
|--------|-----------|--------|-------|
| OpenAPI | `openapi` | Planned | Parse JSON/YAML spec files — reference implementation |
| GraphQL | `graphql` | Planned | Parse SDL files |
| Protobuf | `protobuf` | Planned | Parse `.proto` files |
| Avro | `avro` | Planned | Parse `.avsc` schema files or registry |
| DB Migrations (Alembic) | `db_migration` | Planned | Parse migration chain |
| DB Migrations (Flyway) | `db_migration` | Planned | Parse versioned SQL files |

---

## 10. Invariants

1. **One event per schema version** (not per field change)
2. **Structural summary required** (endpoint, type, and field counts)
3. **Diff from previous version required** (additions and removals)
4. **Commit reference required** (enables cross‑source correlation)
5. **No semantic interpretation** (a removed endpoint is a fact, not a "breaking change judgment")
6. **Same schema file → same event** (determinism)

---

> **Summary:**
> A schema version is a versioned, commit‑anchored record of how data contracts
> evolve. The Schema adapter preserves structural shape and change — without
> judging compatibility or intent.
