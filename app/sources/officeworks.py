import httpx

from app.models import NormalizedResult
from app.sources.base import BaseSource
from app.sources._common import now_mnl, get_client, HTTP_TIMEOUT

_API_URL = "https://api.officeworks.ph/wp-json/wc/store/v1/products"
_SELLER = "OfficeWorks"


class OfficeWorksSource(BaseSource):
    """
    officeworks.ph is a Nuxt frontend over a headless WordPress backend at
    api.officeworks.ph; the storefront HTML has no product markup. Uses the
    public WooCommerce Store API instead. Prices come back in minor units
    (centavos) with a currency_minor_unit exponent.
    """

    department = "office"

    async def search(self, query: str, limit: int) -> tuple[list[NormalizedResult], str | None]:
        params = {"search": query, "per_page": str(min(limit, 100))}
        try:
            resp = await get_client().get(_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            return [], f"OfficeWorks: request timed out after {HTTP_TIMEOUT}s"
        except httpx.HTTPStatusError as exc:
            return [], f"OfficeWorks: HTTP {exc.response.status_code}"
        except Exception as exc:
            return [], f"OfficeWorks: request failed — {exc}"

        try:
            results = self._parse(data, query, limit)
        except Exception as exc:
            return [], f"OfficeWorks: failed to parse results — {exc}"

        return results, None

    def _parse(self, data: list, query: str, limit: int) -> list[NormalizedResult]:
        scraped_at = now_mnl()
        results: list[NormalizedResult] = []

        for p in data:
            prices = p.get("prices") or {}
            raw = prices.get("price")
            if not raw:
                continue
            try:
                minor_unit = int(prices.get("currency_minor_unit", 2))
                price = int(raw) / (10 ** minor_unit)
            except (ValueError, TypeError):
                continue
            if price <= 0:
                continue

            images = p.get("images") or []
            image = (images[0].get("thumbnail") or images[0].get("src")) if images else None

            results.append(NormalizedResult(
                item=query,
                source=_SELLER,
                product_code=p.get("sku") or str(p.get("id", "")),
                description=p.get("name", ""),
                uom="",
                price_php=price,
                seller=_SELLER,
                is_official=False,
                url=p.get("permalink", "https://www.officeworks.ph/"),
                image_url=image,
                scraped_at=scraped_at,
            ))

            if len(results) >= limit:
                break

        return results
