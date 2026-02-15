# SDLC Integration Plan

> **Goal**: Meet users where they are in their trust journey with EE.
> A new Pro user needs to *see the value working* before they'll trust automation.
> An established user needs EE to be invisible until it matters.

---

## The Three Integration Paths

These are not alternatives — they are a **progression**. Users naturally move through them as they build confidence:

```
 Path 1: CLI (Manual)         Path 2: CLI (Hooks)          Path 3: GitHub Action
 "Show me everything"         "Tell me when it matters"    "Watch my team's PRs"
 ─────────────────────        ─────────────────────        ─────────────────────
 User runs evo analyze        Hook runs on commit          Action runs on PR
 Always shows full report     Silent unless threshold met  Posts to PR comments
 Explore all features         Desktop notification         Inline review comments
 Build confidence             Auto-opens report            Verification on push

 ← TRUST BUILDS OVER TIME →
```

| Path | Trigger | Output | Who | When to use |
|------|---------|--------|-----|-------------|
| **1. CLI (Manual)** | User runs `evo analyze` | Always shows full report | New users, exploration | First days/weeks — see everything |
| **2. CLI (Hooks)** | `git commit` / `git push` | Silent unless threshold | Confident users | Once you trust EE's judgment |
| **3. GitHub Action** | PR opened/updated | PR comments + inline fixes | Teams | Continuous team-level monitoring |

---

## Path 1: Pure CLI (Manual / Explorer Mode)

**This is the default and the most important path.** When someone pays $19/mo, the first thing they do is run `evo analyze .` and see a full report. They need to:

1. See that it works
2. Understand what it finds
3. Explore Pro features (investigate, fix, patterns)
4. Build trust in the accuracy

### The Manual Workflow

```bash
# Step 1: Run analysis — always shows full report
evo analyze .

# Step 2: See everything in the browser
evo report . --open

# Step 3: Explore Pro features
evo investigate .              # AI root cause analysis
evo fix .                      # Iterative AI fix loop

# Step 4: Review history over time
evo history list               # See how findings change over runs
evo history diff               # Compare latest vs previous
```

### What the user sees — ALWAYS

The CLI always outputs a summary, regardless of severity:

```
Evolution Engine — Analysis Complete

  Scope:     my-project
  Events:    1,247 across 3 families (git, ci, dependency)
  Signals:   8 significant changes detected

  Overall:   ⚠️  Action Required — 2 Critical, 1 High, 5 Medium

  ┌─────────────────────────────────────────────────────┐
  │  #  Risk       Family      Metric                   │
  │  1  🔴 Critical  git         dispersion    (+93%)   │
  │  2  🔴 Critical  ci          run_duration  (+48%)   │
  │  3  🟠 High      dependency  max_depth     (+120%)  │
  │  4  🟡 Medium    git         files_touched (+35%)   │
  │  ...                                                │
  └─────────────────────────────────────────────────────┘

  Patterns: 2 known matches, 1 new candidate
  Report:   .evo/report.html (open with: evo report . --open)

  Next steps:
    evo investigate .    Investigate findings with AI
    evo fix .            Start AI-powered fix loop
    evo accept . 4 5     Dismiss expected changes
```

And when everything is clean:

```
Evolution Engine — Analysis Complete

  Scope:     my-project
  Events:    1,247 across 3 families (git, ci, dependency)
  Signals:   0 significant changes

  Overall:   ✅  All Clear — development patterns look healthy

  Report:   .evo/report.html
```

**Key principle:** The manual CLI never hides anything. Every run produces output. This is how users learn what EE does and calibrate their expectations.

---

## Path 2: CLI with Git Hooks (Automated Local)

**Only after the user is comfortable with Path 1** should they set up automation. The hook path is for users who think: "I trust EE — just tell me when something needs attention, don't make me remember to run it."

### Advisory Status Levels

The system already has severity tiers. For automation, we map them to **three notification thresholds**:

| Advisory Status | Icon | Meaning | Default action |
|----------------|------|---------|----------------|
| **Action Required** | ⚠️ | Critical or High findings — likely real issues | Notify + open report |
| **Needs Attention** | 🔍 | Medium findings or concern-level patterns | Notify (configurable) |
| **Worth Monitoring** | 👁️ | Low findings or watch-level patterns | Silent (log only) |
| **All Clear** | ✅ | No significant deviations | Silent |

**Default threshold: `concern`** — notifies on ⚠️ Action Required and 🔍 Needs Attention.
User can change: `evo config set hooks.min_severity critical` (only ⚠️) or `watch` (everything).

### Setup

```bash
evo install-hooks .                    # Install post-commit hook
```

That's it. From now on:

```
git commit -m "add feature"
      |
[Background: evo analyze . --quiet]
      |
  Advisory status?
      |
  ✅ All Clear ──────────────> (silent, nothing happens)
      |
  👁️ Worth Monitoring ───────> (silent, logged to .evo/hook.log)
      |
  🔍 Needs Attention ────────> Desktop notification + auto-open report
      |
  ⚠️ Action Required ────────> Desktop notification + auto-open report
```

### Configuration

```bash
# Adjust notification threshold
evo config set hooks.min_severity critical    # Only ⚠️ Action Required
evo config set hooks.min_severity concern     # ⚠️ + 🔍 (default)
evo config set hooks.min_severity watch       # ⚠️ + 🔍 + 👁️
evo config set hooks.min_severity info        # Everything (like manual mode)

# Other hook settings
evo config set hooks.trigger pre-push         # Trigger on push instead of commit
evo config set hooks.auto_open true           # Open browser on notification (default)
evo config set hooks.notify true              # Desktop notification (default)
evo config set hooks.families "git,ci"        # Restrict to specific families

# Manage hooks
evo install-hooks . --status                  # Show installed hook info
evo install-hooks . --remove                  # Uninstall
```

### The Notification

**macOS:**
```
┌─────────────────────────────────────────┐
│ Evolution Engine                         │
│ ⚠️ 2 unusual changes detected           │
│ 1 Critical (dispersion), 1 High (CI)    │
│ Click to view report                     │
└─────────────────────────────────────────┘
```

Clicking opens `.evo/report.html` in the default browser — the same interactive report from Path 1, with all the action buttons.

---

## Path 3: GitHub Action (Team Workflow)

For teams that want EE watching every PR automatically. Same analysis, delivered through GitHub's PR interface.

### Basic Workflow (Free Tier)

```yaml
name: Evolution Engine
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  evolution:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: codequal/evolution-engine@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

Produces: PR comment with risk badges, pattern matches, deviation summary.

### Full Workflow (Pro Tier)

```yaml
name: Evolution Engine
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  evolution:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: codequal/evolution-engine@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          investigate: true
          suggest-fixes: true
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
        env:
          EVO_LICENSE_KEY: ${{ secrets.EVO_LICENSE_KEY }}
```

Adds: AI investigation, inline fix suggestions, verification on subsequent pushes.

### PR Output Flow

```
PR opened
   |
[Action: evo analyze]
   |
Findings? ──No──> PR comment: "✅ All Clear — no unusual changes detected"
   |
  Yes
   |
[Action: evo investigate] (Pro)
   |
PR comment:
  "⚠️ 3 unusual changes detected [1 Critical, 2 Medium]"
  + Table with risk badges
  + Pattern matches
  + AI investigation summary
   |
[Action: inline suggestions] (Pro)
   |
Inline review comments on changed lines
   |
Developer pushes fix
   |
[Action: evo verify]
   |
Updated PR comment:
  "2 of 3 resolved (67%) — 1 still flagged"
```

---

## User Response to Findings — Fix, Accept, or Scope

EE detects anomalies. The user has three possible responses:

1. **Fix it** — the finding is a real problem, apply a fix
2. **Accept it permanently** — this metric is always noisy for this project (current `evo accept`)
3. **Scope-accept it** — this was planned/expected for these specific commits, but flag it if it happens again unexpectedly (NEW: `evo accept --scope`)

### The "Expected Change" Problem

Current `evo accept` is a **permanent global blanket**:
```bash
evo accept . 1                 # Accepts "git:dispersion" FOREVER
```

This is wrong for the most common case: "We did a planned refactoring last week.
Of course dispersion spiked. But if it spikes again next month for no reason, I
want to know."

### Scoped Acceptance

```bash
# Accept for specific commits (most common)
evo accept . 1 --scope commits abc123..def456
evo accept . 1 --scope commits abc123           # Single commit

# Accept for a date range
evo accept . 1 --scope dates 2026-02-10..2026-02-14

# Accept for the current advisory only (one-time)
evo accept . 1 --scope this-run

# Accept permanently (current behavior, still available)
evo accept . 1 --scope permanent
evo accept . 1                                   # Default without --scope: permanent (backward compat)
```

When Phase 5 builds the advisory, scoped acceptances are checked:
- **commits**: if the signal's trigger events fall within the accepted commit range → suppress
- **dates**: if the signal's trigger events fall within the date range → suppress
- **this-run**: acceptance expires after the next `evo analyze` (one-time dismiss)
- **permanent**: always suppress (current behavior)

**Accepted entry in `accepted.json` (enhanced):**
```json
{
  "key": "git:dispersion",
  "family": "git",
  "metric": "dispersion",
  "reason": "Planned monorepo refactoring sprint",
  "scope": {
    "type": "commits",
    "from": "abc123",
    "to": "def456"
  },
  "accepted_at": "2026-02-14T15:00:00Z",
  "from_advisory": "adv-123"
}
```

This means: "git:dispersion is expected between commits abc123 and def456. If it
shows up in later commits, flag it normally."

### How Scoped Acceptance Works in Each Path

| Path | User action | What happens next |
|------|------------|-------------------|
| **Path 1 (CLI)** | `evo accept . 1 --scope commits abc..def -r "Planned refactor"` | Next `evo analyze` skips this finding for those commits |
| **Path 2 (Hooks)** | Report has "Accept — expected" button with scope picker | Next commit's hook run respects the scope |
| **Path 3 (Action)** | PR comment reaction or command: `/evo accept 1 --scope this-run` | Next push's action run skips this finding |

---

## The Fix Loop — How Remediation Actually Works

When findings ARE real problems (not expected), the user needs to fix them. The fix
loop works differently depending on the user's tooling — and most users will NOT
have Claude CLI.

### The Two Fix Modes

```
                        EE detects findings
                               |
              ┌────────────────┴────────────────┐
              ▼                                  ▼
       Mode A: Prompt-and-Verify          Mode B: Manual
       (Cursor/Copilot/ChatGPT/Claude)   (Developer reads report)
              |                                  |
      User copies fix prompt              User reads report
      pastes into their AI tool           fixes by hand
      AI fixes files                             |
              |                           User commits fix
      User commits fix                           |
              |                           [evo verify or next hook]
      [evo verify or next hook]                  |
              |                           Sees what's resolved
      Sees what's resolved                       |
              |                                Done
      Copy residual prompt
      paste again → iterate
              |
           Done
```

> **Note:** If `claude` CLI is on PATH, `evo fix .` can run the fully automated
> RALF loop (agent edits files, EE verifies, iterates automatically). This works
> well for developers with Claude Code but is a niche setup. The prompt-and-verify
> mode described below is the primary experience.

### Mode A: Prompt-and-Verify (Cursor, Copilot, ChatGPT, or any AI tool)

**This is the primary fix experience.** The user has their preferred AI tool open.
The loop is a **two-step dance** between EE and the user's AI tool:

```bash
# Step 1: EE generates the fix prompt
evo fix . --dry-run            # Shows the prompt, doesn't edit anything
```

The report's "Fix with AI" button (or `--dry-run`) produces a prompt like:

```
INVESTIGATION REPORT

## Finding 1: dispersion
Risk: Critical
Root cause: Commit abc123 touches 15 files across 8 directories...
Assessment: problem
Suggested fix: Split into focused commits by module. Specifically:
  - src/auth.py and src/auth_test.py → auth module commit
  - src/api/*.py → api module commit

## Finding 2: run_duration
Risk: High
Root cause: New dependency `heavy-lib` added 40s to CI...
Suggested fix: Add caching in .github/workflows/test.yml, line 23...
```

User copies this into Cursor/Copilot. The AI makes changes.

```bash
# Step 2: User tells EE to check what changed
evo verify .                   # Re-analyzes and compares against previous advisory
```

EE shows:

```
Verification against previous advisory:

  ✅ Resolved:  dispersion (back to normal)
  ⚠️ Persisting: run_duration (still high, but improving: 1200s → 900s)

  1 of 2 resolved (50%)

  Residual prompt saved to: .evo/phase5/residual_prompt.txt
  Copy it to continue fixing in your AI tool.
```

```bash
# Step 3: If residual findings exist, copy the NEW prompt and repeat
evo fix . --dry-run --residual  # Generates prompt focused on what's still broken
```

The residual prompt is smarter — it tells the AI what was already fixed, what's
still broken, and what NOT to re-introduce:

```
RESIDUAL FINDINGS (iteration 2):

ALREADY RESOLVED (do NOT re-introduce):
  ✅ dispersion — back to normal after splitting commits

STILL FLAGGED:
  - ci / run_duration: 900s (was 1200s, improving but still high)
    Previous fix partially worked. Build on it.

Focus on the CI configuration. The dependency caching helped but
isn't sufficient...
```

User copies into Cursor, AI makes more changes, user runs `evo verify .` again.
**The loop continues until the user is satisfied or EE shows all clear.**

### Mode B: Manual (Developer fixes by hand)

For developers who prefer to read the report and fix manually:

```bash
evo analyze .                  # See findings
evo report . --open            # Read HTML report
# ... developer makes changes ...
evo verify .                   # Check what's resolved
```

Same `evo verify` step — just without the AI prompt generation.

### How Each Path Handles Findings

| Path | Detection | User Response Options | Verification |
|------|-----------|----------------------|-------------|
| **Path 1: CLI** | `evo analyze` | Fix (copy prompt to AI tool) / Accept (scope or permanent) / Ignore | `evo verify .` (manual) |
| **Path 2: Hooks** | Auto on commit | Fix (report button → AI tool) / Accept (report button with scope) | Next commit auto-verifies |
| **Path 3: Action** | Auto on PR | Fix (inline suggestions → AI tool) / Accept (PR command) | Next push auto-verifies |

### Path 2 Fix Loop (Hooks)

```
Commit → [hook: evo analyze] → ⚠️ Notification opens report
   |
User sees report with findings
   |
Clicks "Fix with AI" → prompt copied to clipboard
   |
Pastes into Cursor/Copilot → AI fixes files
   |
User commits the fix
   |
[hook: evo analyze] → runs again automatically
   |
✅ All clear? → silent, done
⚠️ Still findings? → notification with UPDATED report
   |                   (shows: "2 of 3 resolved, 1 still flagged")
   |                   (new residual prompt ready to copy)
   |
User iterates until clear or accepts remaining
```

**The commit hook IS the verification step.** Every commit triggers re-analysis.
If the fix resolved the findings, the hook stays silent. If not, it notifies again
with the residual findings. The loop is natural — commit-based iteration.

### Path 3 Fix Loop (GitHub Action)

```
PR opened → [action: evo analyze + investigate]
   |
PR comment: "⚠️ 3 findings [1 Critical, 2 Medium]"
Inline comments on specific changed lines
   |
Developer reads inline suggestions
   |
Developer pushes fix to PR branch
   |
[action: evo analyze + verify] (synchronize event)
   |
PR comment UPDATED: "2 of 3 resolved (67%)"
Remaining inline comments updated
   |
Developer pushes another fix
   |
[action: evo verify]
   |
PR comment: "✅ All clear — all 3 resolved"
```

**The push is the verification step.** Every push to the PR branch triggers the action
again, which re-analyzes and compares against the previous advisory. The PR comment
updates with resolution progress. The developer sees inline suggestions evolve as
findings get resolved.

### Key Design Principle

**EE never blocks the developer.** In all three paths:
- Detection is non-blocking (background hook, async action, or explicit CLI)
- Fix prompts are copy-paste friendly (work with ANY AI tool)
- Verification happens naturally (next commit or next push)
- The loop terminates when the user decides it's done (accept remaining, or all clear)

The critical UX insight: `evo verify` is just `evo analyze` that knows about the
previous run. It's not a separate mode — it's the same pipeline with a comparison
step. This means any trigger that runs `evo analyze` (hook, action, manual) also
acts as verification if a previous advisory exists.

---

## The Onboarding Journey

### Day 1: "Does this thing work?"

```bash
pip install evolution-engine
evo license activate <key>        # Pro activated
evo analyze .                     # Full report — see everything
evo report . --open               # Browse the HTML report
evo investigate .                 # Try AI investigation
```

User sees the full pipeline working. They understand what EE detects and how severe the findings are. They can explore all Pro features immediately.

### Week 1: "I trust it, but I want to tune it"

```bash
evo analyze .                     # Run a few more times
evo accept . 3 5                  # Mark expected changes as accepted
evo config set analyze.families "git,ci,dependency"  # Focus on what matters
evo history diff                  # See findings evolving over runs
```

User calibrates: accepting false positives, restricting families, comparing runs.

### Week 2+: "Just tell me when something's wrong"

```bash
evo install-hooks .               # One command, done
# Or:
evo init                          # Guided setup (hooks, action, or both)
```

Now EE runs silently. User only sees it when the advisory reaches ⚠️ Action Required or 🔍 Needs Attention.

### For Teams: "Watch our PRs"

```bash
evo init --github-action          # Generates workflow YAML
git add .github/workflows/evolution.yml
git push
```

Every PR gets automatic analysis, investigation, and inline suggestions.

---

## Implementation Plan

### Phase A: CLI Experience Polish

**Goal:** Make Path 1 compelling enough that new Pro users immediately see the value.

**Files:** `evolution/cli.py`, `evolution/report_generator.py`

1. **Enhanced terminal output** — structured summary table (as shown above) with advisory status icon, risk counts, next-step commands. Currently output is minimal; needs to show the "dashboard" feel in the terminal.

2. **Interactive HTML report buttons** — add action elements to the report:
   - "Investigate with AI" — copies command to clipboard
   - "Fix with AI" — copies command to clipboard
   - "Open in IDE" — `vscode://file/{path}:{line}` links per finding
   - "Dismiss" per finding — shows `evo accept` command
   - Severity filter toggle — show/hide by risk level
   - Finding deep-links — anchor URLs for sharing

3. **Advisory status rollup** — compute overall advisory status from individual finding severities:
   - Any Critical or High → ⚠️ Action Required
   - Any Medium or concern patterns → 🔍 Needs Attention
   - Only Low or watch patterns → 👁️ Worth Monitoring
   - No findings → ✅ All Clear
   - Expose as `advisory.status` in JSON output

### Phase B: Git Hook Integration

**Goal:** Deliver the "silent until it matters" experience with one command.

**New files:** `evolution/hooks.py`, `tests/unit/test_hooks.py`

1. **`evolution/hooks.py`** — core hook management:
   - `install_hook(repo_path, trigger="post-commit")` — writes hook script
   - `remove_hook(repo_path, trigger)` — removes EE section from hook
   - `hook_status(repo_path)` — returns installed hooks info
   - Hook script template: runs `evo analyze --quiet --json`, checks advisory status against threshold, triggers notification + report if exceeded
   - Respects existing hooks (EE section between markers)
   - Background execution (non-blocking via `nohup`)

2. **`evo install-hooks` CLI command** with `--pre-push`, `--remove`, `--status`

3. **Desktop notification module** — `_notify(title, message, report_path)`:
   - macOS: `osascript -e 'display notification'`
   - Linux: `notify-send`
   - Fallback: terminal bell + stderr message

4. **Config keys** in `evolution/config.py`:
   ```
   hooks.trigger = "post-commit"
   hooks.auto_open = true
   hooks.notify = true
   hooks.min_severity = "concern"      # ⚠️ + 🔍 by default
   hooks.families = ""
   hooks.background = true
   ```

5. **Hook result file** — `.evo/last-hook-run.json`:
   ```json
   {
     "timestamp": "2026-02-14T15:30:00Z",
     "advisory_status": "action_required",
     "significant_changes": 3,
     "report_path": ".evo/report.html",
     "notified": true
   }
   ```

### Phase C: Setup Wizard & Workflow Templates

**Goal:** Guide users to the right integration path for their situation.

**New files:** `evolution/init.py`, `evolution/templates/`, `tests/unit/test_init.py`

1. **`evo init`** — interactive setup wizard:
   - Detects: is this a GitHub repo? does `.github/workflows/` exist?
   - Presents three paths:
     ```
     How would you like to use Evolution Engine?

     1. CLI only (recommended to start)
        Run evo analyze manually. Best for exploring features.

     2. Automated local hooks
        EE runs silently on every commit. Notifies when findings
        reach your threshold. Requires: evo install-hooks

     3. GitHub Action (for teams)
        EE runs on every PR. Posts comments and inline suggestions.
        Generates: .github/workflows/evolution.yml

     4. All of the above
     ```
   - For option 2: calls `install_hook()`
   - For option 3: generates workflow YAML from template
   - Shows Free vs Pro features relevant to chosen path
   - Saves choice to `init.integration` config key

2. **Workflow template** — `evolution/templates/github-action.yml`:
   - Free version (analyze + comment)
   - Pro version (+ investigate + suggest-fixes)
   - `evo init --github-action` writes to `.github/workflows/evolution.yml`

3. **First-run hint** — after `evo analyze` completes (only first 3 runs):
   ```
   Tip: Run `evo init` to set up automatic analysis (hooks or GitHub Action).
   ```

### Phase D: Watch/Daemon Mode

**Goal:** Alternative to git hooks for users who prefer a running process.

**New files:** `evolution/watcher.py`, `tests/unit/test_watcher.py`

1. **`evo watch .`** — foreground mode:
   - Monitors `.git/refs/heads/` for new commits
   - On new commit: runs analysis, prints summary, notifies if threshold met
   - Ctrl+C to stop

2. **`evo watch . --daemon`** — background mode:
   - PID file at `.evo/watch.pid`
   - Log at `.evo/watch.log`
   - `evo watch --stop` terminates

3. **Polling fallback** — `--interval N` for environments without fs events

### Phase E: Scoped Acceptance

**Goal:** Let users say "this was expected" without permanently hiding future anomalies.

**Files:** `evolution/accepted.py`, `evolution/cli.py`, `evolution/phase5_engine.py`

1. **Enhance `accepted.json` schema** — add `scope` field to each entry:
   ```json
   {
     "type": "commits|dates|this-run|permanent",
     "from": "abc123",    // commit SHA or date
     "to": "def456"       // commit SHA or date
   }
   ```
   Default (no `--scope` flag) remains `permanent` for backward compatibility.

2. **`evo accept . 1 --scope commits abc123..def456`** — CLI syntax:
   - `--scope commits SHA..SHA` — suppress for events triggered by these commits
   - `--scope dates YYYY-MM-DD..YYYY-MM-DD` — suppress for events in date range
   - `--scope this-run` — one-time dismiss, expires on next analysis
   - `--scope permanent` — current behavior (default)

3. **Phase 5 filtering enhancement** — `phase5_engine.py` currently does:
   ```python
   changes = [c for c in changes if f"{c['family']}:{c['metric']}" not in self._accepted]
   ```
   Needs to check scope: for commit-scoped acceptances, only suppress if the
   signal's trigger events fall within the accepted commit range.

4. **Report "Accept — Expected" button** — in the HTML report, each finding gets
   a dropdown: "Accept permanently" / "Accept for these commits" / "Accept this time".
   Shows the `evo accept` command to copy.

### Phase F: Fix Loop for External AI Tools

**Goal:** Make the prompt-and-verify loop seamless for users who fix in
Cursor/Copilot/ChatGPT (the primary fix experience).

**Files:** `evolution/fixer.py`, `evolution/cli.py`, `evolution/report_generator.py`

1. **`evo fix --dry-run --residual`** — if a previous advisory exists, generate a
   residual-aware prompt that tells the AI what's already fixed, what's still broken,
   and what not to re-introduce. Currently `--dry-run` always generates the initial
   prompt; this adds iteration awareness.

2. **`evo verify .`** — already exists but needs enhancement:
   - After verification, auto-save `residual_prompt.txt` to `.evo/phase5/`
   - Print copy-friendly output: "Copy this prompt to continue fixing"
   - Show resolution progress: "2 of 3 resolved (67%)"

3. **Report "Fix with AI" button** — in the HTML report:
   - Generates the investigation/fix prompt inline in the report
   - "Copy to clipboard" button (JavaScript)
   - After `evo verify`, the report refreshes to show residual prompt
   - Shows iteration history: what was tried, what worked

4. **Selective fix** — `evo fix . --only 1,3` to generate prompts for specific
   findings by index, not all of them

5. **SARIF output** — `evo analyze . --sarif` for VS Code Problems tab integration

6. **Hook-based loop closure** — when hooks are installed, every commit after a fix
   automatically runs `evo analyze` which acts as `evo verify` if a previous advisory
   exists. The notification shows resolution progress, not just new findings.
   No extra command needed — the commit IS the verify step.

### Phase G: Configuration UX — CLI Setup + Web UI Settings

**Goal:** With 22+ config keys across 7+ groups, the flat `evo config set` / `evo config list`
is no longer sufficient. New users need guided configuration, power users need fast surgical
edits, and everyone benefits from being able to see and change settings visually.

**Two interfaces, one config file:** Both read/write `~/.evo/config.toml`. The source of
truth is always the file. No sync issues, no conflicts.

#### Version 1: `evo setup` — Interactive CLI Configurator

**New file:** `evolution/setup.py`

Interactive, prompt-driven configuration grouped by functional area:

```bash
evo setup                    # Full guided walkthrough
evo setup hooks              # Configure just hooks settings
evo setup analyze            # Configure just analysis settings
evo setup llm                # Configure AI/LLM settings
evo setup notifications      # Configure when/how to alert
```

**Full walkthrough flow:**
```
Evolution Engine — Setup

 1. Analysis       What to analyze, output format
 2. Hooks          Background analysis on commit/push
 3. Notifications  When and how to alert you
 4. AI / LLM       Investigation and fix settings
 5. Patterns       Community sharing and sync
 6. Adapters       Plugin management
 7. Telemetry      Anonymous usage statistics

 Choose area [1-7], or 'all' for full walkthrough:
```

**Per-group walkthrough (example: hooks):**
```
─── Hooks Configuration ───

When should EE run automatically?
  1. After each commit (post-commit)
  2. Before push (pre-push)
  > 1

Notification threshold — when should EE bother you?
  1. Only critical issues     (⚠️ Action Required)
  2. Important findings       (⚠️ + 🔍 Needs Attention)  [recommended]
  3. Everything worth noting  (⚠️ + 🔍 + 👁️)
  4. Everything
  > 2

Open report in browser automatically when findings detected?  [Y/n] Y
Desktop notifications enabled?  [Y/n] Y

✓ Hooks configured. Settings saved to ~/.evo/config.toml
  Run `evo install-hooks .` to activate.
```

**Key design principles:**
- Each question shows the current value and a recommended default
- Validates input (e.g., min_severity must be one of the allowed values)
- Shows what changed at the end ("3 settings updated")
- Groups are self-contained — `evo setup hooks` is a complete experience
- `evo init` calls `evo setup` at the end: "Want to configure preferences? Running setup..."

#### Version 2: `evo setup --ui` — Web-Based Settings Page

**New files:** `evolution/setup_ui.py`, `evolution/templates/setup.html`

A standalone HTML settings page, same pattern as `report_generator.py`:

```bash
evo setup --ui               # Opens settings page in browser
evo setup --ui --port 9876   # Custom port
```

**How it works:**
1. `evo setup --ui` starts a minimal local HTTP server (stdlib `http.server`, no deps)
2. Serves a single-page settings UI at `http://localhost:9847`
3. Opens browser automatically
4. Browser page shows all config groups as expandable cards
5. User changes settings via toggles, dropdowns, inputs
6. Save button POSTs changes back → server writes `~/.evo/config.toml`
7. Server auto-shuts down after 10 minutes idle or on explicit "Done"

**Settings page layout:**
```
┌─────────────────────────────────────────────────────┐
│  Evolution Engine — Settings                    [×] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ▼ Analysis                                         │
│  ┌─────────────────────────────────────────────┐   │
│  │  Families    [auto-detect ▼]                 │   │
│  │  Output      ○ Human  ● JSON                 │   │
│  │  Report      [dark theme ▼]                  │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ▼ Hooks                                            │
│  ┌─────────────────────────────────────────────┐   │
│  │  Trigger     ○ post-commit  ○ pre-push       │   │
│  │  Threshold   [⚠️+🔍 Needs Attention ▼]       │   │
│  │  Auto-open   [✓]   Notify  [✓]              │   │
│  │  Status: ● Installed (post-commit)           │   │
│  │  [Install hooks]  [Remove hooks]             │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ▼ AI / LLM                                        │
│  ┌─────────────────────────────────────────────┐   │
│  │  Enabled     [✓]                             │   │
│  │  Provider    [anthropic ▼]                   │   │
│  │  Model       [claude-sonnet-4-5 ▼]           │   │
│  │  API Key     [••••••••••] (from env)         │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ▶ Patterns        (collapsed)                      │
│  ▶ Adapters        (collapsed)                      │
│  ▶ Telemetry       (collapsed)                      │
│                                                     │
│  License: Pro (expires 2027-02-14)                  │
│  Config: ~/.evo/config.toml                         │
│                                                     │
│              [ Save ]     [ Done ]                  │
└─────────────────────────────────────────────────────┘
```

**Key design principles:**
- Standalone HTML with inline CSS/JS (same as report — no build step)
- Zero external dependencies (Python stdlib http.server)
- Shows current values live from config.toml
- Validates before saving (highlights invalid values)
- Shows hook status, license status, detected adapters inline
- "Done" button stops the server and closes the tab
- Config groups match the CLI `evo setup` groups exactly
- Each setting has a help tooltip explaining what it does
- API keys are never shown in full (masked, detected from env)

#### Improved `evo config list` (for power users)

The existing `evo config list` gets grouped output with descriptions:

```
Evolution Engine Configuration (~/.evo/config.toml)

─── Analysis ───
  analyze.families      = (auto-detect)    Families to analyze
  analyze.json_output   = false            Machine-readable output

─── Hooks ───
  hooks.trigger         = post-commit *    When to run: post-commit | pre-push
  hooks.min_severity    = concern *        Notify threshold
  hooks.auto_open       = true             Open report on findings
  hooks.notify          = true             Desktop notification
  hooks.families        = (auto-detect)    Override families for hooks
  hooks.background      = true             Non-blocking execution

─── AI / LLM ───
  llm.enabled           = false            LLM-enhanced explanations (Pro)
  llm.provider          = anthropic        AI backend
  llm.model             = claude-sonnet-4-5-20250929

─── Patterns & Sync ───
  sync.privacy_level    = 0                Sharing: 0=off 1=metadata 2=patterns
  sync.registry_url     = codequal.dev     Registry endpoint
  sync.auto_pull        = false            Auto-pull on analyze

─── Adapters ───
  adapter.check_blocklist = true           Check blocklist on detect
  adapter.check_updates   = true           Show update reminders

─── Telemetry ───
  telemetry.enabled     = false            Anonymous usage stats

  (* = user override)
  Run `evo setup` for interactive config, or `evo setup --ui` for browser.
```

---

## Task Breakdown

### Milestone 1: Pro Onboarding (Phase A) — "I can see it works"

| # | Task | Effort | Priority |
|---|------|--------|----------|
| 1 | Implement advisory status rollup (action_required/needs_attention/worth_monitoring/all_clear) | Small | **Critical** |
| 2 | Enhanced CLI terminal output — structured summary table with advisory status | Medium | **Critical** |
| 3 | Add interactive buttons to HTML report (Investigate, Fix, IDE, Dismiss, Filter) | Medium | High |
| 4 | Tests for advisory status rollup | Small | High |

### Milestone 2: Automated Hooks (Phase B) — "Just tell me when it matters"

| # | Task | Effort | Priority |
|---|------|--------|----------|
| 5 | Implement `evolution/hooks.py` — install, remove, status, hook script template | Medium | High |
| 6 | Add `evo install-hooks` CLI command | Small | High |
| 7 | Add `hooks.*` config keys to config.py | Small | High |
| 8 | Desktop notification module (macOS + Linux) | Small | Medium |
| 9 | Background analysis runner in hook script | Medium | High |
| 10 | Tests for hooks module | Medium | High |

### Milestone 3: Guided Setup (Phase C) — "Help me choose"

| # | Task | Effort | Priority |
|---|------|--------|----------|
| 11 | Implement `evo init` — interactive setup wizard | Medium | High |
| 12 | GitHub Action workflow YAML template generator | Small | High |
| 13 | First-run hint after `evo analyze` | Small | Medium |
| 14 | Tests for init module | Medium | High |

### Milestone 4: Scoped Acceptance (Phase E) — "This was expected"

| # | Task | Effort | Priority |
|---|------|--------|----------|
| 15 | Enhance accepted.json schema with scope field (commits/dates/this-run/permanent) | Medium | **High** |
| 16 | `evo accept --scope` CLI syntax for commit ranges and date ranges | Medium | **High** |
| 17 | Phase 5 scoped filtering — check commit/date range before suppressing | Medium | **High** |
| 18 | Report "Accept — Expected" button with scope picker | Medium | High |
| 19 | Tests for scoped acceptance | Medium | High |

### Milestone 5: Fix Loop for External AI (Phase F) — "Copy prompt, fix, verify"

| # | Task | Effort | Priority |
|---|------|--------|----------|
| 20 | `evo fix --dry-run --residual` — iteration-aware prompt generation | Medium | **High** |
| 21 | `evo verify` enhancement — auto-save residual_prompt.txt, show progress | Medium | **High** |
| 22 | Report "Fix with AI" button with copy-to-clipboard and residual awareness | Medium | High |
| 23 | Hook-based loop closure — commit acts as verify, notification shows progress | Medium | High |
| 24 | Selective fix (`evo fix --only 1,3`) | Small | Medium |
| 25 | SARIF output for IDE integration | Medium | Medium |

### Milestone 6: Configuration UX (Phase G) — "Show me all the knobs"

| # | Task | Effort | Priority |
|---|------|--------|----------|
| 26 | Config metadata registry — descriptions, types, allowed values per key | Small | **High** |
| 27 | `evo setup` — interactive CLI configurator with per-group walkthrough | Medium | **High** |
| 28 | Improved `evo config list` — grouped display with descriptions | Small | High |
| 29 | `evo setup --ui` — local HTTP server + standalone HTML settings page | Large | High |
| 30 | Settings page: hook status, license info, adapter detection inline | Medium | Medium |
| 31 | Tests for setup CLI and config metadata | Medium | High |

### Milestone 7: Watch & Docs (Phase D)

| # | Task | Effort | Priority |
|---|------|--------|----------|
| 32 | Implement `evo watch` (foreground + daemon) | Medium | Medium |
| 33 | Tests for watcher | Medium | Medium |
| 34 | Update QUICKSTART.md — three-path journey, Pro onboarding | Medium | High |
| 35 | Update README.md — integration paths section | Small | High |
| 36 | Update website — "How It Works" with all integration paths and config | Medium | High |
| 37 | End-to-end test: full journey (analyze → setup → accept/fix → verify → hooks) | Large | High |

---

## Config Keys (New)

```toml
# ~/.evo/config.toml additions

[hooks]
trigger = "post-commit"    # "post-commit" | "pre-push"
auto_open = true           # Open report in browser when threshold met
notify = true              # Desktop notification when threshold met
min_severity = "concern"   # "critical" | "concern" | "watch" | "info"
                           #  ⚠️ only  |  ⚠️ + 🔍   | + 👁️   |  all
families = ""              # Override families for hook runs (empty = auto)
background = true          # Non-blocking hook execution

[init]
integration = ""           # "cli" | "hooks" | "action" | "all" (set by evo init)
first_run_count = 0        # Tracks runs for first-run hints (suppress after 3)
```

---

## Advisory Status Rollup Logic

```python
def advisory_status(advisory: dict) -> dict:
    """Compute overall advisory status from findings."""
    changes = advisory.get("changes", [])
    if not changes:
        return {"level": "all_clear", "icon": "✅", "label": "All Clear"}

    max_deviation = max(abs(c.get("deviation_stddev", 0)) for c in changes)

    if max_deviation >= 4.0:   # Critical or High individual findings
        return {"level": "action_required", "icon": "⚠️", "label": "Action Required"}
    elif max_deviation >= 2.0: # Medium findings
        return {"level": "needs_attention", "icon": "🔍", "label": "Needs Attention"}
    elif max_deviation >= 1.0: # Low findings
        return {"level": "worth_monitoring", "icon": "👁️", "label": "Worth Monitoring"}
    else:
        return {"level": "all_clear", "icon": "✅", "label": "All Clear"}
```

The hook compares `advisory_status.level` against `hooks.min_severity`:
- `critical` → only notify on `action_required`
- `concern` → notify on `action_required` + `needs_attention` (default)
- `watch` → notify on everything except `all_clear`
- `info` → notify on everything (same as manual mode)

---

## User Journey Summary

```
DAY 1 — "Show me everything"
│
│  pip install evolution-engine
│  evo license activate <key>
│  evo analyze .                    ← Full output, always
│  evo report . --open              ← Browse HTML report
│  evo investigate .                ← Try AI features
│  evo fix .                        ← Try fix loop
│
│  User thinks: "OK, this works. I see what it catches."
│
WEEK 1-2 — "Let me tune it"
│
│  evo analyze .                    ← Run several more times
│  evo accept . 3 5                 ← Mark expected things
│  evo history diff                 ← See how findings change
│
│  User thinks: "I trust the severity levels. The Critical/High
│  findings are real. The Medium ones are usually worth looking at."
│
WEEK 2+ — "Just tell me when it matters"
│
│  evo init                         ← Guided setup
│  # Chooses: hooks (local) or GitHub Action (team) or both
│
│  From now on:
│    Commit → [silent analysis] → notification only on ⚠️🔍
│    PR → [action runs] → comment only when findings
│
│  User thinks: "I forgot EE was running. Then it caught a real
│  issue before it hit production. That's worth $19/mo."
```

---

*This plan prioritizes the Pro onboarding experience (Milestone 1) because that's where retention is won or lost. A user who sees the value on Day 1 will stick around long enough to automate.*

---

## Implementation Status

### Completed (30/30 tasks)
All SDLC integration features are implemented and have 1333 automated tests passing.

| Feature | Module | Tests |
|---------|--------|-------|
| Advisory status rollup | `phase5_engine.py` | test_friendly.py |
| Interactive HTML report (filters, buttons, IDE links) | `report_generator.py` | test_report_generator.py |
| Git hook management | `hooks.py` | test_hooks.py (77) |
| Project initialization wizard | `init.py` | test_init.py (35) |
| Commit watcher (foreground + daemon) | `watcher.py` | test_watcher.py (37) |
| Setup CLI wizard | `cli.py` (setup command) | test_setup_cli.py (39) |
| Setup browser UI | `setup_ui.py` | test_setup_ui.py (42) |
| Scoped acceptance (permanent/commits/dates/this-run) | `accepted.py` | test_accepted.py |
| Residual fix prompts | `fixer.py` | test_fixer.py |
| Hook-based loop closure (resolution tracking) | `orchestrator.py`, `hooks.py` | test_hook_loop.py (24) |
| Verify with auto-residual | `cli.py` (verify command) | test_verify_residual.py (12) |
| E2E integration journeys | — | test_sdlc_e2e.py (70) |

### Manual Testing (2026-02-14)

| Area | Status | Bugs Found |
|------|--------|------------|
| `evo init` | PASS | Was non-interactive — fixed (now numbered menu) |
| `evo setup` (CLI wizard) | PASS | — |
| `evo setup --ui` (browser) | Starts OK | Needs manual browser verification |
| `evo hooks install/uninstall/status` | PASS | — |
| `evo watch --daemon/--stop/--status` | PASS | `--stop` showed `PID ?` — fixed |
| `evo analyze + report` | PASS | `--json` without `--quiet` mixes output (pre-existing) |
| `evo accept --scope` | PASS | — |
| `evo fix --dry-run --residual` | PASS | — |
| `evo verify` | PASS | — |
| `evo config` | Not yet tested | — |
| `evo patterns` | Not yet tested | — |
| `evo sources/status/history` | Not yet tested | — |

### Open Items

| # | Issue | Priority | Status |
|---|-------|----------|--------|
| 1 | **Installation guidance incomplete** — docs say `pip install evolution-engine` but don't mention venv setup, Python version requirement (>=3.10), or PATH activation. Users who run `pip install` in a venv won't have `evo` on PATH without `source .venv/bin/activate`. Need to document: venv creation, activation, `pipx` alternative, from-source install. | HIGH | TODO |
| 2 | **`evo setup` wizard not documented** — neither the CLI wizard nor the `--ui` browser mode are explained in QUICKSTART.md, README.md, or website/docs.html. Need: walkthrough of wizard flow (Enter/s/q navigation), example output, config groups, how CLI and UI share config. | MEDIUM | TODO |
| 3 | **`--json` mixes progress output** — `evo analyze . --json` prints human-readable progress before the JSON. Works with `--json --quiet` but `--json` alone should probably suppress progress. | LOW | Pre-existing |
| 4 | **"No events" error unclear** — when run outside a git repo, message says "No events ingested. Check that the repo has git history." Should detect missing `.git` and say "No .git directory found." | LOW | TODO |
| 5 | **`evo setup --ui` needs browser testing** — server starts and binds, but couldn't verify from sandbox. Needs manual test on real machine. | MEDIUM | TODO |
| 6 | **Guided user walkthrough** — need to complete manual walkthrough of all 21 steps on a real repo (codequal). Transition doc at `memory/session-2026-02-14-manual-testing.md`. | HIGH | In progress |

*Last updated: 2026-02-14*
