"""
Rate-limited, disk-cached HTTP fetcher for the QElectroTech bugtracker.

Read-only by construction: this module only ever issues GET requests. It
never posts, comments, or authenticates. Two rules protect a small
volunteer-run server:

  * every fetched page is written to disk and served from cache by default
    (--refresh re-fetches), so re-running the parser never re-scrapes the
    site; and
  * requests are throttled to >= 1 per second and never issued in parallel.

stdlib only: urllib.request for transport, hashlib/json for the cache index.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = (
    "QET-bugtracker-corpus/1.0 (read-only research; contact: ispyisail on GitHub)"
)
MIN_INTERVAL = 1.0  # seconds between requests -- do not lower
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "cache"


class RateLimiter:
    """In-process throttle: never less than MIN_INTERVAL between requests."""

    def __init__(self, min_interval: float = MIN_INTERVAL) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delay = self._last + self.min_interval - now
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


class FetchCache:
    """GET a URL, caching the raw bytes plus a small metadata sidecar."""

    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR, refresh: bool = False) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self._limiter = RateLimiter()

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.html", self.cache_dir / f"{key}.meta.json"

    def _cached(self, html_path: Path, meta_path: Path) -> bytes | None:
        if self.refresh:
            return None
        if html_path.exists() and meta_path.exists():
            return html_path.read_bytes()
        return None

    def get(self, url: str) -> bytes:
        """Return the page bytes, fetching (rate-limited) only if uncached."""
        html_path, meta_path = self._paths(url)
        cached = self._cached(html_path, meta_path)
        if cached is not None:
            return cached

        self._limiter.wait()
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        )
        status: int | None = None
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            # A 404/redirect target still carries a body; keep it so the parser
            # can fail loudly on the *content* rather than silently on a blank.
            data = e.read()
            status = e.code
        html_path.write_bytes(data)
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "status": status,
                    "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return data
