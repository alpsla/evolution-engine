# AI Safety Audit — Evolution Engine

**Date:** 2026-02-11
**Scope:** All components that involve AI-generated actions, code modifications, or external write operations.
**Auditor:** Automated code audit via Claude Opus 4.6

---

## Executive Summary

Evolution Engine (EE) has a generally conservative safety posture. The analysis pipeline (Phases 1-5) is strictly read-only. The AI investigation system (`evo investigate`) is text-only and never modifies source code. The fix system (`evo fix`) **does modify files without per-change user confirmation**, but operates on a dedicated git branch and requires the user to explicitly invoke the command. The GitHub Action never pushes commits or merges code — it only posts comments and review suggestions.

**Key finding:** The `evo fix` command applies AI-generated code changes to the working tree without prompting the user to review each individual change before it is written. The user must explicitly invoke `evo fix`, and changes land on a new branch, but there is no interactive approval step between the AI producing a fix and the fix being applied to files.

---

## Component-by-Component Audit

### 1. `evolution/investigator.py` — AI Investigation

**What the AI can do:**
- Reads Phase 5 advisory data from `.evo/phase5/advisory.json` (read-only).
- Sends advisory context to an AI agent and receives a text response.
- Saves the investigation report to `.evo/investigation/investigation.json` and `.evo/investigation/investigation.txt`.

**Does it modify source code?** No. It only writes report files into the `.evo/` metadata directory. It never touches repository source files.

**User confirmation required?** The user must explicitly run `evo investigate`. No further confirmation is needed because no source code is modified.

**Auto-apply behavior:** None. This is a pure analysis component.

**Risk level:** LOW

---

### 2. `evolution/fixer.py` — RALF Fix-Verify Loop

**What the AI can do:**
- Creates a new git branch (`evo/fix-<timestamp>` or user-specified name) via `git checkout -b`.
- Delegates to an AI agent's `complete_with_files()` method, which can modify any file in the repository working tree.
- Re-runs the full EE pipeline (`Orchestrator.run()`) to verify whether fixes resolved the flagged issues.
- Iterates up to `max_iterations` (default 3) times, applying additional fixes if issues persist.

**Does it modify source code?** YES. When the `CliAgent` is used, it invokes the `claude` CLI in the repository directory with full file-editing capability. The AI agent can create, modify, or delete any file within the repository.

**User confirmation required?**
- The user must explicitly run `evo fix` to start the process.
- A `--dry-run` flag is available that shows the fix prompt without modifying files.
- **HOWEVER:** Once `evo fix` is invoked (without `--dry-run`), there is NO interactive confirmation before each file modification. The AI agent applies changes directly.
- There is no diff review step between iterations.
- There is no "accept/reject" prompt after the AI produces its changes.

**Safety mitigations already in place:**
- Changes are made on a new git branch, never on the current branch directly. The user must manually merge the branch.
- The `can_edit_files` property gates which agents are allowed to make modifications (only `CliAgent` returns `True`).
- If the agent does not support file editing, the fixer returns an error with a helpful message rather than silently failing.
- Max iteration cap (default 3) prevents infinite loops.
- No-progress detection stops the loop if fix attempts are not reducing issues.
- No `git push` is ever executed — changes remain local.
- No `git commit` is executed by the fixer itself (the CLI agent may or may not commit depending on its behavior).

**Auto-apply behavior:** YES — this is the primary concern. The RALF loop applies AI changes directly to files without per-change user approval.

**Risk level:** MEDIUM

**Recommendations:**
1. Add an optional `--confirm` / `--interactive` flag that shows a diff after each iteration and prompts the user to continue, skip, or abort.
2. Consider logging all files modified by the agent to `.evo/fix/modified_files.txt` for post-hoc review.
3. Document clearly in CLI help text that `evo fix` will modify files on a branch without per-change prompts.

---

### 3. `evolution/agents/` — AI Agent Backends

#### 3a. `AnthropicAgent` (`evolution/agents/anthropic_agent.py`)

**What it can do:** Send text prompts to the Anthropic API and receive text responses. It is a pure text-completion agent.

**Can it edit files?** No. `can_edit_files` is `False` (inherited default from `BaseAgent`). Its `complete_with_files()` falls back to `complete()`, which only returns text. If the fixer selects this agent, it is explicitly rejected at line 199 of `fixer.py` with an error message.

**Risk level:** LOW

#### 3b. `CliAgent` (`evolution/agents/cli_agent.py`)

**What it can do:**
- Invoke an external CLI tool (default: `claude`) as a subprocess.
- Pass prompts via `--prompt` argument.
- Run in a specified `working_dir` (the repository root), where the subprocess has full read/write access to the filesystem.
- Uses `--print --output-format text` flags for non-interactive mode.

**Can it edit files?** YES. `can_edit_files` returns `True`. The `complete_with_files()` method runs the CLI tool with `cwd` set to the repo directory. The external tool (e.g., Claude Code CLI) has the same filesystem permissions as the user running the command.

**User confirmation required?** Depends on the underlying CLI tool. The `claude --print` flag runs in non-interactive mode, meaning Claude Code will apply changes without its own interactive confirmation prompts. The EE code does not add any confirmation layer on top.

**Risk level:** MEDIUM — This is the agent that enables the fixer to actually modify files. The security boundary is entirely delegated to the external CLI tool.

**Recommendations:**
1. Document that `--print` mode in Claude Code bypasses interactive confirmation.
2. Consider adding a wrapper that captures the list of files changed by the subprocess.

#### 3c. `ShowPromptAgent` (`evolution/agents/base.py`)

**What it can do:** Returns the prompt text as-is for the user to manually paste into any AI tool.

**Can it edit files?** No. It is a pure pass-through.

**Risk level:** NONE

---

### 4. `evolution/inline_suggestions.py` — PR Inline Review Comments

**What the AI can do:**
- Parse investigation report text to extract file references and suggested fixes.
- Format these as GitHub Pull Request Review comment payloads.

**Does it create commits?** No. It produces a JSON payload with `"event": "COMMENT"` (line 125). This means GitHub treats it as a comment-only review, not an approval or request-for-changes. The payload is a data structure — the actual GitHub API call is made by the GitHub Action shell step, not by this module.

**Does it modify source code?** No. It only reads investigation and advisory data and produces structured output.

**Does it push code?** No.

**User confirmation required?** The user must opt in by setting `suggest-fixes: 'true'` in the GitHub Action inputs. The suggestions appear as PR review comments that the developer must manually accept/apply via GitHub's UI.

**Risk level:** LOW — Suggestions are posted as review comments, not applied directly.

---

### 5. `evolution/pr_comment.py` — PR Comment Formatting

**What it can do:**
- Format Phase 5 advisory data as markdown for GitHub PR comments.
- Format verification results as markdown.

**Does it have write access to GitHub?** No. This module is a pure formatter. It takes data in, returns a markdown string. The actual posting to GitHub is done by the GitHub Action's shell step using `gh pr comment` or `gh api`.

**Does it modify source code?** No.

**Risk level:** NONE

---

### 6. `action/action.yml` — GitHub Action

**What the Action can do:**
1. Install Evolution Engine and run `evo analyze` (read-only analysis).
2. Run `evo investigate` with the Anthropic API (text-only investigation, no file edits).
3. Post a PR comment with analysis results via `gh pr comment` or `gh api PATCH`.
4. Post inline fix suggestions as a PR review via `gh api POST .../reviews`.
5. Run `evo verify` on subsequent pushes to compare against previous advisory.
6. Save current advisory as `.prev` for future comparison.

**Does it push commits?** No. There is no `git push`, `git commit`, or any write operation to the git history anywhere in the action. Confirmed by searching for `git push`, `git commit`, `auto-merge`, `auto-apply`, and `force-push` patterns — none found.

**Does it merge PRs?** No.

**Does it approve PRs?** No. The review payload uses `"event": "COMMENT"`, not `"APPROVE"`.

**Write operations performed:**
- Creates/updates PR comments (informational only).
- Posts review comments with fix suggestions (developers must manually apply via GitHub's suggestion UI).
- Writes temporary files to `.evo/` directory within the CI workspace.

**User confirmation required?**
- The action only runs if explicitly included in a workflow file.
- `comment: 'true'` is the default — PR comments are opt-out.
- `investigate: 'false'` is the default — AI investigation is opt-in.
- `suggest-fixes: 'false'` is the default — inline suggestions are opt-in.

**Risk level:** LOW

---

### 7. `evolution/cli.py` — CLI Commands

#### `evo investigate`

**User interaction model:** The user explicitly runs the command. They can use `--show-prompt` to preview the prompt without making an AI call. The investigation result is printed to stdout and saved to `.evo/investigation/`. No source files are modified.

**Risk level:** LOW

#### `evo fix`

**User interaction model:**
- The user explicitly runs `evo fix`.
- `--dry-run` previews the fix prompt without modifying files.
- Without `--dry-run`, the fixer creates a branch and applies AI changes immediately.
- There is **no interactive confirmation prompt** between "start" and "files modified."
- After completion, results are printed showing resolved/remaining counts per iteration.
- Results are saved to `.evo/fix/fix_result.json`.

**Risk level:** MEDIUM — The gap between "user invokes command" and "files are changed" has no confirmation step.

**Recommendations:**
1. Add a confirmation prompt after showing what the AI intends to do but before applying changes.
2. Show a summary diff after each iteration and ask whether to continue.
3. At minimum, print a warning banner like: "This will modify files on branch 'evo/fix-...'. Continue? [y/N]"

#### `evo analyze`

**User interaction model:** Pure read-only analysis. Writes only to `.evo/` metadata directory. No source code modification.

**Risk level:** NONE

---

### 8. `evolution/orchestrator.py` — Pipeline Orchestration

**What it does:**
- Runs the 5-phase pipeline: event ingestion, baseline computation, explanation generation, pattern discovery, and advisory generation.
- All output is written to the `.evo/` metadata directory.
- Imports bundled universal patterns into the local knowledge base.

**Does it modify source code?** No. It reads git history and API data, computes statistics, and writes results to `.evo/`.

**Auto-apply behavior:** None. The orchestrator is called by the fixer's `_verify()` method to re-run analysis after fixes, but it does not apply any changes itself.

**Risk level:** NONE

---

## Summary Matrix

| Component | Reads Code | Modifies Code | Writes to GitHub | User Must Invoke | Per-Change Confirmation | Risk |
|-----------|:----------:|:-------------:|:----------------:|:----------------:|:----------------------:|:----:|
| `investigator.py` | Yes (advisory) | No | No | Yes | N/A | LOW |
| `fixer.py` | Yes | **YES** | No | Yes | **No** | MEDIUM |
| `AnthropicAgent` | No | No | No | Yes | N/A | LOW |
| `CliAgent` | No | **YES** | No | Yes | **No** | MEDIUM |
| `ShowPromptAgent` | No | No | No | Yes | N/A | NONE |
| `inline_suggestions.py` | Yes (advisory) | No | No | N/A (library) | N/A | LOW |
| `pr_comment.py` | Yes (advisory) | No | No | N/A (library) | N/A | NONE |
| `action.yml` | Yes | No | **Yes** (comments) | Yes (workflow) | N/A | LOW |
| `cli.py` (`investigate`) | Yes | No | No | Yes | N/A | LOW |
| `cli.py` (`fix`) | Yes | **YES** | No | Yes | **No** | MEDIUM |
| `orchestrator.py` | Yes | No | No | Yes | N/A | NONE |

---

## Findings Requiring Attention

### Finding 1: `evo fix` applies changes without per-change confirmation

**Severity:** Medium
**Location:** `evolution/fixer.py` lines 239-264, `evolution/cli.py` lines 179-253

Once the user runs `evo fix` (without `--dry-run`), the system:
1. Creates a new git branch (no confirmation).
2. Sends a prompt to the CLI agent (no confirmation).
3. The CLI agent modifies files in the repository (no confirmation).
4. Re-runs the EE pipeline to verify (no confirmation).
5. If issues remain, repeats steps 2-4 up to `max_iterations` times (no confirmation between iterations).

The user has no opportunity to review changes between any of these steps.

**Mitigating factors:**
- Changes are on a dedicated branch, not the user's working branch.
- No `git push` occurs — changes stay local.
- The user explicitly opted in by running `evo fix`.
- `--dry-run` is available for preview.

**Recommendation:** Add an optional `--interactive` flag (or make it the default) that pauses after each iteration to show a diff and ask whether to continue. Example:

```
Iteration 1 complete. Files changed:
  M src/config.py (+3, -1)
  M tests/test_config.py (+12, -0)

Continue to verification? [Y/n]:
```

### Finding 2: CliAgent delegates all safety to the external tool

**Severity:** Low-Medium
**Location:** `evolution/agents/cli_agent.py` lines 47-54

The `CliAgent` runs the external CLI tool with `cwd` set to the repository root. The `--print` flag means Claude Code runs in non-interactive mode. EE does not inspect, validate, or constrain what the external tool does.

**Mitigating factors:**
- The external tool (Claude Code) has its own safety mechanisms.
- The tool runs with the user's own filesystem permissions (no privilege escalation).
- Only invoked when the user explicitly runs `evo fix`.

**Recommendation:** Consider capturing the list of files modified by the subprocess (e.g., by comparing `git status` before and after) and logging them for auditability.

### Finding 3: GitHub Action posts comments with `github.token` permissions

**Severity:** Low
**Location:** `action/action.yml` lines 111-188

The action uses the default `github.token` to post PR comments and review suggestions. This is standard GitHub Action behavior and the token has appropriate scoped permissions. However, the action could theoretically update any existing EE comment on the PR (it searches for comments starting with "## Evolution Engine" and patches them).

**Mitigating factors:**
- The token is the standard `GITHUB_TOKEN` with repository-scoped permissions.
- Only PR comments and review comments are written — no code changes, merges, or approvals.
- The review event is `COMMENT`, not `APPROVE` or `REQUEST_CHANGES`.

**Recommendation:** No changes needed. This is standard CI behavior.

---

## What the AI System CANNOT Do

For completeness, the following actions are explicitly NOT possible through EE's AI system:

1. **Push to remote repositories** — No `git push` command exists anywhere in the codebase.
2. **Merge pull requests** — No merge API calls or `git merge` commands to main/default branches.
3. **Approve pull requests** — Review events are `COMMENT` only.
4. **Modify files outside the repository** — The CLI agent's `cwd` is set to the repo root; no absolute paths are used.
5. **Run arbitrary shell commands** — The fixer only invokes the configured CLI tool with a fixed argument pattern (`--print --output-format text --prompt ...`).
6. **Access secrets or credentials** — The AI agents receive only advisory/investigation text, not tokens or API keys.
7. **Auto-run on schedule** — All AI features require explicit user invocation (CLI) or opt-in configuration (GitHub Action).

---

## Recommendations Summary

| Priority | Recommendation | Affected Component |
|----------|---------------|-------------------|
| 1 | Add `--interactive` flag to `evo fix` with diff review between iterations | `fixer.py`, `cli.py` |
| 2 | Log all files modified by the fix agent to `.evo/fix/` for auditability | `fixer.py` |
| 3 | Print a confirmation prompt before the first fix iteration begins | `cli.py` (`fix` command) |
| 4 | Capture pre/post `git diff` around agent invocations | `fixer.py` |
| 5 | Document that `--dry-run` should be used for first-time users | CLI help text, README |

---

## Conclusion

Evolution Engine's AI system has a conservative design overall. The read-only analysis pipeline, the branch-based fix isolation, and the comment-only GitHub Action all demonstrate reasonable safety practices. The primary gap is the lack of per-change or per-iteration confirmation in the `evo fix` flow. Adding an interactive mode would close this gap and bring the system in line with best practices for AI-assisted code modification tools.

No evidence was found of auto-apply behavior that bypasses user intent. Every AI action requires the user to explicitly invoke a command or configure a GitHub Action workflow. The AI never acts autonomously.
