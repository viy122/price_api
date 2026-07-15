from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from app.models import NormalizedResult
from app.sources.base import BaseSource
from app.sources._common import now_mnl, clean_price, extract_img, get_client, HTTP_TIMEOUT

_SEARCH_URL = "https://www.officewarehouse.com.ph/search/?_k={query}"
_BASE_URL = "https://www.officewarehouse.com.ph"
_SELLER = "Office Warehouse"


class OfficeWarehouseSource(BaseSource):
    """
    The site shows a cookie-consent overlay, but it's a cosmetic ASP.NET
    __doPostBack UI element that doesn't gate page content — search
    results render fully server-side without accepting it.
    """

    department = "office"

    async def search(self, query: str, limit: int) -> tuple[list[NormalizedResult], str | None]:
        url = _SEARCH_URL.format(query=quote(query))
        try:
            resp = await get_client().get(url)
            resp.raise_for_status()
            html = resp.text
        except httpx.TimeoutException:
            return [], f"Office Warehouse: request timed out after {HTTP_TIMEOUT}s"
        except httpx.HTTPStatusError as exc:
            return [], f"Office Warehouse: HTTP {exc.response.status_code}"
        except Exception as exc:
            return [], f"Office Warehouse: request failed — {exc}"

        try:
            results = self._parse(html, query, limit)
        except Exception as exc:
            return [], f"Office Warehouse: failed to parse results — {exc}"

        return results, None

    def _parse(self, html: str, query: str, limit: int) -> list[NormalizedResult]:
        soup = BeautifulSoup(html, "html.parser")
        scraped_at = now_mnl()
        results: list[NormalizedResult] = []

        for card in soup.select("div.product-grid-item"):
            link = card.select_one("div.product-grid-item-name a")
            price_el = card.select_one("div.product-grid-item-price")
            if link is None or price_el is None:
                continue

            price = clean_price(price_el.get_text())
            if price is None:
                continue

            href = link.get("href", "")
            results.append(NormalizedResult(
                item=query,
                source=_SELLER,
                product_code="",
                description=link.get_text(strip=True),
                uom="",
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
