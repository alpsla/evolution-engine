# Quickstart

## Install

```bash
pip install evolution-engine
```

## Choose Your Path

Evolution Engine integrates into your workflow three ways. Start with the CLI, then graduate to automation as you gain confidence.

```
Path 1: CLI Explorer          Path 2: Git Hooks           Path 3: GitHub Action
(start here)                  (automate locally)          (automate in CI)

  evo analyze .        -->      evo init --path hooks  -->  evo init --path action
  evo report .                  evo watch .                 PR comments + badges
  evo status                    auto-analyze on commit      team-wide coverage
```

**Free tier** gets all three paths. **Pro** adds AI investigation (`evo investigate`), fix suggestions (`evo fix`), and inline PR review comments.

---

## Path 1: CLI Explorer (start here)

Navigate to any git repository and run:

```bash
cd your-project
evo analyze .
```

That's it. EE auto-detects git history, lockfiles, and config files -- no setup needed.

### Recommended first session

```bash
# 1. See what tools EE detected in your project
evo sources

# 2. Run the full analysis pipeline
evo analyze .

# 3. Check the summary
evo status

# 4. Generate a visual HTML report
evo report . --open

# 5. Preview what AI would fix (without changing files)
evo fix . --dry-run
```

### Go deeper with the CLI

```bash
# Interactive configuration wizard
evo setup .

# Or open the browser-based settings UI
evo setup --ui

# Connect GitHub API for CI + deployment + dependency signals
export GITHUB_TOKEN=ghp_...
evo analyze . --token $GITHUB_TOKEN

# Estimate what connecting additional tools would add
evo sources --what-if datadog
evo sources --what-if datadog --what-if pagerduty

# Get the investigation prompt to paste into any AI
evo analyze . --show-prompt

# Run AI investigation directly (requires API key, Pro)
export ANTHROPIC_API_KEY=sk-...
evo investigate .

# Full AI fix loop -- iterates until advisory clears (Pro)
evo fix .

# Iteration-aware prompt: compare current vs previous advisory
evo fix . --dry-run --residual

# Compare before/after a fix
evo verify .evo/phase5/advisory.json
```

---

## Path 2: Git Hooks (automate locally)

Once you trust the CLI output, automate it. Git hooks run analysis on every commit or push without you remembering to type anything.

### Quick setup

```bash
# Initialize with hooks integration
evo init . --path hooks
```

This installs a post-commit hook that runs `evo analyze` automatically. You can also install hooks manually:

```bash
# Install hooks (post-commit by default)
evo hooks install .

# Or trigger on push instead
evo hooks install . --trigger push

# Check hook status
evo hooks status .

# Remove hooks
evo hooks uninstall .
```

### Continuous watching

For ongoing monitoring without git hooks, use the watcher:

```bash
# Foreground -- polls for new commits, Ctrl+C to stop
evo watch .

# Check every 30 seconds, only alert on critical findings
evo watch . --interval 30 --min-severity critical

# Run as a background daemon
evo watch . --daemon

# Check daemon status
evo watch . --status

# Stop the daemon
evo watch . --stop
```

---

## Path 3: GitHub Action (CI)

Add Evolution Engine to your pull request workflow. Every PR gets an automated analysis comment with risk badges and evidence links.

### Quick setup

```bash
# Generate the workflow file automatically
evo init . --path action

# Commit and push to activate
git add .github/workflows/evo-monitor.yml
git commit -m "ci: add Evolution Engine analysis"
git push
```

### Manual workflow setup

Add to `.github/workflows/evo-monitor.yml`:

```yaml
name: Evolution Engine
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
  pull-requests: write
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
          comment: true
```

### All paths at once

```bash
# Set up CLI + hooks + Action in one command
evo init . --path all
```

---

## Adapters

```bash
# See what adapters are available for tools in your repo
evo adapter discover .

# Install a discovered adapter
pip install evo-adapter-datadog
```

## Community Patterns

EE distributes community patterns through two redundant channels: a real-time registry and durable PyPI packages. Both are checked automatically on `evo analyze`.

The default package [`evo-patterns-community`](https://pypi.org/project/evo-patterns-community/) is auto-fetched from PyPI -- no `pip install` needed.

```bash
# Patterns import automatically during analysis
evo analyze .
#   Imported 25 pattern(s) from community registry
#   Imported 25 pattern(s) from community packages

# Pull/push patterns from the community registry
evo patterns pull .
evo patterns push .   # requires: evo config set sync.privacy_level 2

# Add a third-party pattern package
evo patterns add evo-patterns-web-security

# See what's indexed
evo patterns packages

# Block an unwanted package
evo patterns block evo-patterns-untrusted

# Create your own pattern package
evo patterns new my-patterns
# Edit evo_patterns_my_patterns/patterns.json
evo patterns validate evo-patterns-my-patterns
evo patterns publish evo-patterns-my-patterns
```

## Configuration

```bash
# Interactive wizard (recommended for first-time setup)
evo setup .

# Or configure individual settings
evo config list
evo config set ai.model claude-sonnet-4-5-20250929
evo config set github.token ghp_...
evo config set sync.auto_pull true
evo config set sync.privacy_level 2
```

## What it watches

| Family | Signals | Source |
|--------|---------|--------|
| **Git** | File count, dispersion, locality, co-change novelty | Git history |
| **Dependencies** | Package count, dependency depth | Lockfiles |
| **CI** | Build duration, failures | GitHub Actions API |
| **Deployments** | Release cadence, pre-releases, assets | GitHub Releases API |

When EE detects unusual patterns -- a commit touching 10x more files than usual, or a dependency count spike -- it flags them with risk levels and PM-friendly explanations.

Cross-family patterns are the key insight: "When dependency changes happen, git dispersion also spikes" is something no single tool can see.

## All commands

```
Core
  evo analyze [path]              Run the full analysis pipeline
  evo report [path]               Generate visual HTML report
  evo sources [path]              Show detected data sources + what-if estimates
  evo status [path]               Show adapter and run info
  evo investigate [path]          AI root cause analysis (Pro)
  evo fix [path]                  AI fix-verify loop (Pro)
  evo fix [path] --residual       Iteration-aware prompt (current vs previous)
  evo verify <advisory>           Compare current state to a previous advisory

Setup & Integration
  evo init [path]                 Detect environment and suggest integration path
  evo init [path] --path cli     Set up CLI-only analysis
  evo init [path] --path hooks   Install git hooks for auto-analysis
  evo init [path] --path action  Generate GitHub Action workflow
  evo init [path] --path all     Set up all integration paths
  evo setup [path]               Interactive configuration wizard
  evo setup --ui                 Browser-based settings page
  evo watch [path]               Watch for commits and auto-analyze
  evo hooks install [path]       Install git hooks
  evo hooks uninstall [path]     Remove git hooks
  evo hooks status [path]        Show hook status

Adapters
  evo adapter list [path]         Show connected adapters and plugins
  evo adapter discover [path]     Find available adapters for your tools
  evo adapter new <name>          Scaffold a new adapter project

Patterns & Knowledge Base
  evo patterns list [path]        Show knowledge base
  evo patterns packages           List pattern packages + cache status
  evo patterns new <name>         Scaffold a pattern package
  evo patterns validate <path>    Validate a pattern package
  evo patterns publish <path>     Publish to PyPI
  evo patterns add <package>      Subscribe to a pattern package
  evo patterns remove <package>   Unsubscribe from a pattern package
  evo patterns pull [path]        Fetch community patterns
  evo patterns push [path]        Share anonymized patterns

Settings & History
  evo config list                 Show all settings
  evo config set <key> <val>      Update a setting
  evo license status              Check license tier
  evo history list [path]         Show run history
  evo history diff [r1 r2]        Compare two runs
```

Your code never leaves your machine. [Learn more](docs/INTEGRATIONS.md)
