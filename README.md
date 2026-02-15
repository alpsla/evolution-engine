# Evolution Engine

**Development Process Intelligence — a local-first CLI tool that observes how software evolves, learns what is structurally normal, and surfaces unexpected change with evidence to act.**

---

## What It Does

Run `evo analyze .` on any git repository. The Evolution Engine detects adapters automatically, builds per-repo baselines, and reports when your development process deviates from its own historical norms — across commits, CI, dependencies, deployments, and more.

No data leaves your machine. No configuration required. No accounts to create.

### The Pipeline

```
Sources → Phase 1 (Record) → Phase 2 (Measure) → Phase 3 (Explain)
                                  │                    │
                                  └──── Phase 4 (Learn) ←──┘
                                           │
                                    Phase 5 (Inform)
                                           │
                                      HTML Report
                                           │
                                       HUMAN / AI
```

| Phase | What It Does |
|-------|-------------|
| **Phase 1** | Records immutable events from truth sources |
| **Phase 2** | Computes baselines and deviation signals (MAD/IQR robust statistics) |
| **Phase 3** | Explains signals in human language (template + optional LLM) |
| **Phase 4** | Discovers cross-source patterns (correlation, lift, presence-based) |
| **Phase 5** | Advisory reports with evidence packages |

---

## Quick Start

```bash
pip install evolution-engine
evo analyze .
```

### Three Integration Paths

| Path | Command | When to use |
|------|---------|-------------|
| **CLI Explorer** | `evo analyze .` | Start here -- manual analysis, reports, investigation |
| **Git Hooks** | `evo init . --path hooks` | Automate locally -- analyze on every commit or push |
| **GitHub Action** | `evo init . --path action` | Automate in CI -- PR comments with risk badges |

Start with the CLI. Graduate to hooks when you trust the output. Add the GitHub Action for team-wide coverage. See [QUICKSTART.md](QUICKSTART.md) for the full walkthrough.

```bash
# Path 1: CLI Explorer (start here)
evo analyze .                    # Run the full pipeline
evo report . --open              # Visual HTML report
evo status                       # Detected adapters and run info

# Path 2: Git Hooks (automate locally)
evo init . --path hooks          # Install post-commit hook
evo watch .                      # Or poll for commits continuously

# Path 3: GitHub Action (CI)
evo init . --path action         # Generate workflow file, then push

# All paths at once
evo init . --path all
```

Free tier gets all three paths. Pro adds AI investigation, fix suggestions, and inline PR review comments.

### From Source

```bash
git clone <repo-url>
cd evolution-engine
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Run the test suite (840+ tests)
python -m pytest tests/ -v
```

### Environment Variables

```bash
# .env file (all optional)
GITHUB_TOKEN=ghp_xxx            # Unlocks CI, deployment, security adapters
EVO_LICENSE_KEY=xxx              # Pro/Team features (free tier works without)
OPENROUTER_API_KEY=xxx           # LLM-enhanced explanations (Phase 3.1)
PHASE31_ENABLED=false            # LLM off by default
```

---

## Source Families & Auto-Detection

The adapter registry automatically detects available data sources in three tiers:

### Tier 1 — File-Based (zero config, always works offline)

| Family | Detected By | What It Observes |
|--------|------------|-----------------|
| Version Control | `.git/` | Commits, file changes, structural coupling, co-change novelty |
| Dependency Graph | `requirements.txt`, `package-lock.json`, `go.mod`, `Cargo.lock`, `Gemfile.lock` | Dependency count, churn, transitive depth |
| Configuration | `*.tf`, `docker-compose.yml` | Resource count, config churn |
| Schema / API | `openapi.yaml`, `*.graphql` | Endpoint growth, field changes |

### Tier 2 — API-Enriched (optional token unlocks more)

| Family | Token | What It Observes |
|--------|-------|-----------------|
| CI / Build Pipeline | `GITHUB_TOKEN` | Build durations, failure rates |
| Deployment | `GITHUB_TOKEN` | Release cadence, pre-releases, asset count |
| Security Scanning | `GITHUB_TOKEN` | Vulnerability count, severity, Dependabot alerts |

### Tier 3 — Community Plugins (pip-installable)

Already using tools like **Snyk**, **SonarQube**, **Jenkins**, **ArgoCD**, **GitLab CI**, **Datadog**, or **PagerDuty**? Evo doesn't replace them — it learns from them. Install or build an adapter to feed their data into the pipeline, and Evo will correlate it with your git history, dependencies, and other sources to discover cross-tool patterns.

```bash
pip install evo-adapter-jenkins    # Jenkins CI adapter
pip install evo-adapter-snyk       # Snyk security adapter
pip install evo-adapter-argocd     # ArgoCD deployment adapter
evo analyze .                      # Auto-detected!
```

Plugins are auto-discovered via Python `entry_points`. If an adapter for your tool doesn't exist yet, you can [build one](#building-adapters) or [request one](#cli-commands) (`evo adapter request`).

### Historical Replay

The **Git History Walker** extracts dependency, schema, and config files from git history, creating temporal evolution timelines (not just current-state snapshots). This enables Phase 4 to correlate dependency changes with CI failures, deployments, and other events over time.

---

## CLI Commands

```bash
# Core Analysis
evo analyze [path]               # Detect adapters, run full pipeline
evo analyze . --families git,ci  # Override auto-detection
evo report [path]                # Generate HTML report from last run
evo status                       # Show detected adapters and event counts
evo investigate [path]           # AI root cause analysis (Pro)
evo fix [path]                   # AI fix-verify loop (Pro)
evo fix [path] --residual        # Iteration-aware prompt (current vs previous)
evo verify <advisory>            # Compare current state to a previous advisory

# Setup & Integration
evo init [path]                  # Detect environment and suggest integration path
evo init . --path hooks          # Install git hooks for auto-analysis
evo init . --path action         # Generate GitHub Action workflow
evo init . --path all            # Set up all integration paths
evo setup [path]                 # Interactive configuration wizard
evo setup --ui                   # Browser-based settings page
evo watch [path]                 # Watch for commits and auto-analyze
evo watch . --daemon             # Run watcher in background
evo hooks install [path]         # Install git hooks
evo hooks uninstall [path]       # Remove git hooks
evo hooks status [path]          # Show hook status

# Patterns & Knowledge Base
evo patterns list                # Show discovered patterns
evo patterns pull [path]         # Fetch community patterns from registry
evo patterns push [path]         # Share anonymized patterns (requires privacy_level >= 1)
evo patterns export              # Export anonymized pattern digests
evo patterns import <file>       # Import community patterns
evo patterns packages            # List pattern packages + cache status
evo patterns new <name>          # Scaffold a pattern package
evo patterns validate <path>     # Validate a pattern package
evo patterns publish <path>      # Publish pattern package to PyPI
evo patterns add <package>       # Subscribe to a pattern package
evo patterns remove <package>    # Unsubscribe from a pattern package
evo patterns block <name>        # Block a pattern package
evo patterns unblock <name>      # Unblock a pattern package

# Adapter Ecosystem
evo adapter list                 # Show detected adapters with trust badges
evo adapter discover [path]      # Find available adapters for your tools
evo adapter validate <class>     # Run 13-check certification
evo adapter validate <class> --security  # + security scan
evo adapter security-check <mod> # Standalone security scan
evo adapter guide                # How to build an adapter
evo adapter new <name> --family ci   # Scaffold a pip-installable package
evo adapter prompt <name> --family ci  # Generate AI prompt for building
evo adapter request <description>     # Request an adapter from the community
evo adapter block <name> -r "reason"  # Block an adapter locally
evo adapter unblock <name>       # Unblock a blocked adapter
evo adapter check-updates        # Check PyPI for plugin updates
evo adapter report <name>        # Report a broken/malicious adapter

# Configuration & History
evo config list                  # Show all settings
evo config set <key> <val>       # Update a setting
evo license status               # Check license tier
evo history list [path]          # Show run history
evo history diff [r1 r2]         # Compare two runs
```

---

## Building Adapters

The Evolution Engine supports a plugin ecosystem. Third-party adapters are pip-installable packages that auto-register via Python `entry_points`.

### Quick Path

```bash
# Scaffold a complete pip package
evo adapter new jenkins --family ci

# Or generate an AI prompt and paste it into your coding assistant
evo adapter prompt jenkins --family ci --copy
```

### Certification

Before publishing, validate your adapter passes all 13 contract checks:

```bash
cd evo-adapter-jenkins
pip install -e .
evo adapter validate evo_jenkins.JenkinsAdapter
```

Adapters pass 13 structural checks + security scanning before certification.

### Learn More

```bash
evo adapter guide    # Full tutorial with contract details
```

---

## Pattern Knowledge Base

The Evolution Engine discovers cross-family patterns automatically:

- **Pearson correlation**: deviation magnitudes track together (|r| >= 0.3)
- **Lift-based co-occurrence**: deviations co-occur more than chance (lift >= 1.5)
- **Presence-based**: metric distributions differ when events co-occur (Cohen's d >= 0.2)

Patterns progress through scopes: **local** (this repo) -> **community** (shared anonymously) -> **confirmed** (local + community match).

Community patterns are distributed through two redundant channels:
- **Registry** (real-time) — patterns pushed by users are immediately available via `codequal.dev/api`
- **PyPI packages** (durable) — periodic snapshots published as [`evo-patterns-community`](https://pypi.org/project/evo-patterns-community/), auto-fetched without `pip install`

If the registry is unavailable, PyPI packages still work. Both are checked automatically on `evo analyze`.

### Pattern Distribution

```bash
# Auto-fetch happens on every `evo analyze` — no manual install needed
evo analyze .
#   Imported 25 pattern(s) from community registry
#   Imported 25 pattern(s) from community packages

# Pull/push patterns from the community registry
evo patterns pull .
evo patterns push .   # requires: evo config set sync.privacy_level 2

# Add a third-party pattern package to your sources
evo patterns add evo-patterns-web-security

# Block an unwanted package
evo patterns block evo-patterns-untrusted

# Build and publish your own pattern package
evo patterns new my-patterns
# ... edit patterns.json ...
evo patterns validate evo-patterns-my-patterns
evo patterns publish evo-patterns-my-patterns
```

---

## Project Structure

```
evolution-engine/
├── evolution/
│   ├── cli.py                     # Click-based CLI (evo command)
│   ├── orchestrator.py            # Pipeline orchestration (detect → P1-P5)
│   ├── registry.py                # 3-tier adapter auto-detection
│   ├── phase1_engine.py           # Phase 1: Observation
│   ├── phase2_engine.py           # Phase 2: Baselines (MAD/IQR)
│   ├── phase3_engine.py           # Phase 3: Explanations
│   ├── phase3_1_renderer.py       # Phase 3.1: LLM enhancement
│   ├── phase4_engine.py           # Phase 4: Pattern discovery
│   ├── phase5_engine.py           # Phase 5: Advisory
│   ├── knowledge_store.py         # SQLite knowledge base
│   ├── kb_export.py               # Anonymized pattern export/import
│   ├── kb_security.py             # Import validation (XSS, injection, traversal)
│   ├── pattern_registry.py        # Auto-fetch pattern packages from PyPI
│   ├── pattern_validator.py       # Pattern package validation
│   ├── pattern_scaffold.py        # Pattern package scaffolding
│   ├── report_generator.py        # Standalone HTML report generator
│   ├── adapter_validator.py       # 13-check adapter certification
│   ├── adapter_scaffold.py        # Package scaffolding + AI prompt gen
│   ├── license.py                 # License tier gating
│   ├── llm_openrouter.py          # OpenRouter LLM client
│   ├── llm_anthropic.py           # Anthropic LLM client
│   ├── validation_gate.py         # LLM output validation
│   ├── data/
│   │   ├── universal_patterns.json  # Bundled universal patterns
│   │   ├── pattern_index.json       # Known pattern packages
│   │   └── pattern_blocklist.json   # Blocked pattern packages
│   └── adapters/
│       ├── git/                   # Version Control (+ Git History Walker)
│       ├── ci/                    # CI / Build Pipeline (GitHub Actions)
│       ├── testing/               # Test Execution (JUnit XML)
│       ├── dependency/            # Dependency Graph (pip, npm, go, cargo, bundler)
│       ├── schema/                # Schema / API (OpenAPI)
│       ├── deployment/            # Deployment (GitHub Releases)
│       ├── config/                # Configuration (Terraform)
│       └── security/              # Security Scanning (Trivy, Dependabot)
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── unit/                      # 200+ unit tests
│   │   ├── test_phase2_deviation.py
│   │   ├── test_phase4_cooccurrence.py
│   │   ├── test_phase5_advisory.py
│   │   ├── test_knowledge_store.py
│   │   ├── test_registry.py
│   │   ├── test_adapter_validator.py
│   │   ├── test_adapter_scaffold.py
│   │   ├── test_kb_export.py
│   │   ├── test_kb_security.py
│   │   ├── test_license.py
│   │   ├── test_report_generator.py
│   │   └── adapters/              # Lockfile parser tests
│   └── integration/
│       └── test_pipeline_e2e.py   # Full pipeline integration test
├── scripts/
│   └── aggregate_calibration.py   # Cross-repo pattern aggregation
├── docs/
│   ├── ARCHITECTURE_VISION.md     # Constitution
│   ├── IMPLEMENTATION_PLAN.md     # Roadmap
│   ├── PHASE_*_CONTRACT.md        # Phase contracts (2, 3, 4, 5)
│   ├── PHASE_*_DESIGN.md          # Phase designs (2, 3, 4, 5)
│   ├── ADAPTER_CONTRACT.md        # Universal adapter contract
│   └── adapters/                  # 8 family contracts
├── pyproject.toml                 # Package config (entry point: evo)
└── .env                           # Environment config (optional)
```

---

## Open-Core Model

| Open Source (MIT) | Proprietary |
|-------------------|-------------|
| All adapters | Phase 2-5 engines |
| CLI, registry, orchestrator | Knowledge store |
| Phase 1 engine | |
| KB export/import/security | |
| Report generator | |
| Adapter scaffold & validator | |

The open adapter ecosystem ensures anyone can connect new data sources. The analysis engines are the proprietary core.

---

## Documentation

See [`docs/README.md`](docs/README.md) for the full documentation structure and authority hierarchy.

Key documents:
- **[Architecture Vision](docs/ARCHITECTURE_VISION.md)** — why the system exists and how it works
- **[Implementation Plan](docs/IMPLEMENTATION_PLAN.md)** — what's done, what's next
- **[Adapter World Map](docs/adapters/README.md)** — all 8 source families

---

## Principles

1. Observation precedes interpretation
2. History is immutable; interpretation is disposable
3. Determinism beats intelligence
4. Local baselines over global heuristics
5. Multiple weak signals beat one strong opinion
6. Absence of signal is not evidence of safety
7. Humans are escalated to, not replaced
8. Evidence enables action

---

## License

Open-core: adapters and CLI under MIT, analysis engines proprietary.
