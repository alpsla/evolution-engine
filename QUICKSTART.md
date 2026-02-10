# Quickstart

## Install

```bash
pip install evolution-engine
```

## Analyze a repo

```bash
cd your-repo
evo analyze .
```

That's it. EE auto-detects git history, lockfiles, and config files — no setup needed.

## Unlock more data

```bash
# Add CI + deployment + security families
export GITHUB_TOKEN=ghp_...
evo analyze . --token $GITHUB_TOKEN

# See what tools you already use
evo sources

# Estimate what connecting Datadog would add
evo sources --what-if datadog
```

## AI investigation

```bash
# Get the investigation prompt for any AI tool
evo analyze . --show-prompt

# Or run directly with Claude
export ANTHROPIC_API_KEY=sk-...
evo investigate .

# AI fix loop — iterates until advisory clears
evo fix .
```

## GitHub Action

```yaml
# .github/workflows/evo-monitor.yml
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

## What it does

EE monitors your development process across multiple signal families:

| Family | What it watches | Source |
|--------|----------------|--------|
| **Git** | File count, dispersion, change locality, novelty | Git history |
| **Dependencies** | Package count, dependency depth | Lockfiles |
| **CI** | Build duration, failures | GitHub Actions API |
| **Deployments** | Release cadence, pre-releases | GitHub Releases API |

When it detects unusual patterns — a commit touching 10x more files than usual, or a dependency count spike — it flags them with risk levels and PM-friendly explanations.

Cross-family patterns are the key insight: "When dependency changes happen, git dispersion also spikes" is something no single tool can see.

## Commands

```
evo analyze [path]           Run the full pipeline
evo sources [path]           Show connected + detected data sources
evo investigate [path]       AI root cause analysis
evo fix [path]               AI fix loop
evo report [path]            Generate HTML report
evo status [path]            Show adapter and run info
evo config list              Show settings
evo patterns list [path]     Show knowledge base
```

Your code never leaves your machine. [Learn more](docs/INTEGRATIONS.md)
