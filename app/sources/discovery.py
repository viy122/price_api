"""
Platform detection and candidate discovery for vendor onboarding.

Given a storefront's base URL, figure out whether it's Shopify or
WooCommerce so a generic source can be instantiated for it without writing
any per-vendor scraping code. Sites that are neither (bespoke HTML, Magento,
document-based catalogues, ...) still need a real BaseSource subclass.

search_candidate_domains() finds candidate URLs to run that detection
against, via SerpApi (a paid Google-search API — scraping Google's results
page directly violates their ToS) rather than a per-vendor URL a human
already found.
"""

import logging
import os
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.sources._common import get_client
from app.sources._shopify import ShopifyPredictiveSearchSource
from app.sources._woocommerce import WooCommerceSource
from app.sources.base import BaseSource

logger = logging.getLogger("prism.discovery")

_PROBE_QUERY = "a"

# Large marketplaces/social platforms that will never be a single-vendor
# Shopify/WooCommerce storefront — skip them to save a wasted detection
# request against sites that show up in almost every search.
_SKIP_DOMAINS = {
    "google.com", "facebook.com", "youtube.com", "wikipedia.org",
    "lazada.com.ph", "shopee.ph", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "amazon.com",
}


async def search_candidate_domains(query: str, limit: int) -> list[str]:
    """
    Query SerpApi for organic Google results and return candidate storefront
    base URLs (deduped, marketplace/social domains filtered out).

    Returns [] if SERPAPI_KEY isn't set, or on any request failure — this is
    a best-effort discovery step, not something that should ever break the
    background job it runs in.
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return []

    try:
        # get_client()'s default timeout (HTTP_TIMEOUT, 5s) is tuned for
        # vendor-scraping fan-out on the user-facing /search path, where a
        # dead site must fail fast. This call instead runs once a day in a
        # background job, so it can afford to wait longer for SerpApi.
        resp = await get_client().get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "api_key": api_key,
                "num": str(limit),
                "gl": "ph",
                "hl": "en",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("SerpApi request failed for %r: %s", query, exc)
        return []

    candidates: list[str] = []
    for result in data.get("organic_results", []):
        link = result.get("link")
        if not link:
            continue
        parsed = urlparse(link)
        if not parsed.scheme or not parsed.netloc:
            continue
        host = parsed.netloc.removeprefix("www.")
        if any(host == d or host.endswith(f".{d}") for d in _SKIP_DOMAINS):
            continue
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        if base_url not in candidates:
            candidates.append(base_url)

    return candidates


async def detect_platform(base_url: str) -> tuple[str | None, str | None]:
    """Returns (platform, error). platform is "shopify", "woocommerce", or None."""
    base_url = base_url.rstrip("/")
    client = get_client()

    try:
        resp = await client.get(
            f"{base_url}/search/suggest.json",
            params={"q": _PROBE_QUERY, "resources[type]": "product", "resources[limit]": "1"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if "products" in data.get("resources", {}).get("results", {}):
                return "shopify", None
    except Exception:
        pass

    try:
        resp = await client.get(f"{base_url}/", params={"s": _PROBE_QUERY, "post_type": "product"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            if soup.select_one(".type-product") or soup.select_one(".woocommerce-Price-amount"):
                return "woocommerce", None
    except Exception:
        pass

    return None, "not a recognized Shopify/WooCommerce storefront — needs a custom scraper"


def build_dynamic_source(
    vendor_id: int, platform: str, base_url: str, seller: str, department: str | None
) -> BaseSource:
    """
    Instantiate a generic source for a manually-approved vendor.

    The rest of the app (cache keys, per-source concurrency semaphores,
    health stats) all identify a source by its class name, one class per
    vendor — true for every hand-written 7-line subclass. A plain instance
    of the shared generic class would break that: two approved vendors on
    the same platform would collide under the same cache key. A distinct
    class per vendor_id (not per-vendor code, just a mechanical `type()`
    call) restores the one-class-per-vendor invariant.
    """
    base_cls = ShopifyPredictiveSearchSource if platform == "shopify" else WooCommerceSource
    cls = type(f"DynamicVendor{vendor_id}", (base_cls,), {})
    source = cls()
    source.base_url = base_url.rstrip("/")
    source.seller = seller
    source.department = department
    return source
