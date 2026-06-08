"""MySQL persistence for the scraper.

The hot path is the new-product check. We rely on a UNIQUE(dedup_key) index
and INSERT ... ON DUPLICATE KEY UPDATE so each product is one indexed write,
and `row affected == 1` tells us it was genuinely new (worth pushing to the app).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pymysql

from .sources.base import ScrapedProduct


class Database:
    def __init__(self, **conn_kwargs) -> None:
        self._conn = pymysql.connect(
            charset="utf8mb4",
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
            **conn_kwargs,
        )

    # -- sources ---------------------------------------------------------- #
    def source_id(self, slug: str, display_name: str, base_url: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO sources (slug, display_name, base_url)
                       VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE display_name = VALUES(display_name)""",
                (slug, display_name, base_url),
            )
            cur.execute("SELECT id FROM sources WHERE slug = %s", (slug,))
            row = cur.fetchone()
        self._conn.commit()
        return int(row["id"])

    def mark_run(self, source_id: int, *, started_at: datetime,
                 duration_ms: int, found: int, new: int,
                 status: str, note: str | None = None) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO scrape_runs
                       (source_id, started_at, duration_ms, items_found,
                        items_new, status, note)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (source_id, started_at, duration_ms, found, new, status, note),
            )
            cur.execute(
                """UPDATE sources
                      SET last_run_at = %s, last_status = %s, last_error = %s
                    WHERE id = %s""",
                (started_at, status, note, source_id),
            )
        self._conn.commit()

    # -- products --------------------------------------------------------- #
    def upsert(self, source_id: int, slug: str,
               product: ScrapedProduct) -> bool:
        """Insert/refresh a product. Returns True if it was newly seen."""
        now = datetime.now(timezone.utc)
        dedup = product.dedup_key(slug)
        with self._conn.cursor() as cur:
            affected = cur.execute(
                """INSERT INTO products
                       (source_id, dedup_key, external_id, title, price,
                        currency, url, image_url, in_stock, first_seen, last_seen)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       price     = VALUES(price),
                       in_stock  = VALUES(in_stock),
                       last_seen = VALUES(last_seen)""",
                (source_id, dedup, product.external_id, product.title,
                 product.price, product.currency, product.url,
                 product.image_url, int(product.in_stock), now, now),
            )
        # affected rows: 1 = inserted (new), 2 = updated (already existed).
        is_new = affected == 1
        self._conn.commit()
        return is_new

    def close(self) -> None:
        self._conn.close()
