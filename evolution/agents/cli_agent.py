"""
CLI agent — invokes an external AI coding tool via subprocess.

Best for file editing (e.g. `claude` CLI, or any tool that accepts piped input).
The agent runs in the repo directory and can modify files directly.

Default command: `claude` (Claude Code CLI)
Override with: CliAgent(command="my-tool")
"""

import logging
import subprocess
from typing import Optional

from evolution.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 300  # 5 minutes max per invocation


class CliAgent(BaseAgent):
    """Agent that calls a CLI tool via subprocess."""

    def __init__(
        self,
        command: str = "claude",
        model: str = None,
        timeout: int = TIMEOUT_SECONDS,
    ):
        self._command = command
        self._model = model
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"cli ({self._command})"

    @property
    def can_edit_files(self) -> bool:
        return True

    def complete(self, prompt: str, system: str = "") -> AgentResult:
        """Run CLI tool with prompt piped to stdin."""
        return self._run(prompt, system=system)

    def complete_with_files(
        self,
        prompt: str,
        working_dir: str,
        system: str = "",
    ) -> AgentResult:
        """Run CLI tool in a working directory where it can edit files."""
        return self._run(prompt, system=system, cwd=working_dir)

    def _run(
        self,
        prompt: str,
        system: str = "",
        cwd: str = None,
    ) -> AgentResult:
        """Execute the CLI command with the prompt."""
        args = [self._command]

        # Claude Code CLI accepts --print for non-interactive mode
        if self._command == "claude":
            args.extend(["--print", "--output-format", "text"])
            if self._model:
                args.extend(["--model", self._model])
            if system:
                args.extend(["--system-prompt", system])

        args.extend(["--prompt", prompt])

        try:
            result = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

            if result.returncode != 0:
                error_text = result.stderr.strip() or f"Exit code {result.returncode}"
                logger.warning("CLI agent returned non-zero: %s", error_text)
                return AgentResult(
                    text=result.stdout,
                    success=False,
                    error=error_text,
                    model=self._command,
                )

            return AgentResult(
                text=result.stdout,
                success=True,
                model=self._command,
            )

        except subprocess.TimeoutExpired:
            return AgentResult(
                text="",
                success=False,
                error=f"CLI agent timed out after {self._timeout}s",
                model=self._command,
            )
        except FileNotFoundError:
            return AgentResult(
                text="",
                success=False,
                error=f"Command not found: {self._command}",
                model=self._command,
            )
        except Exception as e:
            return AgentResult(
                text="",
                success=False,
                error=str(e),
                model=self._command,
            )
