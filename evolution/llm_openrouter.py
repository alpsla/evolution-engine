"""Minimal OpenRouter LLM client for Phase 3.1."""
import os
try:
    import requests
except ImportError:
    requests = None

class OpenRouterClient:
    def __init__(self, model: str):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = model
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")

    def generate(self, prompt: str) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "You are a neutral explanation renderer. Output ONLY the rewritten explanation text. Do not add preambles, labels, headings, or meta-commentary like 'Here is the rewritten explanation'. Do not add facts, judgments, or recommendations."},
                {"role": "user", "content": prompt},
            ],
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
