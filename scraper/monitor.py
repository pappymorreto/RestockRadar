"""RestockRadar orchestrator.

Runs each enabled source on its own interval, fetches resiliently (rotating
proxies + headers, retry/backoff with jitter, a per-source circuit breaker),
parses, and writes only genuinely-new products to MySQL. New finds are flagged
for the push-notification worker that feeds the mobile app.

Run:  python -m scraper.monitor --once     # single cycle (cron-style)
      python -m scraper.monitor            # continuous loop
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import time
from datetime import datetime, timezone

import requests

from .db import Database
from .sources.base import MarkupChanged, Source
from .sources.kicksmarket import KicksMarket

log = logging.getLogger("restockradar")

SOURCES: list[Source] = [
    KicksMarket(),
    # add more adapters here — each is isolated from the others
]

_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0 Safari/537.36",
]


def _headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(_UA),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }


def _proxies() -> dict[str, str]:
    pool = [p for p in os.getenv("PROXY_POOL", "").split(",") if p]
    if not pool:
        return {}
    p = random.choice(pool)
    return {"http": p, "https": p}


class CircuitBreaker:
    def __init__(self, threshold: int = 4, cooldown_s: float = 120.0) -> None:
        self.threshold, self.cooldown_s = threshold, cooldown_s
        self._fails = 0
        self._open_until = 0.0

    @property
    def is_open(self) -> bool:
        return time.time() < self._open_until

    def record(self, ok: bool) -> None:
        if ok:
            self._fails = 0
            return
        self._fails += 1
        if self._fails >= self.threshold:
            self._open_until = time.time() + self.cooldown_s
            self._fails = 0
            log.warning("circuit OPEN for %.0fs", self.cooldown_s)


def fetch(url: str, breaker: CircuitBreaker,
          retries: int = 4, timeout: float = 10.0) -> str:
    if breaker.is_open:
        raise RuntimeError("circuit open; backing off")
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=_headers(), proxies=_proxies(),
                             timeout=timeout)
            if r.status_code in (429, 503):
                raise requests.HTTPError(f"throttled {r.status_code}")
            r.raise_for_status()
            breaker.record(ok=True)
            return r.text
        except requests.RequestException as exc:
            last = exc
            breaker.record(ok=False)
            backoff = min(2 ** attempt, 30) + random.uniform(0, 1.5)
            log.warning("fetch %s/%s failed (%s); retry in %.1fs",
                        attempt, retries, exc, backoff)
            time.sleep(backoff)
    raise RuntimeError(f"exhausted retries for {url}: {last}")


def run_source(src: Source, db: Database) -> tuple[int, int]:
    sid = db.source_id(src.slug, src.display_name, src.base_url)
    breaker = CircuitBreaker()
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    found = new = 0
    status, note = "ok", None
    try:
        html = fetch(src.listing_url(), breaker)
        for product in src.parse(html):
            found += 1
            if db.upsert(sid, src.slug, product):
                new += 1
                log.info("NEW  %-12s  %s  %.2f %s", src.slug,
                         product.title, product.price or 0, product.currency)
    except MarkupChanged as exc:
        status, note = "error", str(exc)          # alert-worthy: site drifted
        log.error("[%s] %s", src.slug, exc)
    except Exception as exc:                       # network / circuit / etc.
        status, note = "degraded", str(exc)
        log.error("[%s] run failed: %s", src.slug, exc)

    db.mark_run(sid, started_at=started,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                found=found, new=new, status=status, note=note)
    return found, new


def cycle(db: Database) -> None:
    total_new = 0
    for src in SOURCES:
        _, new = run_source(src, db)
        total_new += new
    log.info("cycle complete: %d new across %d sources", total_new, len(SOURCES))


def main() -> None:
    ap = argparse.ArgumentParser(description="RestockRadar scraper")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    ap.add_argument("--interval", type=int, default=300, help="loop seconds")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    db = Database(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", ""),
        database=os.getenv("DB_NAME", "restockradar"),
    )
    try:
        if args.once:
            cycle(db)
        else:
            while True:
                cycle(db)
                time.sleep(args.interval)
    finally:
        db.close()


if __name__ == "__main__":
    main()
