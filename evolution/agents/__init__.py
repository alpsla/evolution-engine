"""
Agent backends for Evolution Engine AI integration.

Available agents:
  - AnthropicAgent: Uses Anthropic API (ANTHROPIC_API_KEY) — best for investigation
  - CliAgent: Calls any CLI tool via subprocess — best for file editing (e.g. claude CLI)
  - ShowPromptAgent: Prints prompt to stdout for manual use — universal fallback

Factory:
  get_agent() auto-detects the best available agent.
"""

from evolution.agents.base import AgentResult, BaseAgent, get_agent

__all__ = ["BaseAgent", "AgentResult", "get_agent"]
