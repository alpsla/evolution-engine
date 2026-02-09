"""OpenRouter LLM client with retry, backoff, and rate-limit handling."""
import os
import time

try:
    import requests as _requests
except ImportError:
    _requests = None


class OpenRouterClient:
    def __init__(self, model: str, max_retries: int = 3, base_delay: float = 2.0,
                 timeout: float = 60):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self._consecutive_errors = 0
        self._request_count = 0
        self._rate_delay = 0.0  # adaptive delay between requests
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

        # Adaptive pacing: slow down if we've been hitting errors
        if self._rate_delay > 0:
            time.sleep(self._rate_delay)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                self._request_count += 1
                r = _requests.post(url, headers=headers, json=payload,
                                   timeout=self.timeout)

                # Rate limited — back off using server's Retry-After or exponential
                if r.status_code == 429:
                    retry_after = float(r.headers.get("Retry-After", 0))
                    delay = max(retry_after, self.base_delay * (2 ** attempt))
                    self._rate_delay = min(self._rate_delay + 1.0, 10.0)
                    time.sleep(delay)
                    continue

                r.raise_for_status()
                self._consecutive_errors = 0
                # Ease off adaptive delay on success
                self._rate_delay = max(0, self._rate_delay - 0.1)
                return r.json()["choices"][0]["message"]["content"]

            except (_requests.exceptions.Timeout,
                    _requests.exceptions.ConnectionError) as e:
                last_error = e
                self._consecutive_errors += 1
                delay = self.base_delay * (2 ** attempt)
                # If many consecutive errors, increase pacing significantly
                if self._consecutive_errors >= 5:
                    self._rate_delay = min(self._rate_delay + 2.0, 15.0)
                time.sleep(delay)

            except _requests.exceptions.HTTPError as e:
                # 5xx server errors — retry; 4xx (except 429) — don't
                if r.status_code >= 500:
                    last_error = e
                    time.sleep(self.base_delay * (2 ** attempt))
                    continue
                raise

        raise last_error or RuntimeError(f"LLM request failed after {self.max_retries} retries")
