"""
Fixer — AI agent applies fixes, EE validates, iterates until clear.

The RALF-style loop:
  1. Read investigation report (or advisory if no investigation)
  2. AI agent applies targeted fixes on a branch
  3. EE re-analyzes (evo verify)
  4. Compare: all clear? → done. Residual issues? → back to step 2.

Termination conditions:
  - All advisory items resolved (ideal)
  - Max iterations reached (default 3)
  - No progress (same advisory after fix → stop to avoid infinite loop)

Residual mode (dry_run + residual):
  When used with --residual, generates an iteration-aware prompt for external
  AI tools (Cursor, Copilot, etc.) that shows what was already fixed vs. what's
  still broken, so the external tool can build on previous progress.

Usage:
    fixer = Fixer(repo_path=".", evo_dir=".evo")
    result = fixer.run()
    result = fixer.run(dry_run=True)
    result = fixer.run(dry_run=True, residual=True)
    result = fixer.run(max_iterations=5)
"""

import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from evolution.agents.base import BaseAgent, get_agent

logger = logging.getLogger(__name__)

FIX_SYSTEM_PROMPT = """\
You are a senior software engineer reviewing development drift detected by \
Evolution Engine. EE monitors SDLC signals (git patterns, CI, dependencies, \
deployments) and flags when development patterns shift from established baselines.

Your job is to assess whether a flagged drift was intentional and, if not, \
course-correct the codebase back on track.

Rules:
1. Check the breakpoint commit(s) — was this change intentional?
2. If intentional (new feature, deliberate refactor), leave it alone.
3. If unintentional (AI tool drift, accidental complexity), apply a minimal \
   course correction.
4. Do NOT rewrite or refactor unrelated code.
5. Do NOT add new features, tests, or documentation unless needed.
6. If a finding is marked "expected" or "accepted", skip it entirely.
7. Briefly describe your assessment: intentional vs. unintentional, and what \
   you changed (if anything).
"""

FIX_PROMPT_TEMPLATE = """\
Evolution Engine detected a shift in development patterns for this repository. \
Review the investigation below and determine if the drift was intentional.

{investigation_text}

{residual_context}

For each finding, assess:
1. Which commit introduced the change (check the breakpoint commit)
2. Whether the shift was intentional (new feature, planned refactor) or \
   unintentional (AI drift, accidental complexity growth)
3. If unintentional, apply a minimal course correction

Do NOT modify findings that are expected or accepted.
"""

RESIDUAL_PROMPT_TEMPLATE = """\
This is an ITERATION of a course-correction loop. A previous attempt was made.

## Already Resolved (DO NOT re-introduce)
{resolved_section}

## Still Drifting (FOCUS HERE)
{persisting_section}

## Previous Changes
{previous_changes}

## Original Investigation
{investigation_text}

Focus ONLY on the "Still Drifting" items above. The previous correction partially \
worked — build on those changes, don't undo them.
"""


def compare_advisories(current: dict, previous: dict) -> dict:
    """Compare two advisory dicts and classify each finding.

    Matching is by (family, metric) tuple from the changes list.

    Args:
        current: The current (newer) advisory dict.
        previous: The previous (older) advisory dict.

    Returns:
        Dict with resolved, persisting, new, and regressions lists.
        Each list contains dicts with at minimum {family, metric}.
    """
    prev_by_key = {}
    for c in previous.get("changes", []):
        key = (c["family"], c["metric"])
        prev_by_key[key] = c

    curr_by_key = {}
    for c in current.get("changes", []):
        key = (c["family"], c["metric"])
        curr_by_key[key] = c

    prev_keys = set(prev_by_key.keys())
    curr_keys = set(curr_by_key.keys())

    resolved = []
    for key in sorted(prev_keys - curr_keys):
        item = prev_by_key[key]
        resolved.append({
            "family": key[0],
            "metric": key[1],
            "was_deviation": item.get("deviation_stddev", 0),
        })

    persisting = []
    for key in sorted(prev_keys & curr_keys):
        prev_item = prev_by_key[key]
        curr_item = curr_by_key[key]
        prev_dev = abs(prev_item.get("deviation_stddev", 0))
        curr_dev = abs(curr_item.get("deviation_stddev", 0))
        persisting.append({
            "family": key[0],
            "metric": key[1],
            "was_deviation": prev_item.get("deviation_stddev", 0),
            "now_deviation": curr_item.get("deviation_stddev", 0),
            "improved": curr_dev < prev_dev,
        })

    new = []
    regressions = []
    prev_families = {k[0] for k in prev_keys}
    for key in sorted(curr_keys - prev_keys):
        curr_item = curr_by_key[key]
        entry = {
            "family": key[0],
            "metric": key[1],
            "deviation": curr_item.get("deviation_stddev", 0),
        }
        # A new finding in a family that previously had issues is a regression
        if key[0] in prev_families:
            regressions.append(entry)
        else:
            new.append(entry)

    return {
        "resolved": resolved,
        "persisting": persisting,
        "new": new,
        "regressions": regressions,
    }


class FixIteration:
    """Result of a single fix iteration."""

    def __init__(
        self,
        iteration: int,
        agent_response: str,
        verification: Optional[dict] = None,
        resolved: int = 0,
        persisting: int = 0,
        new_issues: int = 0,
        regressions: int = 0,
        modified_files: Optional[list[str]] = None,
        diff_before: Optional[str] = None,
        diff_after: Optional[str] = None,
    ):
        self.iteration = iteration
        self.agent_response = agent_response
        self.verification = verification
        self.resolved = resolved
        self.persisting = persisting
        self.new_issues = new_issues
        self.regressions = regressions
        self.modified_files = modified_files or []
        self.diff_before = diff_before or ""
        self.diff_after = diff_after or ""

    @property
    def all_clear(self) -> bool:
        return self.persisting == 0 and self.new_issues == 0 and self.regressions == 0

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "resolved": self.resolved,
            "persisting": self.persisting,
            "new_issues": self.new_issues,
            "regressions": self.regressions,
            "all_clear": self.all_clear,
            "agent_response_length": len(self.agent_response),
            "modified_files": self.modified_files,
            "diff_before": self.diff_before,
            "diff_after": self.diff_after,
        }


class FixResult:
    """Complete result of the fix loop."""

    def __init__(
        self,
        status: str,
        iterations: list[FixIteration],
        branch: Optional[str] = None,
        total_resolved: int = 0,
        total_remaining: int = 0,
        dry_run: bool = False,
    ):
        self.status = status  # "all_clear", "partial", "no_progress", "max_iterations", "error"
        self.iterations = iterations
        self.branch = branch
        self.total_resolved = total_resolved
        self.total_remaining = total_remaining
        self.dry_run = dry_run
        self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "branch": self.branch,
            "total_resolved": self.total_resolved,
            "total_remaining": self.total_remaining,
            "iterations_count": len(self.iterations),
            "iterations": [it.to_dict() for it in self.iterations],
            "dry_run": self.dry_run,
            "generated_at": self.generated_at,
        }


class Fixer:
    """Apply AI fixes and validate with EE in a loop.

    Args:
        repo_path: Path to the git repository.
        evo_dir: Path to the .evo directory.
    """

    def __init__(self, repo_path: str | Path, evo_dir: str | Path = None):
        self.repo_path = Path(repo_path).resolve()
        self.evo_dir = Path(evo_dir).resolve() if evo_dir else self.repo_path / ".evo"

    def run(
        self,
        agent: BaseAgent = None,
        max_iterations: int = 3,
        dry_run: bool = False,
        residual: bool = False,
        branch_name: str = None,
        scope: str = None,
        interactive_callback: Optional[Callable[[FixIteration], bool]] = None,
    ) -> FixResult:
        """Execute the fix-verify loop.

        Args:
            agent: AI agent for applying fixes (auto-detected if None).
            max_iterations: Max fix attempts before stopping (default 3).
            dry_run: If True, show what would be fixed without modifying files.
            residual: If True (with dry_run), generate an iteration-aware prompt
                that compares current advisory with previous advisory to show
                what's fixed, what's still broken, and previous fix context.
            branch_name: Git branch name for fixes (default: evo/fix-<timestamp>).
            scope: Pipeline scope name (default: repo directory name).
            interactive_callback: If provided, called after each iteration with
                the FixIteration result. Should return True to continue or False
                to abort. Used by --interactive mode in the CLI.

        Returns:
            FixResult with loop status and iteration details.
        """
        scope = scope or self.repo_path.name

        # Load investigation (or build from advisory)
        investigation_text = self._load_investigation()
        if not investigation_text:
            return FixResult(
                status="error",
                iterations=[],
                dry_run=dry_run,
            )

        # Dry run with residual mode: compare current vs previous advisory
        if dry_run and residual:
            result = self._run_residual_dry_run(investigation_text)
            if result is not None:
                return result
            # Fall through to normal dry_run if no previous advisory
            logger.info("No previous advisory found, falling back to normal dry_run.")

        # Dry run: just show the fix prompt
        if dry_run:
            prompt = FIX_PROMPT_TEMPLATE.format(
                investigation_text=investigation_text,
                residual_context="",
            )
            return FixResult(
                status="dry_run",
                iterations=[FixIteration(
                    iteration=0,
                    agent_response=f"--- FIX PROMPT (dry run) ---\n\n"
                                   f"--- SYSTEM ---\n{FIX_SYSTEM_PROMPT}\n\n"
                                   f"--- PROMPT ---\n{prompt}",
                )],
                dry_run=True,
            )

        # Get agent
        if agent is None:
            agent = get_agent(prefer="cli")  # file-editing agent preferred

        if not agent.can_edit_files:
            logger.warning(
                "Agent '%s' cannot edit files. Use a CLI agent or --dry-run.",
                agent.name,
            )
            return FixResult(
                status="error",
                iterations=[FixIteration(
                    iteration=0,
                    agent_response=f"Agent '{agent.name}' cannot edit files. "
                                   f"Use `evo fix --agent cli` or install Claude Code CLI.",
                )],
            )

        # Create fix branch
        branch = branch_name or f"evo/fix-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        if not self._create_branch(branch):
            return FixResult(
                status="error",
                iterations=[],
                branch=branch,
            )

        # Save the pre-fix advisory path for verification
        pre_fix_advisory = self.evo_dir / "phase5" / "advisory.json"
        if not pre_fix_advisory.exists():
            return FixResult(
                status="error",
                iterations=[FixIteration(
                    iteration=0,
                    agent_response="No advisory found. Run `evo analyze` first.",
                )],
                branch=branch,
            )

        # ── Fix-Verify Loop ──
        iterations = []
        previous_remaining = None
        residual_context = ""

        for i in range(1, max_iterations + 1):
            logger.info("Fix iteration %d/%d", i, max_iterations)

            # Build fix prompt
            prompt = FIX_PROMPT_TEMPLATE.format(
                investigation_text=investigation_text,
                residual_context=residual_context,
            )

            # Capture pre-agent diff state
            diff_before = self._capture_git_diff_stat()

            # Ask agent to apply fixes
            result = agent.complete_with_files(
                prompt=prompt,
                working_dir=str(self.repo_path),
                system=FIX_SYSTEM_PROMPT,
            )

            # Capture post-agent diff state
            diff_after = self._capture_git_diff_stat()

            # Collect modified files
            modified_files = self._get_modified_files()

            if modified_files:
                import click
                click.echo(f"\n  Modified files (iteration {i}):")
                for f in modified_files:
                    click.echo(f"    - {f}")
            else:
                import click
                click.echo(f"\n  No files modified in iteration {i}.")

            if diff_before or diff_after:
                logger.info("Diff before agent (iteration %d):\n%s", i, diff_before)
                logger.info("Diff after agent (iteration %d):\n%s", i, diff_after)

            if not result.success:
                iterations.append(FixIteration(
                    iteration=i,
                    agent_response=result.error or "Agent failed",
                    modified_files=modified_files,
                    diff_before=diff_before,
                    diff_after=diff_after,
                ))
                return FixResult(
                    status="error",
                    iterations=iterations,
                    branch=branch,
                )

            # Run verification
            verification = self._verify(str(pre_fix_advisory), scope)

            if verification is None:
                iterations.append(FixIteration(
                    iteration=i,
                    agent_response=result.text,
                    modified_files=modified_files,
                    diff_before=diff_before,
                    diff_after=diff_after,
                ))
                return FixResult(
                    status="error",
                    iterations=iterations,
                    branch=branch,
                )

            summary = verification.get("verification", {}).get("summary", {})
            resolved = summary.get("resolved", 0)
            persisting = summary.get("persisting", 0)
            new_issues = summary.get("new", 0)
            regressions = summary.get("regressions", 0)
            remaining = persisting + new_issues + regressions

            iteration = FixIteration(
                iteration=i,
                agent_response=result.text,
                verification=verification.get("verification"),
                resolved=resolved,
                persisting=persisting,
                new_issues=new_issues,
                regressions=regressions,
                modified_files=modified_files,
                diff_before=diff_before,
                diff_after=diff_after,
            )
            iterations.append(iteration)

            logger.info(
                "Iteration %d: resolved=%d, persisting=%d, new=%d, regressions=%d",
                i, resolved, persisting, new_issues, regressions,
            )

            # Interactive mode: let the caller review and decide
            if interactive_callback is not None:
                should_continue = interactive_callback(iteration)
                if not should_continue:
                    logger.info("User aborted fix loop after iteration %d.", i)
                    return FixResult(
                        status="aborted",
                        iterations=iterations,
                        branch=branch,
                        total_resolved=resolved,
                        total_remaining=remaining,
                    )

            # Check termination conditions
            if iteration.all_clear:
                return FixResult(
                    status="all_clear",
                    iterations=iterations,
                    branch=branch,
                    total_resolved=resolved,
                    total_remaining=0,
                )

            # No progress check
            if previous_remaining is not None and remaining >= previous_remaining:
                logger.info("No progress detected (remaining: %d → %d). Stopping.", previous_remaining, remaining)
                return FixResult(
                    status="no_progress",
                    iterations=iterations,
                    branch=branch,
                    total_resolved=resolved,
                    total_remaining=remaining,
                )

            previous_remaining = remaining

            # Build residual context for next iteration
            residual_context = self._format_residual(verification)

        # Max iterations reached
        total_resolved = sum(it.resolved for it in iterations)
        last = iterations[-1] if iterations else None
        total_remaining = (last.persisting + last.new_issues + last.regressions) if last else 0

        return FixResult(
            status="max_iterations",
            iterations=iterations,
            branch=branch,
            total_resolved=total_resolved,
            total_remaining=total_remaining,
        )

    def _capture_git_diff_stat(self) -> str:
        """Capture `git diff --stat` output for audit trail."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return proc.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Failed to capture git diff --stat: %s", e)
            return ""

    def _get_modified_files(self) -> list[str]:
        """Get list of files modified in the working tree (staged + unstaged)."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            files = [f for f in proc.stdout.strip().split("\n") if f]
            return files
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Failed to get modified files: %s", e)
            return []

    def _load_investigation(self) -> Optional[str]:
        """Load investigation report text, falling back to advisory prompt."""
        # Try investigation report first
        inv_path = self.evo_dir / "investigation" / "investigation.txt"
        if inv_path.exists():
            return inv_path.read_text()

        # Fall back to investigation prompt from Phase 5
        prompt_path = self.evo_dir / "phase5" / "investigation_prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text()

        logger.error("No investigation report or advisory found in %s", self.evo_dir)
        return None

    def _create_branch(self, branch_name: str) -> bool:
        """Create and checkout a new git branch."""
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Created branch: %s", branch_name)
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Failed to create branch: %s", e.stderr)
            return False

    def _verify(self, previous_advisory_path: str, scope: str) -> Optional[dict]:
        """Run evo verify to compare current state against pre-fix advisory."""
        try:
            from evolution.orchestrator import Orchestrator

            # Re-run the full pipeline
            orch = Orchestrator(
                repo_path=str(self.repo_path),
                evo_dir=str(self.evo_dir),
            )
            orch.run(scope=scope, quiet=True)

            # Now run verification
            from evolution.phase5_engine import Phase5Engine
            phase5 = Phase5Engine(self.evo_dir)
            result = phase5.verify(
                scope=scope,
                previous_advisory_path=previous_advisory_path,
            )
            return result

        except Exception as e:
            logger.error("Verification failed: %s", e)
            return None

    @staticmethod
    def _format_residual(verification: dict) -> str:
        """Format residual findings for the next iteration's context."""
        v = verification.get("verification", {})
        lines = ["RESIDUAL FINDINGS (from previous fix attempt):"]

        persisting = v.get("persisting", [])
        if persisting:
            lines.append("\nSTILL FLAGGED:")
            for item in persisting:
                improved = "improving" if item.get("improved") else "not improving"
                lines.append(
                    f"  - {item['family']} / {item['metric']}: "
                    f"deviation {item.get('after_deviation', '?')} ({improved})"
                )

        new = v.get("new", [])
        if new:
            lines.append("\nNEW ISSUES (introduced by previous fix):")
            for item in new:
                lines.append(
                    f"  - {item['family']} / {item['metric']}: "
                    f"deviation {item.get('deviation', '?')}"
                )

        regressions = v.get("regressions", [])
        if regressions:
            lines.append("\nREGRESSIONS:")
            for item in regressions:
                lines.append(
                    f"  - {item['family']} / {item['metric']}: "
                    f"deviation {item.get('deviation', '?')} (was normal before fix)"
                )

        resolved = v.get("resolved", [])
        if resolved:
            lines.append(f"\nALREADY RESOLVED: {len(resolved)} item(s) — do NOT re-introduce them.")

        lines.append("\nFocus on the STILL FLAGGED and NEW ISSUES above. "
                      "The previous fix attempt partially worked — build on it.")

        return "\n".join(lines)

    # ── Residual mode helpers ──

    @staticmethod
    def _load_advisory(path: Path) -> Optional[dict]:
        """Load and parse an advisory JSON file.

        Args:
            path: Path to the advisory JSON file.

        Returns:
            Parsed advisory dict, or None if file doesn't exist or is invalid.
        """
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load advisory from %s: %s", path, e)
            return None

    def save_previous_advisory(self) -> bool:
        """Copy current advisory.json to advisory_previous.json.

        Called by `evo verify` (or externally) to snapshot the pre-fix advisory
        so that residual mode can compare against it later.

        Returns:
            True if the copy was made, False if no current advisory exists.
        """
        current = self.evo_dir / "phase5" / "advisory.json"
        previous = self.evo_dir / "phase5" / "advisory_previous.json"
        if not current.exists():
            logger.warning("No current advisory to save as previous.")
            return False
        try:
            shutil.copy2(str(current), str(previous))
            logger.info("Saved previous advisory: %s", previous)
            return True
        except OSError as e:
            logger.error("Failed to save previous advisory: %s", e)
            return False

    def _run_residual_dry_run(self, investigation_text: str) -> Optional[FixResult]:
        """Build a residual-aware dry-run prompt comparing current vs previous advisory.

        Returns a FixResult with status "dry_run_residual", or None if no previous
        advisory is available (caller should fall back to normal dry_run).
        """
        current_path = self.evo_dir / "phase5" / "advisory.json"
        previous_path = self.evo_dir / "phase5" / "advisory_previous.json"

        current_advisory = self._load_advisory(current_path)
        previous_advisory = self._load_advisory(previous_path)

        if current_advisory is None or previous_advisory is None:
            return None

        prompt = self._build_residual_prompt(
            current_advisory, previous_advisory, investigation_text,
        )

        # Count resolved/persisting/new for metadata
        current_keys = {
            (c["family"], c["metric"]) for c in current_advisory.get("changes", [])
        }
        previous_keys = {
            (c["family"], c["metric"]) for c in previous_advisory.get("changes", [])
        }

        resolved_count = len(previous_keys - current_keys)
        persisting_count = len(previous_keys & current_keys)
        new_count = len(current_keys - previous_keys)

        iteration = FixIteration(
            iteration=0,
            agent_response=prompt,
            resolved=resolved_count,
            persisting=persisting_count,
            new_issues=new_count,
        )

        result = FixResult(
            status="dry_run_residual",
            iterations=[iteration],
            dry_run=True,
            total_resolved=resolved_count,
            total_remaining=persisting_count + new_count,
        )
        # Attach extra metadata for callers
        result.resolved_count = resolved_count
        result.persisting_count = persisting_count
        result.new_count = new_count

        return result

    def _build_residual_prompt(
        self,
        current_advisory: dict,
        previous_advisory: dict,
        investigation_text: str,
    ) -> str:
        """Build an iteration-aware prompt comparing current vs previous advisory.

        Compares advisory changes by (family, metric) key to classify items as:
        - Resolved: in previous but not in current (or deviation dropped below 1.0)
        - Persisting: in both current and previous
        - New: in current but not in previous

        Args:
            current_advisory: The current advisory dict (post-fix-attempt).
            previous_advisory: The previous advisory dict (pre-fix-attempt).
            investigation_text: Original investigation report text.

        Returns:
            Formatted residual prompt string.
        """
        # Index changes by (family, metric)
        prev_by_key = {}
        for c in previous_advisory.get("changes", []):
            key = (c["family"], c["metric"])
            prev_by_key[key] = c

        curr_by_key = {}
        for c in current_advisory.get("changes", []):
            key = (c["family"], c["metric"])
            curr_by_key[key] = c

        prev_keys = set(prev_by_key.keys())
        curr_keys = set(curr_by_key.keys())

        # Classify
        resolved_keys = prev_keys - curr_keys
        persisting_keys = prev_keys & curr_keys
        new_keys = curr_keys - prev_keys

        # Also check for items in both but with deviation now below 1.0
        still_persisting = set()
        for key in persisting_keys:
            dev = curr_by_key[key].get("deviation_stddev", curr_by_key[key].get("deviation", 999))
            if dev < 1.0:
                resolved_keys.add(key)
            else:
                still_persisting.add(key)
        persisting_keys = still_persisting

        # Build resolved section
        if resolved_keys:
            resolved_lines = []
            for key in sorted(resolved_keys):
                item = prev_by_key[key]
                resolved_lines.append(
                    f"- {key[0]} / {key[1]}: was deviation "
                    f"{item.get('deviation_stddev', item.get('deviation', '?'))}"
                )
            resolved_section = "\n".join(resolved_lines)
        else:
            resolved_section = "(none resolved yet)"

        # Build persisting section
        if persisting_keys:
            persisting_lines = []
            for key in sorted(persisting_keys):
                prev_item = prev_by_key[key]
                curr_item = curr_by_key[key]
                prev_dev = prev_item.get("deviation_stddev", prev_item.get("deviation", "?"))
                curr_dev = curr_item.get("deviation_stddev", curr_item.get("deviation", "?"))
                persisting_lines.append(
                    f"- {key[0]} / {key[1]}: deviation {prev_dev} -> {curr_dev}"
                )
            persisting_section = "\n".join(persisting_lines)
        else:
            persisting_section = "(none — all previous issues resolved!)"

        # Build new issues section (append to persisting)
        if new_keys:
            new_lines = ["\n### New Issues (not in previous advisory)"]
            for key in sorted(new_keys):
                curr_item = curr_by_key[key]
                curr_dev = curr_item.get("deviation_stddev", curr_item.get("deviation", "?"))
                new_lines.append(
                    f"- {key[0]} / {key[1]}: deviation {curr_dev}"
                )
            persisting_section += "\n" + "\n".join(new_lines)

        # Get recent changes context
        previous_changes = self._get_recent_changes_context()

        return RESIDUAL_PROMPT_TEMPLATE.format(
            resolved_section=resolved_section,
            persisting_section=persisting_section,
            previous_changes=previous_changes,
            investigation_text=investigation_text,
        )

    def _get_recent_changes_context(self) -> str:
        """Get a summary of recent git changes for residual prompt context."""
        try:
            # Get diff stat of modified files
            proc = subprocess.run(
                ["git", "diff", "--stat", "HEAD~1"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return f"Recent changes (git diff --stat HEAD~1):\n{proc.stdout.strip()}"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: list modified files from working tree
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return f"Modified files:\n{proc.stdout.strip()}"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return "(no recent changes detected)"
