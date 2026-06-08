"""Example source adapter: a sneaker/streetwear "new arrivals" grid.

Illustrative of the real pattern: locate the listing grid, pull a stable id +
fields per card, and raise MarkupChanged the moment the structure we rely on
disappears. Selectors are kept in one place so a site redesign is a quick edit.
"""

from __future__ import annotations

from typing import Iterable

from selectolax.parser import HTMLParser

from .base import MarkupChanged, ScrapedProduct, Source, page_fingerprint


class KicksMarket(Source):
    slug = "kicksmarket"
    display_name = "KicksMarket"
    base_url = "https://kicksmarket.example"

    # All site-specific selectors live here — the only thing that changes
    # when the source redesigns its page.
    CARD = "div.product-card"
    SEL_ID = "data-product-id"
    SEL_TITLE = "a.product-card__title"
    SEL_PRICE = "span.price"
    SEL_LINK = "a.product-card__title"
    SEL_IMG = "img.product-card__img"

    def listing_url(self) -> str:
        return f"{self.base_url}/collections/new-arrivals?sort=created-desc"

    def parse(self, html: str) -> Iterable[ScrapedProduct]:
        tree = HTMLParser(html)
        cards = tree.css(self.CARD)
        if not cards:
            # Structure gone => site changed, not "no products". Fail loud.
            raise MarkupChanged(
                f"{self.slug}: no '{self.CARD}' nodes; "
                f"fingerprint={page_fingerprint(html)}"
            )

        for card in cards:
            external_id = card.attributes.get(self.SEL_ID)
            title_node = card.css_first(self.SEL_TITLE)
            if not external_id or title_node is None:
                # Skip a malformed card rather than crashing the whole run.
                continue

            link = title_node.attributes.get("href", "")
            price_node = card.css_first(self.SEL_PRICE)
            img_node = card.css_first(self.SEL_IMG)

            yield ScrapedProduct(
                external_id=external_id,
                title=title_node.text(strip=True),
                url=self._abs(link),
                price=self._parse_price(price_node.text() if price_node else None),
                currency="GBP",
                image_url=img_node.attributes.get("src") if img_node else None,
                in_stock="sold-out" not in (card.attributes.get("class") or ""),
            )

    def _abs(self, href: str) -> str:
        if href.startswith("http"):
            return href
        return f"{self.base_url}{href}"

    @staticmethod
    def _parse_price(raw: str | None) -> float | None:
        if not raw:
            return None
        cleaned = "".join(c for c in raw if c.isdigit() or c == ".")
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
