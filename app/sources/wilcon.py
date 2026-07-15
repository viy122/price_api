from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from app.models import NormalizedResult
from app.sources.base import BaseSource
from app.sources._common import now_mnl, clean_price, extract_img, get_client, HTTP_TIMEOUT

_BASE_URL = "https://shop.wilcon.com.ph"
_SELLER = "Wilcon Depot"


class WilconSource(BaseSource):
    """Magento storefront; search results are server-rendered."""

    department = "hardware"

    async def search(self, query: str, limit: int) -> tuple[list[NormalizedResult], str | None]:
        url = f"{_BASE_URL}/catalogsearch/result/?q={quote(query)}"
        try:
            resp = await get_client().get(url)
            resp.raise_for_status()
            html = resp.text
        except httpx.TimeoutException:
            return [], f"Wilcon Depot: request timed out after {HTTP_TIMEOUT}s"
        except httpx.HTTPStatusError as exc:
            return [], f"Wilcon Depot: HTTP {exc.response.status_code}"
        except Exception as exc:
            return [], f"Wilcon Depot: request failed — {exc}"

        try:
            results = self._parse(html, query, limit)
        except Exception as exc:
            return [], f"Wilcon Depot: failed to parse results — {exc}"

        return results, None

    def _parse(self, html: str, query: str, limit: int) -> list[NormalizedResult]:
        soup = BeautifulSoup(html, "html.parser")
        scraped_at = now_mnl()
        results: list[NormalizedResult] = []

        for card in soup.select("div.product-item-info"):
            link = card.select_one("a.product-item-name") or card.select_one("a.product-item-link")
            price_el = card.select_one("[data-price-amount]")
            if link is None or price_el is None:
                continue

            price = clean_price(price_el.get("data-price-amount"))
            if price is None or price <= 0:
                continue

            uom_el = card.select_one("span.unit-text")
            uom = uom_el.get_text(strip=True).lstrip("/ ").strip() if uom_el else ""

            href = link.get("href", "")
            results.append(NormalizedResult(
                item=query,
                source=_SELLER,
                product_code="",
                description=link.get_text(strip=True),
                uom=uom,
                price_php=price,
                seller=_SELLER,
                is_official=False,
                url=urljoin(_BASE_URL, href),
                image_url=extract_img(card, _BASE_URL),
                scraped_at=scraped_at,
            ))

            if len(results) >= limit:
                break

        return results
