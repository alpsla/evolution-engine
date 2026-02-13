# Phase 5 — Advisory & Evidence Layer Design

> **Design Reference**
>
> This document defines the design of **Phase 5 (Advisory & Evidence Layer)**.
> It explains *how* advisories and evidence packages are compiled and presented
> while strictly conforming to `PHASE_5_CONTRACT.md`.

---

## 1. Design Goals

Phase 5 is designed to:

1. Show users what changed compared to their system's normal behavior
2. Provide historical pattern context when available
3. Include enough specific evidence for immediate investigation
4. Support multiple presentation formats (dashboard, chat, API)
5. Enable AI coding assistants to consume and act on the evidence

The primary success criterion is:

> **A user (or their AI assistant) can go from "something changed" to "here's exactly what to look at" in under 30 seconds.**

---

## 2. Architecture

```
Phase 2 Signals ────────┐
Phase 3 Explanations ───┤
Phase 4 Knowledge ──────┤
Phase 1 Event Metadata ─┤
                        ▼
              ┌──────────────────┐
              │  Advisory Engine  │
              │                  │
              │  1. Significance │  ← Which signals matter?
              │     Filter       │
              │                  │
              │  2. Evidence     │  ← Which artifacts are involved?
              │     Collector    │
              │                  │
              │  3. Pattern      │  ← Have we seen this before?
              │     Matcher      │
              │                  │
              │  4. Formatter    │  ← Render for target platform
              └────────┬─────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │   JSON   │ │  Human   │ │   Chat   │
    │   API    │ │ Summary  │ │  Format  │
    └──────────┘ └──────────┘ └──────────┘
```

---

## 3. Advisory Pipeline

### 3.1 Significance Filter

Not all signals warrant inclusion in an advisory. The filter selects signals where:
- Deviation exceeds a configurable threshold (default: ±1.5 stddev)
- Confidence is at least `accumulating`
- The signal is from the current reporting window

Signals below the threshold are still stored (Phase 2) but not surfaced in the advisory.

### 3.2 Evidence Collector

For each significant signal, the collector traces back to Phase 1 events:

1. `signal.event_ref` → Phase 1 event
2. Phase 1 event → payload artifacts (commits, files, tests, deps, etc.)
3. Cross‑reference: "Which Phase 1 events from OTHER families share the same `commit_sha`?"

This produces the evidence chain: signal → event → specific artifacts.

### 3.3 Pattern Matcher

Query Phase 4 KB with the current signal fingerprint:
- If match found: include pattern context in advisory
- If no match: omit pattern section (don't say "no patterns" — just present the changes)

### 3.4 Formatter

Renders the compiled advisory into the target format.

---

## 4. Human Summary Design

### 4.1 "Normal vs Now" Comparison

Each significant change is presented as a comparison:

```
[Family Icon] [Metric Name]

  Normal:  [baseline mean ± stddev, in human terms]
  Now:     [observed value, in human terms]

  [Visual bar comparing the two]

  [One-sentence Phase 3 explanation, simplified]
```

### 4.2 Visual Comparisons

For numeric metrics, use proportional bars:

```
Normally: ████████████░░░░░░░░  12 endpoints
Now:      ██████████████████░░  18 endpoints  ← 2.3x growth
```

### 4.3 Pattern Context Block

When a known pattern matches:

```
🔍 PATTERN RECOGNITION

  These changes match a known pattern: "[pattern name]"
  Seen [N] times across [M] projects.

  What it typically looks like:
  [semantic description from Knowledge Artifact]

  How long this usually lasts:
  [temporal context from pattern history]
```

### 4.4 Tone Rules

- Use comparative language: "typically X, now Y"
- Avoid alarmist language: no "warning", "danger", "critical"
- Present magnitudes in human terms: "2.3x faster" not "2.3 standard deviations"
- State facts: "14 tests are failing" not "tests are broken"

---

## 5. Evidence Package Design

### 5.1 Structure

The evidence package groups artifacts by category:

```
EVIDENCE PACKAGE
├── Commits Involved
│   ├── SHA, message, author, date, files
│   └── ...
├── Files Affected
│   ├── path, change type, first seen in which commit
│   └── ...
├── Tests Impacted
│   ├── name, was passing / now failing, since when
│   └── ...
├── Dependencies Changed
│   ├── name, added/removed/upgraded, version
│   └── ...
├── Timeline
│   ├── chronological events across all families
│   └── ...
└── Investigation Prompt (optional)
    └── Pre-built prompt for AI assistant
```

### 5.2 Timeline

The timeline merges events from all families into a single chronological view:

```
Feb 3, 10:14  [git]        Commit a3f9c2 — "Add user management API v2"
Feb 3, 10:22  [ci]         Build #847 — passed (142s)
Feb 3, 11:00  [testing]    Test run — 3 failures (test_auth_flow)
Feb 4, 09:30  [git]        Commit b7d1e4 — "Wire up FastAPI dependencies"
Feb 4, 09:45  [dependency] Snapshot — +3 direct deps (fastapi, httpx, uvicorn)
Feb 4, 10:12  [security]   Scan — 2 new vulnerabilities (in httpx transitive)
Feb 4, 14:00  [git]        Commit c92fa8 — "Add payment endpoints"
Feb 4, 14:15  [testing]    Test run — 5 failures (+2: test_user_create, test_payment)
```

This timeline enables the user to see the causal chain: which event caused which consequence.

### 5.3 Investigation Prompt

Pre‑built prompt template:

```
Here is a structural analysis of [project] over the period [from] to [to].

CHANGES DETECTED:
[formatted changes list]

EVIDENCE:
[formatted evidence package]

Based on this evidence:
1. What is the most likely root cause of the observed changes?
2. Which specific files should be reviewed first?
3. Are there any dependency or configuration changes that may explain the test failures?
```

The system generates this prompt but does NOT execute it. The user copies it to their preferred AI tool.

---

## 6. Chat Format Design

For Telegram, Slack, Discord:

```
📋 Evolution Report — my-service

3 things look different from your system's normal behavior:

1. 📊 API surface grew fast — 12 → 18 endpoints in 2 weeks (2.3x usual rate)
2. 🧪 Tests struggling — failure rate 3% → 11% (14 of 127 failing)
3. 📦 Dependencies expanded — +7 packages in one snapshot

🔍 This matches a known pattern seen 47 times:
"API expanding faster than test infrastructure"
Usually stabilizes in 2-4 weeks.

📎 Evidence: 4 commits, 2 new files, 3 failing tests, 3 new deps
[Export evidence for AI investigation →]
```

### 6.1 Platform Formatting Rules

- **Discord/Telegram:** No markdown tables; use bullet lists
- **Slack:** Blocks API for rich formatting
- **Email:** HTML with inline styles
- **All:** Wrap URLs in `<>` to suppress previews where applicable

---

## 7. Reporting Frequency

Phase 5 advisories are generated:
- **On demand** — user requests a report
- **On significant change** — when a signal exceeds the significance threshold
- **Periodic digest** — daily or weekly summary of accumulated changes

The system MUST NOT spam users. A "nothing notable" period produces no advisory (or a brief "all clear" digest if configured).

---

## 8. Levels of AI Integration (Progressive)

| Level | Feature | Status |
|-------|---------|--------|
| **1** | Evidence Package Export | Planned (Phase 5 launch) |
| **2** | Pre‑Built Investigation Prompt | Planned (Phase 5 launch) |
| **3** | Integrated AI Investigation (API call) | Future |
| **4** | Auto‑Fix Proposals | Future (requires careful scoping) |

Levels 1 and 2 ship with Phase 5. Levels 3 and 4 are future enhancements that do not affect the contract.

---

## 9. Definition of Done

Phase 5 design is considered complete when:
- Advisory report shape is defined
- Evidence package shape is defined
- Human summary format is specified
- Chat format is specified
- Investigation prompt template exists
- Reporting frequency rules are documented
- AI integration levels are scoped

Implementation may begin only after this point.

---

> **Summary:**
> Phase 5 shows what changed, how it compares to normal, and whether the system
> has seen this before — with enough evidence to act, not just worry.
