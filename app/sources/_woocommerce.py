from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from app.models import NormalizedResult
from app.sources.base import BaseSource
from app.sources._common import now_mnl, clean_price, extract_img, get_client, HTTP_TIMEOUT


class WooCommerceSource(BaseSource):
    """
    Base for WooCommerce storefronts (search via ?s=query&post_type=product).
    Selectors tolerate theme differences: product cards are matched by the
    theme-independent `type-product` class, titles by the standard
    woocommerce-loop-product__title with h4/h3 fallbacks.

    Subclasses set `base_url` and `seller` class attributes.
    """

    base_url: str
    seller: str

    async def search(self, query: str, limit: int) -> tuple[list[NormalizedResult], str | None]:
        url = f"{self.base_url}/?s={quote(query)}&post_type=product"
        try:
            resp = await get_client().get(url)
            resp.raise_for_status()
            html = resp.text
        except httpx.TimeoutException:
            return [], f"{self.seller}: request timed out after {HTTP_TIMEOUT}s"
        except httpx.HTTPStatusError as exc:
            return [], f"{self.seller}: HTTP {exc.response.status_code}"
        except Exception as exc:
            return [], f"{self.seller}: request failed — {exc}"

        try:
            results = self._parse(html, query, limit)
        except Exception as exc:
            return [], f"{self.seller}: failed to parse results — {exc}"

        return results, None

    def _parse(self, html: str, query: str, limit: int) -> list[NormalizedResult]:
        soup = BeautifulSoup(html, "html.parser")
        scraped_at = now_mnl()
        results: list[NormalizedResult] = []

        for card in soup.select(".type-product"):
            title_el = card.select_one(".woocommerce-loop-product__title")
            if title_el is not None:
                link = title_el.find("a") or title_el.find_parent("a")
            else:
                link = card.select_one("h4 > a, h3 > a")
                title_el = link
            if title_el is None:
                continue

            # Prefer the sale price (<ins>) over the struck-through original
            price_el = (
                card.select_one("ins .woocommerce-Price-amount")
                or card.select_one("span.price .woocommerce-Price-amount")
                or card.select_one(".woocommerce-Price-amount")
            )
            if price_el is None:
                continue

            price = clean_price(price_el.get_text())
            if price is None or price <= 0:
                continue

            sku_el = card.select_one("[data-product_sku]")
            product_code = sku_el.get("data-product_sku", "") if sku_el else ""

            href = link.get("href", "") if link else ""
            results.append(NormalizedResult(
                item=query,
                source=self.seller,
                product_code=product_code,
                description=title_el.get_text(strip=True),
                uom="",
                price_php=price,
                seller=self.seller,
                is_official=False,
                url=urljoin(self.base_url, href) if href else self.base_url,
                image_url=extract_img(card, self.base_url),
                scraped_at=scraped_at,
            ))

            if len(results) >= limit:
                break

        return results
