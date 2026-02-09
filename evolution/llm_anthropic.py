"""Anthropic LLM client with retry, backoff, and rate-limit handling."""
import os
import time

try:
    import requests as _requests
except ImportError:
    _requests = None


class AnthropicClient:
    def __init__(self, model: str, max_retries: int = 3, base_delay: float = 2.0,
                 timeout: float = 60):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self._rate_delay = 0.0
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

    def generate(self, prompt: str) -> str:
        if not _requests:
            raise RuntimeError("The 'requests' library is required for AnthropicClient.")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        if self._rate_delay > 0:
            time.sleep(self._rate_delay)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = _requests.post(url, headers=headers, json=payload,
                                          timeout=self.timeout)

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 0))
                    delay = max(retry_after, self.base_delay * (2 ** attempt))
                    self._rate_delay = min(self._rate_delay + 1.0, 10.0)
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                self._rate_delay = max(0, self._rate_delay - 0.1)
                return response.json()["content"][0]["text"]

            except (_requests.exceptions.Timeout,
                    _requests.exceptions.ConnectionError) as e:
                last_error = e
                time.sleep(self.base_delay * (2 ** attempt))

            except _requests.exceptions.HTTPError as e:
                if response.status_code >= 500:
                    last_error = e
                    time.sleep(self.base_delay * (2 ** attempt))
                    continue
                raise

        raise last_error or RuntimeError(f"Anthropic API failed after {self.max_retries} retries")
