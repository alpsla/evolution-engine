"""
Base agent interface and factory for AI backends.

Agents handle two tasks:
  1. Investigation: Analyze advisory text → produce investigation report (text-only)
  2. Fix: Edit files in a repo based on investigation findings (requires file access)

The factory auto-detects available backends:
  - ANTHROPIC_API_KEY → AnthropicAgent (API-based, text-only)
  - `claude` CLI available → CliAgent (subprocess, can edit files)
  - Neither → ShowPromptAgent (prints prompt for manual use)
"""

import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentResult:
    """Result from an agent invocation."""
    text: str                           # Full response text
    success: bool = True                # Whether the agent completed without error
    error: Optional[str] = None         # Error message if success=False
    model: Optional[str] = None         # Model used (e.g. "claude-sonnet-4-5-20250929")
    usage: dict = field(default_factory=dict)  # Token usage if available


class BaseAgent(ABC):
    """Abstract base for AI agent backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name."""
        ...

    @property
    def can_edit_files(self) -> bool:
        """Whether this agent can modify files on disk."""
        return False

    @abstractmethod
    def complete(self, prompt: str, system: str = "") -> AgentResult:
        """Send a prompt and get a text response.

        Args:
            prompt: The user prompt (investigation context, fix instructions, etc.)
            system: Optional system prompt for role/behavior instructions.

        Returns:
            AgentResult with the response text.
        """
        ...

    def complete_with_files(
        self,
        prompt: str,
        working_dir: str,
        system: str = "",
    ) -> AgentResult:
        """Send a prompt that may result in file edits.

        Only supported by agents with can_edit_files=True.
        Default implementation falls back to complete().

        Args:
            prompt: Instructions including what to fix.
            working_dir: Repository directory the agent can modify.
            system: Optional system prompt.

        Returns:
            AgentResult with the response text and file changes applied.
        """
        return self.complete(prompt, system=system)


class ShowPromptAgent(BaseAgent):
    """Fallback agent that just returns the prompt for manual use.

    Used when no API key or CLI tool is available. The user can
    copy the prompt into any AI tool (Cursor, Copilot, etc.).
    """

    @property
    def name(self) -> str:
        return "show-prompt"

    def complete(self, prompt: str, system: str = "") -> AgentResult:
        return AgentResult(
            text=prompt,
            success=True,
            model="manual",
        )


def get_agent(
    prefer: str = None,
    api_key: str = None,
    cli_command: str = None,
    model: str = None,
) -> BaseAgent:
    """Auto-detect and return the best available agent.

    Detection order:
      1. If `prefer` is specified, use that backend.
      2. If ANTHROPIC_API_KEY is available → AnthropicAgent
      3. If `claude` CLI is on PATH → CliAgent
      4. Fallback → ShowPromptAgent

    Args:
        prefer: Force a specific backend ("anthropic", "cli", "show-prompt").
        api_key: Anthropic API key (overrides env var).
        cli_command: CLI command to use (default: "claude").
        model: Model name override.

    Returns:
        A configured BaseAgent instance.
    """
    if prefer == "show-prompt":
        return ShowPromptAgent()

    if prefer == "anthropic" or (prefer is None and _has_anthropic_key(api_key)):
        try:
            from evolution.agents.anthropic_agent import AnthropicAgent
            key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            return AnthropicAgent(api_key=key, model=model)
        except ImportError:
            pass  # anthropic package not installed

    if prefer == "cli" or (prefer is None and _has_cli(cli_command)):
        from evolution.agents.cli_agent import CliAgent
        return CliAgent(command=cli_command or "claude", model=model)

    return ShowPromptAgent()


def _has_anthropic_key(api_key: str = None) -> bool:
    """Check if Anthropic API key is available."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key)


def _has_cli(command: str = None) -> bool:
    """Check if a CLI command is available on PATH."""
    cmd = command or "claude"
    return shutil.which(cmd) is not None
