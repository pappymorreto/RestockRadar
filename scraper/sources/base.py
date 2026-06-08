"""Source adapter contract.

Every site we monitor is one subclass. Keeping each site isolated behind this
small interface means a markup change on one source is a one-file fix and can
never take the rest of the fleet down.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol


@dataclass(frozen=True)
class ScrapedProduct:
    external_id: str            # stable id from the source site
    title: str
    url: str
    price: float | None = None
    currency: str = "GBP"
    image_url: str | None = None
    in_stock: bool = True
    captured_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def dedup_key(self, source_slug: str) -> str:
        return f"{source_slug}:{self.external_id}"


class MarkupChanged(Exception):
    """Raised when a parser can't find the structure it depends on.

    We fail loud (with a fingerprint of the page) instead of silently
    returning zero products, so an alert can name *which* source drifted.
    """


def page_fingerprint(html: str) -> str:
    return hashlib.sha1(html.encode("utf-8", "ignore")).hexdigest()[:12]


class Source(Protocol):
    slug: str
    display_name: str
    base_url: str

    def listing_url(self) -> str: ...
    def parse(self, html: str) -> Iterable[ScrapedProduct]: ...
