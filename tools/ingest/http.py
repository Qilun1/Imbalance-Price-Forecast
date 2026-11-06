"""Small HTTP helper: retries with backoff, polite rate limiting, raw-response caching."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

USER_AGENT = "WeatherSensAI-SinceAI2026-imbalance/0.1 (hackathon research)"


class Client:
    def __init__(self, min_interval_s: float = 0.5, retries: int = 4, timeout_s: float = 60, headers: dict | None = None):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, **(headers or {})})
        self.min_interval_s, self.retries, self.timeout_s = min_interval_s, retries, timeout_s
        self._last = 0.0

    def get_json(self, url: str, params: dict | None = None, cache: Path | None = None) -> dict | list:
        if cache is not None and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        err = None
        for attempt in range(self.retries):
            wait = self.min_interval_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.get(url, params=params, timeout=self.timeout_s)
                if r.status_code == 429 or r.status_code >= 500:
                    err = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                    time.sleep(min(60, 2 ** attempt * 2))
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                data = r.json()
                if cache is not None:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps(data), encoding="utf-8")
                return data
            except requests.RequestException as e:
                err = e
                time.sleep(min(60, 2 ** attempt * 2))
        raise RuntimeError(f"giving up on {url}: {err}")
