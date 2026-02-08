# Evolution Engine

**A deterministic, memory‑based system that observes how software evolves, learns what is structurally normal, and surfaces unexpected change with evidence to act.**

---

## What It Does

The Evolution Engine monitors software development across 8 source families — version control, CI, testing, dependencies, schemas, deployments, configuration, and security — and detects when a system's evolution deviates from its established patterns.

It does not judge code quality or enforce rules. It **remembers**, **compares**, and **explains** — providing specific evidence (commits, files, tests, dependencies) so humans or their AI assistants can investigate immediately.

### The Pipeline

```
Sources → Phase 1 (Record) → Phase 2 (Measure) → Phase 3 (Explain)
                                  │                    │
                                  └──── Phase 4 (Learn) ←──┘
                                           │
                                    Phase 5 (Inform)
                                           │
                                       HUMAN / AI
```

| Phase | What It Does | Status |
|-------|-------------|--------|
| **Phase 1** | Records immutable events from truth sources | ✅ Complete |
| **Phase 2** | Computes baselines and deviation signals | ✅ Complete |
| **Phase 3** | Explains signals in human language (+ LLM) | ✅ Complete |
| **Phase 4** | Discovers and remembers cross‑source patterns | ✅ Complete |
| **Phase 5** | Advisory reports with evidence packages | ✅ Complete |

---

## Source Families

| Family | Adapter | What It Observes |
|--------|---------|-----------------|
| Version Control | Git | Commits, file changes, structural coupling |
| CI / Build Pipeline | GitHub Actions | Build durations, failure rates, job topology |
| Test Execution | JUnit XML | Test counts, failure rates, flake patterns |
| Dependency Graph | pip | Dependency count, churn, transitive depth |
| Schema / API | OpenAPI | Endpoint growth, field changes, schema churn |
| Deployment | GitHub Releases | Deploy frequency, failure rate, rollbacks |
| Configuration | Terraform | Resource count, config churn, drift |
| Security Scanning | Trivy | Vulnerability count, severity, fix availability |

### Historical Replay

The **Git History Walker** meta-adapter extracts dependency, schema, and config files from git history, creating temporal evolution timelines (not just current state snapshots). This enables Phase 4 pattern learning to correlate dependency changes with test failures, deployments, and other cross-family events over time.

---

## Quick Start

```bash
# Clone and set up
git clone git@github.com:alpsla/evolution_monitor.git
cd evolution_monitor
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Run the full pipeline test (all families, all phases)
python tests/test_all_families.py

# Run Git History Walker to extract historical dependency/schema/config evolution
python examples/run_git_history_walker.py
```

### Environment Variables (for Phase 3.1 LLM)

```bash
# .env file
OPENROUTER_API_KEY=your-key-here
PHASE31_ENABLED=true
PHASE31_MODEL=anthropic/claude-3.5-haiku
```

---

## Calibration & Knowledge Base Seeding

The Evolution Engine includes an **automated search agent** that discovers, validates, and ranks 100+ repositories by multi-family data coverage.

### Automated Repository Discovery 🚀

Find hundreds of calibration candidates with one command:

```bash
cd .calibration

# Discover and rank 100+ repositories automatically
python search_agent.py

# Custom search parameters
python search_agent.py --min-stars 500 --max-repos 500

# Specific languages
python search_agent.py --languages Python Go TypeScript
```

**Output:** `repos_ranked.csv` with 100+ repositories ranked by:
- Family coverage (0-8 families available)
- Calibration score (0-100 points)
- Exact lockfile paths for Git History Walker
- CI runs, test counts, schema files, etc.

The search agent automatically checks each repository for:
- ✅ Git history (500+ commits for stable baselines)
- ✅ CI/CD data (GitHub Actions runs)
- ✅ Dependency lockfiles (in git history for temporal tracking)
- ✅ Test coverage (test files and frameworks)
- ✅ Schema/API files (OpenAPI, GraphQL, migrations)
- ✅ Deployment tracking (releases, tags)
- ✅ Configuration (Terraform, Kubernetes, Docker)
- ✅ Security data (advisories, Dependabot)

**Runtime:** 30-60 minutes for 100-200 repositories

### Calibration Workflow

```bash
# 1. Discover candidates (automated)
python search_agent.py --max-repos 200

# 2. Review results
cat repos_ranked.csv  # Top repos by score

# 3. Select top 10 and run calibration
python .calibration/run_calibration.py --repo SELECTED_REPO

# 4. Inspect discovered patterns
python -c "
from pathlib import Path
from evolution.knowledge_store import SQLiteKnowledgeStore
kb = SQLiteKnowledgeStore(Path('.calibration/runs/REPO/phase4/knowledge.db'))
for p in kb.list_patterns()[:10]:
    print(f'{p['sources']} — {p['metrics']} (corr={p.get('correlation_strength',0):.2f})')
kb.close()
"

# 5. Review Phase 5 advisory
cat .calibration/runs/REPO/phase5/summary.txt
```

**See:** [`.calibration/SEARCH_AGENT_GUIDE.md`](.calibration/SEARCH_AGENT_GUIDE.md) for complete documentation

---

## Project Structure

```
evolution-engine/
├── evolution/
│   ├── phase1_engine.py          # Phase 1: Observation
│   ├── phase2_engine.py          # Phase 2: Baselines (all families)
│   ├── phase3_engine.py          # Phase 3: Explanations (all families)
│   ├── phase3_1_renderer.py      # Phase 3.1: LLM enhancement
│   ├── validation_gate.py        # LLM output validation
│   ├── llm_openrouter.py         # OpenRouter LLM client
│   └── adapters/
│       ├── git/                   # Version Control
│       ├── ci/                    # CI / Build Pipeline
│       ├── testing/               # Test Execution
│       ├── dependency/            # Dependency Graph
│       ├── schema/                # Schema / API
│       ├── deployment/            # Deployment / Release
│       ├── config/                # Configuration / IaC
│       └── security/              # Security Scanning
├── docs/
│   ├── ARCHITECTURE_VISION.md     # Constitution
│   ├── PHASE_*_CONTRACT.md        # Binding contracts (2, 3, 4, 5)
│   ├── PHASE_*_DESIGN.md          # Design documents (2, 3, 4, 5)
│   ├── ADAPTER_CONTRACT.md        # Universal adapter contract
│   ├── IMPLEMENTATION_PLAN.md     # Roadmap & next actions
│   ├── adapters/                  # 8 family contracts
│   └── Research/                  # Exploratory documents
├── tests/
│   └── test_all_families.py       # End-to-end pipeline test
└── .env                           # Environment config
```

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

Private — all rights reserved.
