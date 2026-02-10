"""
Anthropic API agent — uses the anthropic Python SDK for text completions.

Best for investigation (text-only analysis). Does NOT edit files.

Requires:
  pip install anthropic
  export ANTHROPIC_API_KEY=sk-ant-...
"""

import logging
from typing import Optional

from evolution.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 4096


class AnthropicAgent(BaseAgent):
    """Agent that uses the Anthropic API for text completions."""

    def __init__(
        self,
        api_key: str = "",
        model: str = None,
        max_tokens: int = MAX_TOKENS,
    ):
        self._api_key = api_key
        self._model = model or DEFAULT_MODEL
        self._max_tokens = max_tokens
        self._client = None

    @property
    def name(self) -> str:
        return f"anthropic ({self._model})"

    def complete(self, prompt: str, system: str = "") -> AgentResult:
        """Send prompt to Anthropic API, return response text."""
        client = self._get_client()

        try:
            kwargs = {
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system

            response = client.messages.create(**kwargs)

            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

            usage = {}
            if hasattr(response, "usage"):
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }

            return AgentResult(
                text=text,
                success=True,
                model=response.model,
                usage=usage,
            )

        except Exception as e:
            logger.error("Anthropic API error: %s", e)
            return AgentResult(
                text="",
                success=False,
                error=str(e),
                model=self._model,
            )

    def _get_client(self):
        """Lazy-initialize the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required for AnthropicAgent. "
                    "Install it with: pip install anthropic"
                )
        return self._client
