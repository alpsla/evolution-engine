# Quickstart

## Install

```bash
pip install evolution-engine
```

## Your first analysis (30 seconds)

Navigate to any git repository and run:

```bash
cd your-project
evo analyze .
```

That's it. EE auto-detects git history, lockfiles, and config files — no setup needed.

## Recommended workflow

Here's the typical sequence to get full value from your first run:

```bash
# 1. See what tools EE detected in your project
evo sources

# 2. Run the full analysis pipeline
evo analyze .

# 3. Generate a visual HTML report
evo report .

# 4. Preview what AI would fix (without changing files)
evo fix . --dry-run
```

## Go deeper

```bash
# Check your license tier
evo license status

# Connect GitHub API for CI + deployment + dependency signals
export GITHUB_TOKEN=ghp_...
evo analyze . --token $GITHUB_TOKEN

# Estimate what connecting additional tools would add
evo sources --what-if datadog
evo sources --what-if datadog --what-if pagerduty

# Get the investigation prompt to paste into any AI
evo analyze . --show-prompt

# Run AI investigation directly (requires API key)
export ANTHROPIC_API_KEY=sk-...
evo investigate .

# Full AI fix loop — iterates until advisory clears
evo fix .

# Open report in your browser
evo report . --open

# Compare before/after a fix
evo verify .evo/phase5/advisory.json
```

## Adapters & Updates

```bash
# See what adapters are available for tools in your repo
evo adapter discover .

# Install a discovered adapter
pip install evo-adapter-datadog

# Check for adapter and EE updates
evo adapter check-updates

# View pending notifications (new adapters, updates)
evo notifications list

# Dismiss notifications after reading
evo notifications dismiss
```

## Configuration

```bash
# See all settings
evo config list

# Set your preferred AI model
evo config set ai.model claude-sonnet-4-5-20250929

# Set a default GitHub token
evo config set github.token ghp_...

# Auto-pull community patterns on each analysis
evo config set sync.auto_pull true

# Opt into anonymous pattern sharing
evo config set sync.privacy_level 2
```

## GitHub Action

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

## What it watches

| Family | Signals | Source |
|--------|---------|--------|
| **Git** | File count, dispersion, locality, co-change novelty | Git history |
| **Dependencies** | Package count, dependency depth | Lockfiles |
| **CI** | Build duration, failures | GitHub Actions API |
| **Deployments** | Release cadence, pre-releases, assets | GitHub Releases API |

When EE detects unusual patterns — a commit touching 10x more files than usual, or a dependency count spike — it flags them with risk levels and PM-friendly explanations.

Cross-family patterns are the key insight: "When dependency changes happen, git dispersion also spikes" is something no single tool can see.

## All commands

```
evo analyze [path]              Run the full analysis pipeline
evo report [path]               Generate visual HTML report
evo sources [path]              Show detected data sources + what-if estimates
evo investigate [path]          AI root cause analysis
evo fix [path]                  AI fix-verify loop
evo verify <advisory>           Compare current state to a previous advisory
evo status [path]               Show adapter and run info
evo adapter list [path]         Show connected adapters and plugins
evo adapter discover [path]     Find available adapters for your tools
evo adapter check-updates       Check PyPI for adapter updates
evo adapter new <name>          Scaffold a new adapter project
evo notifications list          Show pending update notifications
evo notifications dismiss       Dismiss notifications
evo license status              Check license tier
evo config list                 Show all settings
evo config set <key> <val>      Update a setting
evo patterns list [path]        Show knowledge base
evo patterns pull [path]        Fetch community patterns
evo patterns push [path]        Share anonymized patterns
evo history list [path]         Show run history
evo history diff [r1 r2]        Compare two runs
```

Your code never leaves your machine. [Learn more](docs/INTEGRATIONS.md)
