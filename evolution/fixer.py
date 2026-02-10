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

Usage:
    fixer = Fixer(repo_path=".", evo_dir=".evo")
    result = fixer.run()
    result = fixer.run(dry_run=True)
    result = fixer.run(max_iterations=5)
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evolution.agents.base import BaseAgent, get_agent

logger = logging.getLogger(__name__)

FIX_SYSTEM_PROMPT = """\
You are a senior software engineer fixing anomalies detected by Evolution Engine. \
You receive an investigation report identifying root causes of deviations from \
project baselines.

Rules:
1. Make minimal, targeted fixes. Do NOT rewrite or refactor unrelated code.
2. Fix only the specific issues identified in the report.
3. Prefer the simplest correct solution.
4. Do NOT add new features, tests, or documentation unless the issue requires it.
5. Do NOT modify files outside the scope of the identified problems.
6. If a finding is marked "expected" (not a problem), skip it.
7. After applying fixes, briefly describe what you changed and why.

Focus on the items marked as "problem" in the investigation report.\
"""

FIX_PROMPT_TEMPLATE = """\
The following investigation report identifies anomalies in this repository. \
Please apply targeted fixes for the items marked as problems.

{investigation_text}

{residual_context}

Apply minimal fixes to resolve the flagged issues. Focus on:
- Files and changes identified in the root cause analysis
- The suggested fixes from the investigation
- Preserving existing behavior — do not refactor unrelated code
"""


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
    ):
        self.iteration = iteration
        self.agent_response = agent_response
        self.verification = verification
        self.resolved = resolved
        self.persisting = persisting
        self.new_issues = new_issues
        self.regressions = regressions

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
        branch_name: str = None,
        scope: str = None,
    ) -> FixResult:
        """Execute the fix-verify loop.

        Args:
            agent: AI agent for applying fixes (auto-detected if None).
            max_iterations: Max fix attempts before stopping (default 3).
            dry_run: If True, show what would be fixed without modifying files.
            branch_name: Git branch name for fixes (default: evo/fix-<timestamp>).
            scope: Pipeline scope name (default: repo directory name).

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

            # Ask agent to apply fixes
            result = agent.complete_with_files(
                prompt=prompt,
                working_dir=str(self.repo_path),
                system=FIX_SYSTEM_PROMPT,
            )

            if not result.success:
                iterations.append(FixIteration(
                    iteration=i,
                    agent_response=result.error or "Agent failed",
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
            )
            iterations.append(iteration)

            logger.info(
                "Iteration %d: resolved=%d, persisting=%d, new=%d, regressions=%d",
                i, resolved, persisting, new_issues, regressions,
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
