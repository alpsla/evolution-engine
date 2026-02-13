# Adapter Developer Guide

Build, test, and publish plugin adapters for Evolution Engine.

## Quick Start

```bash
# 1. Scaffold a new adapter
evo adapter new jenkins --family ci

# 2. Develop your adapter logic
cd evo-adapter-jenkins/
# Edit evo_jenkins/__init__.py

# 3. Validate against the Adapter Contract
evo adapter validate evo_jenkins.JenkinsAdapter --args '{"url": "http://ci"}'

# 4. Run security scan
evo adapter security-check evo_jenkins

# 5. Publish to PyPI
pip install build && python -m build
pip install twine && twine upload dist/*
```

## Documentation

| Document | Description |
|----------|-------------|
| [BUILDING.md](BUILDING.md) | Step-by-step guide to building an adapter |
| [SECURITY.md](SECURITY.md) | Security requirements and scanning |
| [TRUST_TIERS.md](TRUST_TIERS.md) | Trust badges and promotion path |
| [LIFECYCLE.md](LIFECYCLE.md) | Full adapter governance lifecycle |

## CLI Command Reference

| Command | Description |
|---------|-------------|
| `evo adapter list [path]` | List detected adapters with trust badges |
| `evo adapter validate <path>` | Validate adapter against the contract |
| `evo adapter validate <path> --security` | Validate + security scan |
| `evo adapter security-check <target>` | Standalone security scan |
| `evo adapter new <name> --family <f>` | Scaffold a new adapter package |
| `evo adapter prompt <name> --family <f>` | Generate AI prompt to build adapter |
| `evo adapter guide` | Show the building guide |
| `evo adapter request <desc>` | Request a new adapter |
| `evo adapter requests` | List pending requests |
| `evo adapter block <name> -r "reason"` | Block an adapter locally |
| `evo adapter unblock <name>` | Unblock a blocked adapter |
| `evo adapter check-updates` | Check PyPI for plugin updates |
| `evo adapter report <name>` | Report a broken/malicious adapter |

## Architecture

Adapters connect external tools to Evolution Engine's event pipeline:

```
External Tool → Adapter → SourceEvent → Phase 1 (ingestion) → Phases 2-5
```

Every adapter must:
1. Declare `source_family`, `source_type`, `ordering_mode`, `attestation_tier`
2. Implement `iter_events()` yielding `SourceEvent` dicts
3. Pass all 13 structural checks via `evo adapter validate`
4. Pass security scanning via `evo adapter security-check`

See [BUILDING.md](BUILDING.md) for the full contract reference.
