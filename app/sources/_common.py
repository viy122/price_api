import re
from datetime import datetime, timezone, timedelta

import httpx

_TZ_MNL = timezone(timedelta(hours=8))

# Shared HTTP timeout for all source adapters. Kept low so one dead site
# can't stall the whole fan-out search.
HTTP_TIMEOUT = 5

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Process-wide AsyncClient shared by every source adapter.

    Reusing one client keeps connections alive between requests (no TLS
    handshake per search) and caps total outbound connections so a burst of
    simultaneous user searches can't open hundreds of sockets at once.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers=_HEADERS,
            limits=httpx.Limits(max_connections=60, max_keepalive_connections=20),
        )
    return _client


def now_mnl() -> datetime:
    return datetime.now(_TZ_MNL)


# The PS-DBM catalogue uses formal terms that never contain the words people
# actually search with ("bond paper" is listed as "PAPER, MULTICOPY").
# A query word also matches when any of its aliases appears in the text.
_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "bond": ("multicopy", "multipurpose"),
    "ballpen": ("ballpoint",),
    "ballpens": ("ballpoint",),
    "photocopy": ("multicopy", "multipurpose"),
    "xerox": ("multicopy", "multipurpose"),
}


def words_match(query: str, text_lower: str) -> bool:
    """True when every query word (or one of its aliases) appears in text."""
    for w in query.lower().split():
        if w in text_lower:
            continue
        if any(a in text_lower for a in _QUERY_ALIASES.get(w, ())):
            continue
        return False
    return True


def extract_img(card, base_url: str) -> str | None:
    """Best-effort product image URL from a BeautifulSoup card element.

    Handles lazy-loading attributes and protocol-relative URLs; skips
    inline data: URI placeholders used by lazy loaders.
    """
    from urllib.parse import urljoin

    img = card.find("img")
    if img is None:
        return None
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        val = img.get(attr)
        if val and not val.startswith("data:"):
            if val.startswith("//"):
                return "https:" + val
            return urljoin(base_url, val)
    return None


def clean_price(raw) -> float | None:
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
