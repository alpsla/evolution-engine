# Evolution Engine — Integrations & Data Sources

## How It Works

Evolution Engine monitors your development process by analyzing **signals** from multiple sources and detecting **cross-family patterns** that no single tool can see.

Every tool your team already uses — CI pipelines, code review, security scanners, dependency managers — produces data that Evolution Engine can ingest as a signal family. **The more sources connected, the richer the pattern detection.**

```
Your existing tools          Evolution Engine              What you get
─────────────────           ─────────────────             ──────────────
Git history          ──→    ┌─────────────────┐
CI/CD (Actions)      ──→    │  Signal Engine   │──→  Cross-family patterns
Code review (Qodo)   ──→    │  (Phase 2)       │──→  Risk advisories
Security (Snyk)      ──→    │                  │──→  Drift detection
Dependencies (npm)   ──→    │  Pattern Engine  │──→  Trend reports
Deployments          ──→    │  (Phase 4)       │──→  Investigation prompts
Quality gates        ──→    └─────────────────┘
```

## Standalone vs. Connected

Evolution Engine delivers value at every level. Each additional data source unlocks new pattern families.

### Level 1 — Git Only (Free, Zero Config)

**What you need:** A git repository. That's it.

**What you get:**
- Commit-level signals: files touched, file dispersion, change locality, co-change novelty
- Baseline comparison: "This commit touched 12 files — about 3x more than usual"
- Risk advisories for unusually large, scattered, or novel changes
- Single-family trend detection over time

**Who it's for:** Any developer who wants to understand if AI-generated commits are drifting from project norms.

```bash
evo analyze .
```

---

### Level 2 — Git + Dependencies (Free)

**What you need:** A supported lockfile (package-lock.json, go.sum, Cargo.lock, Gemfile.lock).

**What you get:** Everything in Level 1, plus:
- Dependency count and depth tracking
- **Cross-family pattern**: "Commits that change dependencies tend to touch 40% more spread-out files" (seen in 5/25 calibrated repos)
- Supply chain drift detection: unusual dependency churn flagged automatically

**Example pattern discovered:**
> Dependency-changing commits have higher file dispersion (Cohen's d = 0.40 across 5 projects). This suggests dependency updates tend to be cross-cutting changes that touch unrelated parts of the codebase.

---

### Level 3 — Git + CI Pipeline (Pro)

**What you need:** GitHub Actions, GitLab CI, or a supported CI provider.

**What you get:** Everything in Level 2, plus:
- Build duration and failure rate tracking
- **Cross-family patterns**:
  - "CI-triggering commits touch more files than average" (4 repos)
  - "CI-triggering commits are more dispersed across the codebase" (4 repos)
  - "CI-triggering commits change less-related files" (3 repos)
- Correlation between code change size and build time trends

**Example insight:**
> Your last 10 commits averaged 45s CI duration. This commit took 180s — about 4x longer than usual. CI-triggering commits with high file dispersion tend to have longer build times. [Medium Risk]

---

### Level 4 — Git + CI + Deployments (Pro)

**What you need:** GitHub Releases, or a deployment tracking system.

**What you get:** Everything in Level 3, plus:
- Release cadence, pre-release tracking, asset count monitoring
- **Cross-family patterns**:
  - "Release commits have very high file dispersion" (5 repos, d = 1.54)
  - "Faster-than-usual releases correlate with dependency changes" (3 repos)
- Deployment velocity drift: detect when release pace is accelerating or decelerating unusually

---

### Level 5 — Full Stack (Pro + Adapters)

**What you need:** Any combination of the tools below, connected via adapters.

**What you get:** Everything above, plus patterns across **every connected source**. The more families, the more cross-family correlations become visible.

| Adapter | Signal Family | Example Metrics | Example Cross-Pattern |
|---------|--------------|-----------------|----------------------|
| **Qodo / CodeRabbit** | `code_review` | Findings count, hallucination flags, suggestion acceptance rate | "PRs with high hallucination flags also have 3x higher file dispersion" |
| **Snyk / Semgrep** | `security_scan` | Vulnerability count, critical count, fixable ratio | "Dependency-heavy commits introduce 2x more fixable vulnerabilities" |
| **SonarQube** | `quality_gate` | Code smells, duplications, coverage delta | "Commits with low change locality have 40% more code smells" |
| **Datadog / PagerDuty** | `incidents` | Incident count, MTTR, severity | "Deployments with high dispersion correlate with more P1 incidents" |
| **Jira / Linear** | `work_items` | Story points, cycle time, rework rate | "Large commits linked to rework items have higher co-change novelty" |
| **Custom** | Any | User-defined | Patterns discovered automatically |

---

## The Value Equation

```
Pattern discovery power = (number of signal families)²
```

With 2 families (git + dependency), you get 1 possible cross-family combination.
With 5 families, you get 10. With 8 families, you get 28.

Each new adapter doesn't add linearly — it multiplies the pattern space.

| Connected Sources | Families | Cross-Family Combinations | Typical Patterns Found |
|-------------------|----------|--------------------------|----------------------|
| Git only | 1 | 0 | Single-family trends only |
| Git + deps | 2 | 1 | 1-3 patterns |
| Git + deps + CI | 3 | 3 | 3-8 patterns |
| Git + deps + CI + deploy | 4 | 6 | 6-15 patterns |
| Full stack (6+ families) | 6+ | 15+ | 15-40+ patterns |

## Compare Your Setup

### What's connected now

Run `evo sources` to see what's currently active and what could be added:

```bash
evo sources
```

Output:
```
CONNECTED (active signal families):
  ✅ Git history          874 commits, 4 metrics
  ✅ Dependencies         package-lock.json (npm), 2 metrics

DETECTED (found in your repo — not yet connected):
  🔍 CI pipeline         .github/workflows/ found — set GITHUB_TOKEN to connect
  🔍 Deployments         GitHub Releases available — set GITHUB_TOKEN to connect
  🔍 Security            .snyk config found — install: pip install evo-adapter-snyk
  🔍 Monitoring          'dd-trace' found in package.json — install: pip install evo-adapter-datadog
  🔍 Error tracking      '@sentry/node' found in package.json — install: pip install evo-adapter-sentry
  🔍 Code quality        sonar-project.properties found — install: pip install evo-adapter-sonarqube

Current: 2 families → 1 cross-family combination
With all detected: 8 families → 28 combinations (28x more patterns)
```

### How detection works

Evolution Engine scans three layers to find tools your team already uses:

**1. Config files** — CI configs, tool property files, YAML configs
```
.github/workflows/     → GitHub Actions
.gitlab-ci.yml         → GitLab CI
Jenkinsfile            → Jenkins
sonar-project.properties → SonarQube
.snyk                  → Snyk
codecov.yml            → Codecov
.sentryclirc           → Sentry
datadog.yaml           → Datadog
newrelic.yml           → New Relic
```

**2. SDK fingerprints in dependencies** — your lockfiles already list the SDKs
```
dd-trace, ddtrace, datadog        → Datadog
newrelic, @newrelic/*              → New Relic
@sentry/node, sentry-sdk          → Sentry
@pagerduty/pdjs                   → PagerDuty
@datadog/browser-rum              → Datadog RUM
applicationinsights               → Azure Monitor
@opentelemetry/*                  → OpenTelemetry (multiple backends)
sonarqube-scanner                 → SonarQube
@codecov/webpack-plugin            → Codecov
@qodana/*                         → Qodana (JetBrains)
```

**3. Import statements** — for projects without lockfiles or with vendored deps
```python
import datadog                    → Datadog
import newrelic.agent             → New Relic
import sentry_sdk                 → Sentry
from opentelemetry import trace   → OpenTelemetry
```

This prescan runs automatically during `evo analyze` and takes < 1 second. It reads only filenames and dependency lists — never executes code or sends data anywhere.

### Full adapter catalog

Browse everything available, including tools not detected in your repo:

```bash
evo adapter list
```

Output:
```
AVAILABLE ADAPTERS                                   STATUS
──────────────────────────────────────────────────────────────

Source Control
  git (built-in)                                     ✅ Connected

Dependencies
  npm, go, cargo, bundler (built-in)                 ✅ Connected

CI / Build
  github-actions (built-in)                          🔍 Detected
  gitlab-ci (built-in)                               —
  jenkins (community: evo-adapter-jenkins)           —
  circleci (community: evo-adapter-circleci)         —

Deployments
  github-releases (built-in)                         🔍 Detected
  argocd (community: evo-adapter-argocd)             —

Code Review
  qodo (community: evo-adapter-qodo)                 —
  coderabbit (community: evo-adapter-coderabbit)     —
  sonarqube (community: evo-adapter-sonarqube)       —

Security Scanning
  snyk (community: evo-adapter-snyk)                 🔍 Detected
  semgrep (community: evo-adapter-semgrep)           —
  dependabot (built-in)                              —

Monitoring / Incidents
  datadog (community: evo-adapter-datadog)           —
  newrelic (community: evo-adapter-newrelic)          —
  pagerduty (community: evo-adapter-pagerduty)       —
  grafana (community: evo-adapter-grafana)           —

Project Tracking
  jira (community: evo-adapter-jira)                 —
  linear (community: evo-adapter-linear)             —

Quality Gates
  codecov (community: evo-adapter-codecov)           —
  coveralls (community: evo-adapter-coveralls)       —

Custom
  Build your own: evo adapter init my-adapter
  Validate: evo adapter validate ./my-adapter

Install any community adapter:
  pip install evo-adapter-datadog

Full catalog & guides: https://evolution-engine.dev/adapters
```

### Curious what more sources would add?

This is entirely optional. Evolution Engine works standalone with just git. But if you're curious whether your existing tools would add useful signal, you can check:

```bash
evo sources --what-if datadog pagerduty
```

Output:
```
Current:   2 families → 1 cross-family combination
With proposed additions: 4 families → 6 cross-family combinations

New questions EE could answer:
  ? git × incidents      "Do scattered commits correlate with more incidents?"
  ? git × monitoring     "Do large changes affect error rates or latency?"
  ? deps × incidents     "Do dependency updates correlate with incident spikes?"
  ? deps × monitoring    "Do dependency changes affect service performance?"
  ? incidents × monitoring  "Do monitoring anomalies precede incidents?"

Try it and compare — you can always disconnect adapters later.
```

You can also compare reports side by side — run once without adapters, once with — and see if the additional patterns are worth it for your team. EE doesn't push you to connect anything. The data speaks for itself.

## Building Custom Adapters

Any tool that produces structured data can become a signal family. Evolution Engine's plugin system auto-discovers adapters installed as Python packages.

```bash
# Scaffold, validate, security-check, publish
evo adapter new jenkins --family ci
evo adapter validate evo_jenkins.JenkinsAdapter --security
evo adapter security-check evo_jenkins
```

Adapters pass 13 structural checks + security scanning before certification.

For the full guide — scaffolding, development, contract reference, testing, publishing, trust tiers, and governance — see **[docs/adapters/](../adapters/README.md)**.

## AI Agent Integration — Closing the Loop

Evolution Engine detects problems. AI coding agents fix them.

The advisory report includes a machine-readable **investigation prompt** — a technical brief designed specifically for AI assistants (Claude Code, Cursor, Copilot, etc.) to pick up and act on.

### The feedback loop

```
  Developer writes code (possibly AI-assisted)
        │
        ▼
  ┌─────────────────────┐
  │  1. evo analyze .   │  ← EE detects anomalies, drift, patterns
  │     (Phase 1→5)     │
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  2. Advisory Report │  ← PM-friendly risk summary
  │  + Investigation    │  ← Technical prompt for AI agents
  │    Prompt           │
  └────────┬────────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
  Human         AI Agent
  reviews       investigates
  the risk      the root cause
  summary       and proposes fix
                    │
                    ▼
              3. Pull Request
                 with fix
                    │
                    ▼
              4. evo verify    ← EE validates: did the fix resolve the advisory?
                    │
              ┌─────┴──────┐
              ▼            ▼
           PASS          FAIL
           Advisory      Residual issues
           cleared →     still flagged →
           merge PR      back to step 2
```

### How it works today

After running `evo analyze`, the advisory includes an investigation prompt:

```bash
evo analyze . --output json | jq '.investigation_prompt'
```

This prompt contains:
- Specific metrics that deviated, with exact values and baselines
- Cross-family patterns detected (e.g., "dependency changes correlate with high dispersion")
- The commit SHAs and file paths involved
- Technical context an AI agent needs to investigate the root cause

You can feed this directly into your AI coding tool:

```bash
# Pipe into Claude Code
evo investigate .

# Or manually: copy the investigation prompt into Cursor / Copilot chat
evo analyze . --show-prompt
```

### `evo investigate` — automated AI investigation

The `evo investigate` command feeds the advisory into an AI agent and produces a structured investigation report:

```bash
evo investigate .
```

Output:
```
Evolution Engine — Investigation Report

Advisory: 6 unusual changes detected [2 High, 3 Medium, 1 Low]

1. [High] Files Changed: 47 files — about 12x more than usual
   Investigation: This commit refactors the authentication module
   across 6 packages. The high file count is expected for this type
   of cross-cutting change. However, 8 of the touched files are
   test fixtures that appear to be copied rather than shared.
   → Suggestion: Extract shared test fixtures to a common package.

2. [High] CI Duration: 340s — about 4x longer than usual
   Investigation: The duration spike correlates with 12 new
   integration tests added in this commit. Each test spins up a
   database container.
   → Suggestion: Use a shared test database fixture to reduce
     container startup overhead.

3. [Medium] Dependency Depth: 8 — about 2x deeper than usual
   Investigation: Adding 'passport-oauth2' introduced a deep
   transitive chain via 'node-fetch' → 'whatwg-url' → 'tr46'.
   → Suggestion: Consider 'undici' (built into Node 18+) as an
     alternative with zero transitive dependencies.

Patterns matched:
  ✦ dep-changing commits have higher dispersion (seen in 5 projects)
    This commit matches: dependency depth increased AND file
    dispersion is 4x above normal.

Verification: Re-run 'evo analyze .' after applying fixes to confirm
the advisory clears.
```

### `evo fix` — AI agent applies the fixes (experimental)

For teams that want full automation, `evo fix` takes the investigation one step further — the AI agent creates a branch, applies the suggested fixes, and opens a PR:

```bash
evo fix . --dry-run         # Preview what would change
evo fix .                   # Create branch, fix, validate — iterate until clear
evo fix . --max-iterations 5  # Allow more fix attempts (default: 3)
```

This is opt-in and experimental. The cycle runs automatically:

```
Iteration 1:
  1. AI reads EE advisory + investigation prompt
  2. AI proposes targeted fixes (minimal changes, not rewrites)
  3. AI applies fixes on a branch
  4. EE re-analyzes the branch (evo verify)
  5. Result: 4 of 6 issues resolved, 2 remaining

Iteration 2:
  1. AI reads RESIDUAL advisory (only the 2 remaining items)
  2. AI proposes fixes for remaining items (knows what was already tried)
  3. AI applies fixes
  4. EE re-analyzes
  5. Result: all clear ✅ → PR ready for human review
```

The loop terminates when:
- **All advisory items resolved** — ideal outcome, PR ready for review
- **Max iterations reached** (default 3) — human reviews remaining items
- **No progress** — same advisory after fix attempt, stops to avoid infinite loop

The validation step is critical — EE acts as the quality gate on the AI's own work. If the AI introduces a new problem while fixing an old one, EE catches it in the next iteration.

### GitHub Action — continuous monitoring + auto-fix

```yaml
# .github/workflows/evo-monitor.yml
name: Evolution Engine
on: [pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: evolution-engine/analyze@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          # Comment risk summary on PR
          comment: true
          # Optional: run AI investigation on High/Critical findings
          investigate: true
          # Optional: auto-suggest fixes as review comments
          suggest-fixes: true
```

This creates a continuous feedback loop:
1. Developer pushes code (human or AI-generated)
2. EE analyzes the PR against project baselines
3. Risk summary posted as PR comment
4. If high-risk findings: AI agent investigates and suggests fixes inline
5. Developer (or AI agent) addresses the findings
6. **EE re-runs on the next push and validates** — compares current advisory to previous
7. PR comment updated: "3 of 6 issues resolved, 2 improving, 1 new regression"
8. Loop continues until advisory clears or team accepts the residual risk

### Using EE reports with external AI tools

The advisory JSON is designed to be portable. You can feed it into any AI tool:

```bash
# Feed into Claude Code
evo analyze . --output json > advisory.json
claude "Review this advisory and investigate the high-risk items" < advisory.json

# Feed into Cursor
evo analyze . --show-prompt | pbcopy
# Paste into Cursor chat

# Feed into a custom script
evo analyze . --output json | python my_auto_fixer.py
```

The investigation prompt uses technical language (commit SHAs, metric names, deviation values) because it's meant for machines, not humans. The PM-friendly report is a separate output for human consumption.

### The complete picture

```
                        ┌──────────────────────────────┐
                        │    Your Development Process   │
                        └──────────────┬───────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
              Git commits       CI builds          Deployments
              Dependencies      Code reviews       Monitoring
              Security scans    Quality gates      Incidents
                    │                  │                  │
                    └──────────────────┼──────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │      Evolution Engine        │
                        │  Signals → Patterns → Advisory│
                        └──────────────┬───────────────┘
                                       │
                         ┌─────────────┼─────────────┐
                         ▼             ▼             ▼
                    PM Report    AI Investigation   Trend
                    (humans)     (AI agents fix)    Dashboard
```

EE is the **eyes**. Your AI coding agent is the **hands**. Together they form a self-correcting loop: detect drift, investigate causes, fix issues, verify resolution.

---

## FAQ

**Q: Do I need to replace my existing tools?**
No. Evolution Engine sits alongside your tools, not instead of them. Your CI still runs, your code review still happens, your security scanner still scans. EE ingests their output as signals and finds patterns across all of them.

**Q: What if I only have git?**
That's enough to start. Git-only analysis detects commit-level anomalies: unusually large changes, scattered modifications, novel file combinations. Many teams start here and add sources over time.

**Q: Does my code leave my machine?**
No. Evolution Engine runs locally by default. Code, events, and signals stay on your machine. The only optional network calls are for API-based adapters (e.g., fetching CI run data from GitHub) and the opt-in community knowledge base.

**Q: How is this different from Qodo / CodeRabbit / Snyk?**
Those tools analyze individual PRs or scans at a point in time. Evolution Engine analyzes the **process over time** — detecting gradual drift, cross-family correlations, and patterns that only emerge across hundreds of commits. Their output can feed into EE as additional signal families, making both more valuable.

**Q: What's the cost of adding more sources?**
Tier 1 sources (file-based: git, dependencies, config) are free and require no API calls. Tier 2 sources (API-based: CI, deployments, security) are included in the Pro license. Tier 3 sources (custom adapters) work with any license.

**Q: Can the AI agent introduce new problems while fixing old ones?**
That's exactly why `evo fix` re-runs the analysis after applying changes. If the fix introduces a new anomaly (e.g., fixing CI duration but spiking file dispersion), EE catches it before the PR merges. The feedback loop is self-correcting.

**Q: Which AI agents work with `evo investigate`?**
Any AI coding tool that accepts text prompts: Claude Code, Cursor, GitHub Copilot, Cody, Windsurf, or your own scripts. The investigation prompt is plain text with structured context — no vendor lock-in.

**Q: Do I need an AI agent to use EE?**
No. EE works without any AI agent. The advisory report is useful on its own for human review. The AI agent integration is an optional layer that automates the investigation and fix cycle.
