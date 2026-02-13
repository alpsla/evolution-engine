# Test Execution — Family Contract

> **Family Contract**
>
> This document defines the source‑family contract for **test execution systems**.
> It extends the universal `ADAPTER_CONTRACT.md` with test‑specific event semantics,
> attestation rules, and payload requirements.
>
> All test adapters (JUnit XML, pytest, Jest, Go test, TAP, etc.) must conform
> to this contract.

---

## 1. Source Family Identity

| Property | Value |
|----------|-------|
| **Family** | `testing` |
| **Source Type** | Vendor‑specific (e.g., `junit_xml`, `pytest`, `jest`) |
| **Ordering Mode** | `temporal` |
| **Attestation Tier** | `medium` |

---

## 2. Atomic Event: Test Suite Run

The atomic event for the Testing family is the **test suite run** — a complete
execution of a test suite producing a structured result report.

### Why Test Suite Run (Not Individual Test Case)
- A suite run is the **smallest complete assessment** — it has a trigger, a set of results, and a verdict
- Individual test cases lack independent context (a single test failure means different things depending on what else passed)
- Test suite runs are what CI systems consume and report on
- Individual test case evolution is tracked *within* the payload, not as separate events

---

## 3. Ordering: Temporal

Test suite runs are ordered **temporally** by execution time.

The adapter MUST:
- emit events in chronological order (oldest → newest)
- include the trigger reference (commit SHA) when available
- use `ordering_mode: "temporal"`

Test runs do not form causal chains — a later run does not "depend on" an earlier run.

---

## 4. Attestation

Test execution provides **medium attestation**.

| Property | Value |
|----------|-------|
| **Attestation type** | `test_run` |
| **Verifier** | Report hash + commit SHA (when available) |
| **Trust tier** | `medium` |
| **Limitations** | Reports can be regenerated, manually edited, or selectively published |

### Why Medium (Not Strong)
- Test reports are not content‑addressed by most systems
- Reports can be regenerated with different outcomes (flaky tests)
- Some systems allow manual result editing
- Selective reporting (omitting failed suites) is possible

---

## 5. Required Payload Fields

Every Testing adapter MUST include the following fields in the `SourceEvent.payload`:

```json
{
  "suite_name": "<string>",
  "trigger": {
    "commit_sha": "<sha>",
    "branch": "<string>"
  },
  "execution": {
    "started_at": "<ISO-8601>",
    "completed_at": "<ISO-8601>",
    "duration_seconds": <number>
  },
  "summary": {
    "total": <number>,
    "passed": <number>,
    "failed": <number>,
    "skipped": <number>,
    "errored": <number>
  },
  "cases": [
    {
      "name": "<string>",
      "classname": "<string>",
      "status": "passed | failed | skipped | errored",
      "duration_seconds": <number>
    }
  ]
}
```

### Field Notes
- `suite_name` identifies the test suite (e.g., "unit", "integration", "e2e")
- `trigger.commit_sha` links the run to a version control event
- `summary` provides aggregate counts without requiring case‑level analysis
- `cases` preserves individual test identities for evolution tracking
- `cases[].classname` provides structural grouping (package, module, file)

---

## 6. Optional Payload Fields

| Field | Description |
|-------|-------------|
| `failure_messages` | Failure details per failed case (truncated, not full stack traces) |
| `coverage` | Code coverage percentage (if reported alongside tests) |
| `environment` | Execution environment (OS, runtime version) |
| `ci_run_ref` | Reference to the CI run that executed these tests |
| `tags` | Test categorization tags (smoke, regression, etc.) |

---

## 7. Phase 2 Metrics (Testing Reference)

| Metric | Description | Derived From |
|--------|-------------|-------------|
| `total_tests` | Total test count per run | `payload.summary.total` |
| `failure_rate` | Fraction of tests that failed | `summary.failed / summary.total` |
| `skip_rate` | Fraction of tests skipped | `summary.skipped / summary.total` |
| `suite_duration` | Total execution time | `payload.execution.duration_seconds` |
| `new_test_ratio` | Fraction of test names not seen in prior window | `payload.cases[].name` across window |
| `flake_score` | Tests that alternate pass/fail across runs without code changes | `cases[].status` across window with same `commit_sha` |

---

## 8. Cross‑Source Correlation Anchors

| Anchor | Correlates With |
|--------|----------------|
| `trigger.commit_sha` | Git family (which code change triggered these tests) |
| `ci_run_ref` | CI family (which pipeline executed these tests) |
| Test failures | Schema changes (breaking contract → test failures) |
| `total_tests` trend | Git family (test-to-code ratio evolution) |

---

## 9. Vendor Implementations

| Vendor | Source Type | Status | Notes |
|--------|-----------|--------|-------|
| JUnit XML | `junit_xml` | Planned | Most universal format — reference implementation |
| pytest | `pytest` | Planned | JSON output or JUnit XML export |
| Jest | `jest` | Planned | JSON reporter output |
| Go test | `go_test` | Planned | JSON output (`go test -json`) |
| TAP | `tap` | Planned | Test Anything Protocol |

---

## 10. Invariants

1. **One event per suite run** (not per test case)
2. **Temporal ordering** (no causal chains between runs)
3. **Medium attestation** (report hash + commit SHA)
4. **Trigger reference required** (enables cross‑source correlation)
5. **Case‑level detail preserved** (individual test names in payload for evolution tracking)
6. **Same report → same events** (determinism)

---

> **Summary:**
> A test suite run is a temporally ordered, system‑attested assessment of system behavior.
> The Testing adapter preserves what passed, failed, and changed — without interpreting why.
