import asyncio
import random
import re
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

from app.models import NormalizedResult
from app.sources.base import BaseSource
from app.sources._common import get_client, HTTP_TIMEOUT
from app.sources._warranty import extract_warranty

# Detail-page fetches (for warranty lookup) are extra requests on top of the
# predictive-search call, so cap how many run at once per search.
_WARRANTY_CONCURRENCY = 5

_TZ_MNL = timezone(timedelta(hours=8))


def _now_mnl() -> datetime:
    return datetime.now(_TZ_MNL)


def _clean_price(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        cleaned = re.sub(r"[^\d.]", "", str(raw).strip())
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None


class ShopifyPredictiveSearchSource(BaseSource):
    """
    Base for Shopify storefronts. Their full-text /search pages are often
    rendered client-side by search apps (e.g. Boost), so plain HTML has no
    product markup. Uses Shopify's built-in predictive-search JSON endpoint
    instead, which every Shopify theme exposes natively.

    Subclasses just set `base_url` and `seller` class attributes.
    """

    base_url: str
    seller: str

    # Warranty text only lives on the product detail page, not in the
    # predictive-search JSON, so fetching it costs one extra request per
    # result. Off by default; only sources known to list warranties (e.g.
    # appliances) opt in.
    fetch_warranty: bool = False

    async def search(self, query: str, limit: int) -> tuple[list[NormalizedResult], str | None]:
        params = {
            "q": query,
            "resources[type]": "product",
            "resources[limit]": str(min(limit, 10)),
        }
        try:
            resp = await get_client().get(f"{self.base_url}/search/suggest.json", params=params)
            if resp.status_code == 503:
                # Shopify throttles bursts from one IP when many stores are
                # queried at once; a short jittered retry usually clears it.
                await asyncio.sleep(1.0 + random.random())
                resp = await get_client().get(f"{self.base_url}/search/suggest.json", params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            return [], f"{self.seller}: request timed out after {HTTP_TIMEOUT}s"
        except httpx.HTTPStatusError as exc:
            return [], f"{self.seller}: HTTP {exc.response.status_code}"
        except Exception as exc:
            return [], f"{self.seller}: request failed — {exc}"

        try:
            results = self._parse(data, query, limit)
        except Exception as exc:
            return [], f"{self.seller}: failed to parse results — {exc}"

        if self.fetch_warranty and results:
            await self._attach_warranties(results)

        return results, None

    async def _attach_warranties(self, results: list[NormalizedResult]) -> None:
        sem = asyncio.Semaphore(_WARRANTY_CONCURRENCY)

        async def _fill(result: NormalizedResult) -> None:
            async with sem:
                try:
                    resp = await get_client().get(result.url)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")
                    warranty = extract_warranty(soup)
                    if warranty:
                        result.warranty = warranty
                except Exception:
                    pass  # leave the "Wala" default on any fetch/parse failure

        await asyncio.gather(*[_fill(r) for r in results])

    def _parse(self, data: dict, query: str, limit: int) -> list[NormalizedResult]:
        scraped_at = _now_mnl()
        results: list[NormalizedResult] = []

        products = data.get("resources", {}).get("results", {}).get("products", [])
        for p in products:
            price = _clean_price(p.get("price"))
            # <= 0 filters "price on request" placeholder listings, which would
            # otherwise always win a cheapest-price canvass
            if price is None or price <= 0:
                continue

            handle = p.get("handle", "")
            image = p.get("image") or p.get("featured_image") or None
            if isinstance(image, str) and image.startswith("//"):
                image = "https:" + image
            results.append(NormalizedResult(
                item=query,
                source=self.seller,
                product_code=str(p.get("id", "")),
                description=p.get("title", ""),
                uom="",
                price_php=price,
                seller=self.seller,
                is_official=False,
                url=f"{self.base_url}/products/{handle}" if handle else self.base_url,
                image_url=image if isinstance(image, str) else None,
                scraped_at=scraped_at,
            ))

            if len(results) >= limit:
                break

        return results
