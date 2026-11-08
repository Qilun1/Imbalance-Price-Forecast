"""Small HTTP helper: retries with backoff, polite rate limiting, raw-response caching."""
from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

USER_AGENT = "KODA-SinceAI2026-imbalance/0.1 (hackathon research)"


class DailyLimit(RuntimeError):
    """The provider's daily quota is used up: stop and resume tomorrow (cached runs are kept)."""


class Budget:
    """Sliding-window call budget, so we stay under a provider's per-minute/hour/day limits."""

    def __init__(self, per_minute: float, per_hour: float, per_day: float):
        self.limits = [(60.0, per_minute), (3600.0, per_hour), (86400.0, per_day)]
        self.log: deque[tuple[float, float]] = deque()

    def acquire(self, weight: float) -> None:
        while True:
            now = time.time()
            while self.log and now - self.log[0][0] > 86400:
                self.log.popleft()
            wait = 0.0
            for window, limit in self.limits:
                used = sum(w for t, w in self.log if now - t <= window)
                if used + weight > limit:
                    if window == 86400:
                        raise DailyLimit("daily call budget reached")
                    oldest = next(t for t, _ in self.log if now - t <= window)
                    wait = max(wait, oldest + window - now + 1)
            if wait <= 0:
                self.log.append((now, weight))
                return
            print(f"    rate budget: waiting {wait:.0f} s")
            time.sleep(wait)


class Client:
    def __init__(self, min_interval_s: float = 0.5, retries: int = 4, timeout_s: float = 60, headers: dict | None = None,
                 budget: Budget | None = None):
        self.budget = budget
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, **(headers or {})})
        self.min_interval_s, self.retries, self.timeout_s = min_interval_s, retries, timeout_s
        self._last = 0.0

    def get_json(self, url: str, params: dict | None = None, cache: Path | None = None, weight: float = 1.0) -> dict | list:
        if cache is not None and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        err = None
        for attempt in range(self.retries):
            if self.budget is not None:
                self.budget.acquire(weight)
            wait = self.min_interval_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.get(url, params=params, timeout=self.timeout_s)
                if r.status_code == 429:
                    reason = r.text.lower()
                    if "daily" in reason:
                        raise DailyLimit(r.text[:200])
                    if "hourly" in reason:
                        nxt = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(minute=1, second=0)
                        pause = (nxt - datetime.now(timezone.utc)).total_seconds()
                    else:
                        pause = 65
                    print(f"    provider rate limit ({r.text[:60]}...): waiting {pause:.0f} s")
                    time.sleep(pause)
                    err = RuntimeError(f"HTTP 429: {r.text[:200]}")
                    continue
                if r.status_code >= 500:
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
