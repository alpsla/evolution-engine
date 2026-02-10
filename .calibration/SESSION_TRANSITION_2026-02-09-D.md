# Session Transition — 2026-02-09-D (Market Research + Integrations + AI Agent Loop)

## What Was Done

### 1. Market Research Report
Comprehensive market research compiled from two parallel research agents into a single document.

**File:** `.calibration/MARKET_RESEARCH_2026-02-09.md` (12 sections)

Key findings:
- **Market size:** $10B AI code tools (27.57% CAGR), DevOps $16-18B (21% CAGR)
- **Gartner** formalized "Developer Productivity Insight Platforms" as a market category
- **DX acquired by Atlassian for $1B** (raised only $1.35M) — validates the space
- **84%** of devs use AI tools, only **29%** trust output accuracy
- **45%** of AI code has OWASP vulnerabilities, incidents per PR up **23.5%**
- **EU AI Act** full enforcement August 2026 — traceability/monitoring mandated
- **PLG dominates:** Cursor hit $200M ARR with zero sales reps
- **EE's unique gap:** No tool does longitudinal cross-signal process monitoring

Strategic insight (from user): Qodo/CodeRabbit/Snyk are NOT competitors — they're **data sources**. Their output becomes signal families in EE's pipeline via adapters.

### 2. Integrations Documentation
New marketing/product doc that ships with the app.

**File:** `docs/INTEGRATIONS.md`

Contents:
- **Value ladder** (5 levels): Git only → +deps → +CI → +deployments → full stack with adapters
- **Pattern multiplier math:** `combinations = families × (families-1) / 2`
- **Source prescan design:** 3-layer detection (config files, SDK fingerprints in lockfiles, import statements)
- **`evo sources`** — shows connected + detected (soft hints, not pushes)
- **`evo adapter list`** — full catalog with detection status
- **`evo sources --what-if`** — estimates cross-family impact before installing
- **AI Agent Integration** — the detect → investigate → fix → validate loop
- **`evo investigate`** — AI reads advisory, produces root cause report
- **`evo fix`** — AI applies fixes, EE validates, **iterates until advisory clears**
- **GitHub Action** workflow with PR comments + investigation + validation loop
- **FAQ** covering: "Do I replace my tools?" (no), "Which AI agents work?" (any), "Does code leave my machine?" (no)

Key user direction: "Try and compare" framing — soft sell, never push adapters. Let data speak.

### 3. SDK Fingerprint Database
**File:** `evolution/data/sdk_fingerprints.json`

Maps **20 services** across **8 families** to their SDK package names, config files, and import patterns:
- Monitoring: Datadog, New Relic, Grafana, Prometheus, OpenTelemetry, Elastic APM, Azure Monitor
- Error tracking: Sentry
- Incidents: PagerDuty, OpsGenie, Statuspage
- Security: Snyk, Semgrep
- Quality: SonarQube, Codecov
- Code review: Qodo, CodeRabbit
- Work items: Jira, Linear
- Feature flags: LaunchDarkly, Unleash

Detection works because these tools require SDK packages in lockfiles (e.g., `dd-trace` → Datadog, `@sentry/node` → Sentry). We already parse lockfiles in Phase 1 — fingerprint scan is essentially free.

### 4. Implementation Plan Updated
**File:** `docs/IMPLEMENTATION_PLAN.md`

New sections added:
- **§8.11 Source Prescan** — SDK fingerprint detection (5 subtasks)
- **§8.12 AI Agent Integration** — detect → investigate → fix → validate loop (8 subtasks)

Removed from non-goals: "Automated code fixes" (now a planned feature via AI agent loop)

Updated priority order (22 total tasks, 14 completed):

| Priority | What | Key Tasks |
|----------|------|-----------|
| **P1** | Source Prescan | `SourcePrescan` class, `evo sources`, `--what-if`, hints in `evo analyze` |
| **P2** | AI Agent Loop | `evo investigate`, `evo fix`, verify loop (iterate until EE confirms all clear), agent abstraction |
| **P3** | GitHub Action | PR comments, investigate, suggest fixes, validate loop on every push |
| **P4** | Enrichment | More universal patterns (GITHUB_TOKEN), Cython, cloud KB sync |

### 5. AI Agent Loop Design (RALF-style)
User directed that the fix loop must iterate until EE confirms everything is back to normal:

```
1. evo analyze .       → EE detects anomalies
2. evo investigate .   → AI reads advisory, finds root causes
3. evo fix .           → AI applies fixes on branch
4. evo verify .        → EE re-analyzes
       │
   ┌───┴────────┐
   ALL CLEAR    RESIDUAL → feed remaining findings back to AI → step 2
```

Termination conditions:
- All advisory items resolved (ideal)
- Max iterations reached (default 3)
- No progress (same advisory after fix → stop)

EE validates its own AI — prevents the fixer from introducing new drift.

## Files Changed/Created

| File | Change |
|------|--------|
| `.calibration/MARKET_RESEARCH_2026-02-09.md` | **NEW** — comprehensive market research (12 sections) |
| `docs/INTEGRATIONS.md` | **NEW** — integrations doc, value ladder, AI agent loop, FAQ |
| `evolution/data/sdk_fingerprints.json` | **NEW** — 20 services × 8 families fingerprint DB |
| `docs/IMPLEMENTATION_PLAN.md` | Added §8.11 (prescan), §8.12 (AI agent), updated priorities |

## What JSON Structures Changed?
**None.** All changes are documentation, design, and a data file. No code changes.

## Key User Decisions This Session

1. **Qodo/CodeRabbit/Snyk are data sources, not partners** — their output feeds into EE as signal families via adapters. EE is the aggregation layer above all tools.
2. **Soft sell approach** — hint at what adapters could add, never push. "Try and compare."
3. **SDK fingerprint prescan** — detect tools from lockfiles/configs/imports (user pointed out all monitoring tools have trackers in the code)
4. **AI agent fix loop must iterate** — not one-shot, keeps going until EE confirms all clear (RALF-style)
5. **EE validates AI fixes** — the validation step prevents AI from introducing new problems

## Architecture State
- 276 tests passing, 0.85s
- 19 universal patterns from 25 repos
- All display text PM-friendly (Phase 3.1 LLM retired)
- No code changes this session — all design/docs/data

## Next Tasks (Priority Order)

1. **P1: Source Prescan** — implement `evolution/prescan.py`, wire into CLI
2. **P2: `evo investigate`** — agent abstraction, feed advisory to AI, investigation report
3. **P2: `evo fix` + validate loop** — AI fixes on branch, EE verifies, iterate
4. **P3: GitHub Action** — `evolution-engine/analyze@v1` with full loop
5. **P4: Enrich patterns** — re-run calibration with GITHUB_TOKEN for CI/deploy data
6. **P4: Cython compilation** — IP protection for phase engines
7. **P4: Cloud KB sync** — opt-in anonymous pattern sharing

## Context for Next Session
- Product goal: monitor AI code generation, detect drift/hallucinations/goal misalignment
- The app is positioned as the **aggregation layer** above existing dev tools
- All existing tools (Datadog, Qodo, Snyk, etc.) are potential data sources, not competitors
- The engagement flow: `evo analyze → investigate → fix → verify → repeat until clear`
- Two audiences: PM-friendly reports (humans), technical investigation prompts (AI agents)
- Local-first, code never leaves the machine
- 276 tests, all passing, 0.85s runtime
- LLM cost: ~$0.01/repo (Phase 4b only)
