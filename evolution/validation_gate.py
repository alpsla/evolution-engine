"""Validation gate for Phase 3.1 LLM output.
Rejects any output that violates Phase 3/3.1 invariants.
"""
import re

FORBIDDEN_TERMS = re.compile(
    r"\b(risk|risky|danger|warning|should|needs|consider|recommend|problematic|bad|good)\b",
    re.IGNORECASE,
)

SECRET_TERMS = re.compile(
    r"\b(api key|apikey|token|secret|credential|\.env|environment variable)\b",
    re.IGNORECASE,
)

class ValidationGate:
    def __init__(self):
        pass

    def _extract_numbers(self, text: str):
        return set(re.findall(r"[-+]?\d*\.\d+|\d+", text))

    def numeric_fidelity(self, candidate: str, baseline: str) -> bool:
        # Candidate must not introduce new numbers
        cand_nums = self._extract_numbers(candidate)
        base_nums = self._extract_numbers(baseline)
        return cand_nums.issubset(base_nums)

    def no_forbidden_language(self, candidate: str) -> bool:
        return not FORBIDDEN_TERMS.search(candidate)

    def no_secret_requests(self, candidate: str) -> bool:
        return not SECRET_TERMS.search(candidate)

    def accepts(self, candidate: str, baseline: str) -> bool:
        return (
            self.numeric_fidelity(candidate, baseline)
            and self.no_forbidden_language(candidate)
            and self.no_secret_requests(candidate)
        )
