import asyncio
import random
import re
from datetime import datetime, timezone, timedelta

import httpx

from app.models import NormalizedResult
from app.sources.base import BaseSource
from app.sources._common import get_client, HTTP_TIMEOUT

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

        return results, None

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
