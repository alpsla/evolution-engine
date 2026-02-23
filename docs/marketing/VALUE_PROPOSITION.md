# Evolution Engine — Value Proposition

> **The drift detector for AI-assisted development.**
> AI coding tools write correct code that's architecturally wrong.
> Evolution Engine catches the drift, shows the evidence, and closes the loop.

---

## The Problem: AI Tools Don't Know Your Baseline

AI coding assistants — Cursor, Copilot, Claude Code, Codex — are generating more code than ever. They write syntactically correct, test-passing code that silently drifts from your project's architectural norms. They don't know that your team never touches more than 3 directories in a single commit, or that your dependency tree was intentionally kept shallow, or that your release cadence was weekly for a reason.

The result: code that looks fine in isolation but compounds into structural debt that surfaces weeks later as build instability, cascading dependency upgrades, or production incidents nobody can trace back to a root cause.

**No existing tool catches this.** Linters check syntax. Security scanners check CVEs. CI checks tests. But nobody is watching whether the *pattern of development* has shifted — and whether that shift was intentional.

Evolution Engine is that missing layer.

---

## What Evolution Engine Does

EE observes your development process — not your code — and learns what is structurally normal for **your specific project**. When something deviates from that learned baseline, it tells you what changed, when the drift started, which commit introduced it, and whether it matches a known risk pattern calibrated across 90+ open-source repositories.

Then it does something no other tool does: it closes the loop.

### The Full Loop

```
evo analyze .       Detect drift across 7 signal families
        |
evo investigate .   AI traces root cause to the exact commit
        |
evo fix .           AI generates a course-correction (not a patch — a realignment)
        |
evo verify .        Re-analyze to confirm the drift resolved
        |
evo accept . 1 2    Human accepts findings or escalates
```

**Detect drift. Show evidence + exact commit. AI fixes it. Verify fix worked. Human accepts or escalates.** No other tool offers this complete loop.

This is not classical code review. The advisory is a drift alarm, not a bug report. Investigation means "when did the AI go off track?" not "what's broken?" Fixing means course-correcting — finding the breakpoint commit, assessing whether drift was intentional, and guiding the AI back on track.

---

## The Evidence Behind It

EE's pattern library is not hand-curated opinions. It is statistically validated from real-world calibration:

| Metric | Value |
|--------|-------|
| Repositories calibrated | 90+ open-source repos |
| SDLC signals analyzed | 6.18 million |
| Commits processed | 2.1 million |
| Validated cross-signal patterns | 44 |
| False positive rate | 1.6% |
| Signal families | 7 (Git, CI, Deployment, Dependency, Testing, Coverage, Error Tracking) |

Each pattern represents a statistically significant correlation between events across different signal families — for example, "when a CI failure coincides with a spike in code dispersion, build instability follows in 7 out of 12 repos where this pattern appeared."

### The 5-Phase Pipeline

```
Phase 1: Event Recording     What happened (commits, builds, releases, deps, tests, errors)
Phase 2: Signal Detection     What's unusual (statistical deviation from YOUR baseline)
Phase 3: Explanation          What it means (evidence-backed, PM-readable)
Phase 4: Pattern Matching     Has this been seen before (44 patterns from 90+ repos)
Phase 5: Advisory             What to do (prioritized by severity, with evidence)
```

Deviation detection uses MAD/IQR-based modified z-scores against your repository's own history — not arbitrary thresholds, not global averages. A 500-file commit is normal for a monorepo refactor but alarming for a microservice. EE knows the difference because the baseline is yours.

---

## Seven Signal Families

| Family | What It Watches | Example Metrics |
|--------|----------------|-----------------|
| **Git** | Commit structure, file dispersion, change locality | `files_touched`, `dispersion`, `change_locality`, `cochange_novelty_ratio` |
| **CI** | Build duration, pass/fail patterns | `run_duration`, `run_failed` |
| **Deployment** | Release cadence, prerelease flags | `release_cadence_hours`, `is_prerelease`, `asset_count` |
| **Dependency** | Dependency count, tree depth (10+ ecosystems) | `dependency_count`, `max_depth` |
| **Testing** | Test counts, failure and skip rates | `total_tests`, `failure_rate`, `skip_rate`, `suite_duration` |
| **Coverage** | Line and branch coverage trends | `line_rate`, `branch_rate` |
| **Error Tracking** | Error volume, affected users, unhandled errors | `event_count`, `user_count`, `is_unhandled` |

Dependency tracking supports npm, pnpm, Go, Cargo, Bundler, pip, Composer, Gradle, Maven, Swift, and CMake out of the box.

---

## Why This Matters Now

AI coding tools are changing how software gets built. The volume of generated code is increasing, but the feedback loops haven't kept up. The core problem:

**AI agents write code without baseline awareness.** They don't know what's normal for your project. They optimize locally — correct function, passing test — while drifting globally from your project's structural norms.

This creates a new category of risk:

- **Correct but scattered**: AI touches 12 files across 6 directories for a change that should be localized to 2 files. CI passes. Tests pass. But the dispersion signature matches a pattern that preceded build instability in similar repos.
- **Correct but deep**: AI adds a dependency that works perfectly but doubles your dependency tree depth. No CVEs, no build failures — but the structural profile shifted.
- **Correct but fast**: AI accelerates your release cadence from weekly to daily. Each release passes checks. But change locality has been declining for 3 weeks — a pattern that historically precedes quality regression.

EE provides the missing feedback loop: tell the developer (or the AI agent) that the *pattern* of development has shifted, show when it started, and provide evidence so they can decide whether the drift was intentional.

For teams adopting AI tools, this is the difference between "we're shipping faster" and "we're shipping faster and we can prove quality isn't degrading."

---

## Three Integration Paths

EE meets you where you are. Start free, automate when you trust it.

### Path 1: CLI Explorer (Free)

```bash
pip install evolution-engine
evo analyze .            # Full 5-phase pipeline
evo report . --open      # Interactive HTML report
evo sources .            # See what data EE can access
evo history .            # Track changes over time
```

Start here. See what EE catches. Explore findings, tune with `evo accept` for intentional changes, build confidence. No account needed. No data leaves your machine.

### Path 2: Git Hooks (Pro)

```bash
evo hooks install .      # One-time setup
# EE runs silently after every commit
# Notifies only when findings exceed your threshold
```

Once you trust EE's judgment, automate it. The hook runs analysis in the background after every commit. Silent when all clear — notifies only when it matters. You control the threshold.

### Path 3: GitHub Action / GitLab CI (Pro)

```yaml
# GitHub Action
- uses: alpsla/evolution-engine@v1
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    investigate: true
    suggest-fixes: true
```

```yaml
# GitLab CI
evo-analyze:
  stage: test
  script:
    - evo analyze . --ci gitlab
    - evo investigate .
```

For teams: every PR/MR gets automatic analysis, AI investigation, inline fix suggestions on changed lines, and verification when the developer pushes a fix. The comment updates itself as findings get resolved.

### The Natural Progression

```
Day 1:   evo analyze .            "I see what it catches."            (Free)
Week 1:  evo analyze . --verify   "The critical findings are real."  (Free)
Week 2:  evo hooks install .      "Just tell me when it matters."   (Pro)
Week 3:  evo init --github-action "Watch my team's PRs too."        (Pro)
```

---

## Free vs. Pro

### Free Tier — CLI Only

Full pipeline, no restrictions on analysis depth. No account required. No data leaves your machine.

- Git history analysis (full walker, all metrics)
- Dependency tracking (10+ package ecosystems)
- Statistical deviation detection (MAD/IQR baselines)
- Pattern matching (44 validated patterns)
- Local knowledge base
- Interactive HTML reports
- Run history and trend comparison
- Source detection and `--what-if` planning

### Pro — $19/dev/month

Everything in Free, plus the full loop and team integration:

- Git hooks — local automation (`evo hooks install`, `evo watch`)
- GitHub Action + GitLab CI integration
- AI investigation — root cause analysis to exact commit (`evo investigate`)
- AI fix loop — iterative course-correction (`evo fix`)
- Inline PR/MR fix suggestions on changed lines
- CI, Deployment, and Error Tracking adapters
- Community pattern sync
- Priority support

### Founding Member — $9.50/month for 3 months

Full Pro access in exchange for monthly feedback on what's working and what's not. 50 spots. Code: **FOUNDING50**.

---

## Who This Is For

### Individual developers using AI coding tools

You're shipping faster with Cursor or Copilot but you have no way to know if the AI is drifting from your project's norms. EE gives you a quantified answer: "This commit's structural profile matches / doesn't match your project's baseline." Confidence, not gut feeling.

### Engineering leads and PMs

You need to answer "is quality holding up?" with data, not anecdotes. EE provides per-repo baselines with deviation tracking over time. When dispersion spikes or dependency depth creeps up, you see it in the trend — with the exact commits that caused it — before it becomes a production incident.

### Teams adopting AI tools at scale

You want the velocity gains of AI-assisted development without the hidden structural debt. EE is the feedback loop that lets you measure whether AI-generated code is maintaining architectural coherence across the team.

---

## Competitive Positioning

**EE is not competing with your existing tools. It makes them more valuable.**

| Tool Category | Examples | What They Do | What EE Adds |
|--------------|----------|-------------|-------------|
| Security scanners | Snyk, Dependabot | Find CVEs in dependencies | Correlate dependency changes with CI failures and deployment patterns |
| Static analysis | SonarQube, CodeClimate | Code quality metrics | Per-repo baselines, cross-signal patterns, historical trend detection |
| Monitoring | Datadog, New Relic, Sentry | Production observability | Pre-production drift detection, development process patterns |
| AI coding tools | Cursor, Copilot, Codex | Code generation | Baseline awareness feedback loop — tell the AI when it's drifting |
| Dev metrics | LinearB, Sleuth | DORA metrics | Per-repo statistical deviation, pattern memory, actionable advisories |

EE is the **aggregation layer** that sits above your existing toolchain. It cross-correlates signals that no single tool can see. Every tool you add to your stack becomes a new signal family for EE — adding more tools makes EE smarter, not redundant.

---

## Core Design Principles

**Local-first, privacy by design.** Your code never leaves your machine. Analysis runs locally. No accounts, no cloud uploads, no telemetry. The only data that can optionally leave your machine is anonymized pattern fingerprints (e.g., "ci event correlates with high dispersion") — never code, filenames, or project details.

**Deterministic analysis.** The pipeline uses payload timestamps, not wall clock time. Events are sorted chronologically. Same input, same output. Every time.

**Evidence over opinion.** Every advisory includes the specific commits, the deviation magnitude, the pattern match confidence, and the historical precedent. No black boxes, no unexplained scores.

**Aggregation, not competition.** EE treats every other tool as a data source. The value proposition strengthens with every tool in your stack.

---

## The Bottom Line

AI coding tools are generating more code than ever. They write correct code that's architecturally wrong — they don't have baseline awareness.

Evolution Engine provides the missing feedback loop:

> **Detect the drift. Show the evidence. Fix the course. Verify it worked. Human decides.**

Five commands. Seven signal families. Forty-four validated patterns from 90+ repos. 1.6% false positive rate. Local-first. Privacy by design.

The question isn't whether AI-assisted development introduces structural drift — it does. The question is whether you're detecting it before it compounds.

---

*Last updated: 2026-02-22*
