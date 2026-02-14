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

Publishing makes your adapter available to all EE users worldwide via PyPI:

```bash
pip install build twine
python -m build
twine upload dist/*
```

**What happens after publish:**
1. Trust badge changes from `[local]` to `[community]` (verified by PyPI metadata)
2. Users running `evo adapter discover` in repos with your tool will see your adapter
3. The notification system will alert users who have the tool detected in their repo
4. `evo adapter check-updates` will track future versions

**PyPI integration is read-only on the user side** — EE queries the public PyPI
JSON API (`https://pypi.org/pypi/{package}/json`) using stdlib `urllib.request`.
No API keys or authentication needed for discovery. Only the publisher needs
PyPI credentials.

## 6. Discover

EE discovers adapters through three mechanisms:

**a) Direct install (manual):**
```bash
pip install evo-adapter-jenkins
evo adapter list .  # Shows: [community] ci/jenkins
```

Entry points declared in `pyproject.toml` register the adapter with EE's plugin system.

**b) Prescan-based discovery (`evo adapter discover`):**
```bash
evo adapter discover .
# Available adapters (install via pip):
#   evo-adapter-datadog       v1.0.0   ← Datadog (monitoring)
#   evo-adapter-sentry        v0.2.0   ← Sentry (error_tracking)
```

This scans the repo for known tools (config files, packages, imports), checks
PyPI for matching adapter packages, and shows what's available to install.

**c) Automatic notifications:**
After `evo analyze`, the notification system checks for adapters matching
detected tools that aren't installed yet. Users see:
```
Notifications:
  Adapter available: evo-adapter-datadog v1.0.0 (detected Datadog in repo).
  Install: pip install evo-adapter-datadog
```

Notifications are cached (24h), respect `DO_NOT_TRACK=1`, and can be
managed with `evo notifications list/dismiss`.

## 7. Update

EE never auto-updates adapters. Users are notified of available updates:

```bash
evo adapter check-updates       # Explicit check against PyPI
evo adapter list .               # Shows update indicator
evo analyze .                    # Prints notifications at end
evo notifications list           # View all pending notifications
evo notifications dismiss        # Clear after reading
```

**How update checking works:**
- Queries the public PyPI JSON API (no authentication needed)
- Results cached in `~/.evo/version_cache.json` with 24-hour TTL
- EE self-update nudge has a separate 7-day check interval
- Respects `DO_NOT_TRACK=1` and `evo config set adapter.check_updates false`
- Runs in the background after analysis — never blocks the pipeline

**Community pattern auto-pull (opt-in):**
```bash
evo config set sync.auto_pull true
```

When enabled, `evo analyze` fetches new community patterns from the registry
before Phase 4 discovery. Throttled to once per 24 hours.

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
