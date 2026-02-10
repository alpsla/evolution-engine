"""Phase 3.1 LLM Renderer with validation-gated fallback."""
import os
import re
from evolution.validation_gate import ValidationGate
from evolution.llm_openrouter import OpenRouterClient
try:
    from evolution.llm_anthropic import AnthropicClient
except ImportError:
    AnthropicClient = None

_PREAMBLE_RE = re.compile(
    r"^(?:(?:Here(?:'s| is) (?:a |the )?rewritten explanation[^:]*:|Explanation:)\s*\n?)",
    re.IGNORECASE,
)

class Phase31Renderer:
    def __init__(self):
        self.enabled = os.getenv("PHASE31_ENABLED", "false").lower() == "true"
        self.model = os.getenv("PHASE31_MODEL", "anthropic/claude-3.5-haiku")
        self.gate = ValidationGate()
        self.llm = None

        if self.enabled:
            # Prefer Anthropic direct if key is present and client is available
            if os.getenv("ANTHROPIC_API_KEY") and AnthropicClient:
                try:
                    self.llm = AnthropicClient(self.model)
                except Exception:
                    self.llm = None
            
            # Fallback to OpenRouter
            if not self.llm:
                try:
                    self.llm = OpenRouterClient(self.model)
                except Exception:
                    # Silent fallback if LLM cannot be initialized
                    self.llm = None
                    if not os.getenv("ANTHROPIC_API_KEY"):
                         self.enabled = False

    @staticmethod
    def _strip_preamble(text: str) -> str:
        """Remove LLM-added preambles like 'Explanation:' or 'Here's a rewritten...'."""
        return _PREAMBLE_RE.sub("", text).strip()

    def render(self, explanation: dict) -> dict:
        if not self.enabled or not self.llm:
            return explanation

        baseline_text = explanation["summary"]
        prompt = (
            "Rewrite the following explanation for a product manager audience. "
            "Use plain English — avoid statistical jargon like 'MAD', 'stddev', 'z-score', or 'deviation'. "
            "Keep the relative comparison (e.g. '3x more than usual') and the practical insight. "
            "Do not add facts, numbers, judgments, recommendations, or generalizations. "
            "Preserve all numeric values exactly.\n\n"
            f"Explanation:\n{baseline_text}"
        )

        try:
            candidate_text = self.llm.generate(prompt)
        except Exception:
            # LLM unavailable (timeout, rate limit, network) — fall back to template
            return explanation

        # Strip common LLM preamble artifacts
        candidate_text = self._strip_preamble(candidate_text)

        if not self.gate.accepts(candidate_text, baseline_text):
            return explanation

        explanation = dict(explanation)
        explanation["summary"] = candidate_text
        explanation["phase31_used"] = True
        return explanation
