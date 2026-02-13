# Adapter Lifecycle & Governance

The full lifecycle of an Evolution Engine adapter, from request to retirement.

## Lifecycle Overview

```
Request → Build → Validate → Security-Check → Publish → Discover → Update → Report → Block
```

## 1. Request

Users can request adapters for tools they use:

```bash
evo adapter request "Bitbucket Pipelines CI adapter" --family ci
```

Requests are saved locally. To submit to the community:
- Open a GitHub Issue with the `adapter-request` label
- Community votes prioritize which adapters get built

## 2. Build

Two paths to build an adapter:

**AI-Assisted:**
```bash
evo adapter prompt jenkins --family ci -d "Fetch builds from Jenkins API"
# Paste the generated prompt into Claude, ChatGPT, or Cursor
```

**Manual Scaffolding:**
```bash
evo adapter new jenkins --family ci --output ~/projects
cd ~/projects/evo-adapter-jenkins
# Edit evo_jenkins/__init__.py
```

See [BUILDING.md](BUILDING.md) for the full development guide.

## 3. Validate

Every adapter must pass 13 structural checks:

```bash
evo adapter validate evo_jenkins.JenkinsAdapter --args '{"url": "http://ci"}'
```

Checks include: required attributes, valid family, event structure, JSON
serializability, attestation format, and more.

## 4. Security Check

Static analysis of adapter source for dangerous patterns:

```bash
evo adapter security-check evo_jenkins
# or combined:
evo adapter validate evo_jenkins.JenkinsAdapter --security
```

See [SECURITY.md](SECURITY.md) for what's scanned and how to fix findings.

## 5. Publish

```bash
pip install build twine
python -m build
twine upload dist/*
```

Once published, the adapter is automatically discoverable by anyone who
`pip install`s it. Trust badge changes from `[local]` to `[community]`.

## 6. Discover

EE discovers adapters automatically via Python entry points:

```bash
pip install evo-adapter-jenkins
evo adapter list .  # Shows: [community] ci/jenkins
```

No configuration needed. Entry points declared in `pyproject.toml` register
the adapter with EE's plugin system.

## 7. Update

EE never auto-updates adapters. Users are notified of available updates:

```bash
evo adapter check-updates   # Explicit check
evo adapter list .           # Shows update indicator if cached
evo analyze .                # Prints nudge at end if EE update available
```

Updates are pulled from PyPI with a 24-hour cache TTL.

## 8. Report

Users can report broken or malicious adapters:

```bash
evo adapter report evo-adapter-bad --category security-concern
evo adapter report evo-adapter-bad -c crashes -d "Fails on Python 3.12"
```

Reports are saved locally. If `GITHUB_BOT_TOKEN` is set, a GitHub Issue is
also filed with the `adapter-report` label.

Categories: `crashes`, `wrong-data`, `security-concern`, `other`.

## 9. Block

Adapters can be blocked from detection:

```bash
# Block locally
evo adapter block bad-adapter -r "Known vulnerability"

# Unblock
evo adapter unblock bad-adapter
```

**Blocklist sources:**
- **Bundled** (`evolution/data/adapter_blocklist.json`): Ships with EE.
  Updated by maintainers when confirmed-bad adapters are reported.
- **Local** (`~/.evo/blocklist.json`): User-managed. Takes precedence.

Blocked adapters are hidden from `evo adapter list` output and appear in a
separate "Blocked" section.

## Removal Process

1. User reports adapter via `evo adapter report`
2. Maintainers investigate the report
3. If confirmed: adapter is added to the bundled blocklist
4. If previously verified: removed from `verified_adapters.json`
5. On next EE release, the adapter is blocked for all users
