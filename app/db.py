"""
MySQL (prism_db) integration: search logging and price-history snapshots.

The API is the single writer of market_price_snapshots — one row per real
scrape, including background refreshes and pre-warms — and the Laravel app
reads them. Every /search is logged to api_search_log; that log drives
cache pre-warming and shows admins what each department looks for.

All writes are fire-and-forget from background tasks: if MySQL is down the
API keeps serving searches and just skips logging until it comes back.
"""

import logging
import os
import time

import aiomysql

from app.models import NormalizedResult

logger = logging.getLogger("prism.db")

# Don't hammer a down MySQL: after a failed pool creation, skip DB work
# for this long before trying to connect again.
_RECONNECT_COOLDOWN = 60

_pool: aiomysql.Pool | None = None
_next_connect_attempt = 0.0

_CREATE_SEARCH_LOG = """
CREATE TABLE IF NOT EXISTS api_search_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    item VARCHAR(255) NOT NULL,
    department VARCHAR(30) NULL,
    searched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_item (item),
    KEY idx_searched_at (searched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


async def _get_pool() -> aiomysql.Pool | None:
    global _pool, _next_connect_attempt
    if _pool is not None:
        return _pool
    if time.monotonic() < _next_connect_attempt:
        return None
    try:
        _pool = await aiomysql.create_pool(
            host=os.getenv("PRISM_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("PRISM_DB_PORT", "3306")),
            user=os.getenv("PRISM_DB_USER", "root"),
            password=os.getenv("PRISM_DB_PASSWORD", ""),
            db=os.getenv("PRISM_DB_NAME", "prism_db"),
            minsize=1,
            maxsize=5,
            autocommit=True,
        )
    except Exception as exc:
        _next_connect_attempt = time.monotonic() + _RECONNECT_COOLDOWN
        logger.warning("MySQL unavailable, logging/history paused: %s", exc)
        return None
    async with _pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(_CREATE_SEARCH_LOG)
    return _pool


async def init() -> None:
    await _get_pool()


async def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


async def log_search(item: str, department: str | None) -> None:
    pool = await _get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO api_search_log (item, department) VALUES (%s, %s)",
                    (item.strip()[:255], department),
                )
    except Exception as exc:
        logger.warning("failed to log search %r: %s", item, exc)


async def record_snapshots(
    results: list[NormalizedResult], query: str, department: str | None
) -> None:
    """Persist one price-history row per freshly scraped result."""
    pool = await _get_pool()
    if pool is None or not results:
        return
    rows = [
        (
            r.description[:255],
            r.price_php,
            r.source[:255],
            r.url[:2048] or None,
            department,
            query.strip()[:255],
            r.scraped_at.replace(tzinfo=None),
        )
        for r in results
        if r.description and r.price_php is not None
    ]
    if not rows:
        return
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO market_price_snapshots"
                    " (product_name, price, original_price, source_site, product_url,"
                    "  department, query_used, scraped_at, created_at, updated_at)"
                    " VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, NOW(), NOW())",
                    rows,
                )
    except Exception as exc:
        logger.warning("failed to record snapshots for %r: %s", query, exc)


async def top_queries(limit: int, days: int) -> list[str]:
    """Most-searched terms in the window, for cache pre-warming."""
    pool = await _get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT LOWER(TRIM(item)) AS q, COUNT(*) AS c"
                    " FROM api_search_log"
                    " WHERE searched_at >= NOW() - INTERVAL %s DAY"
                    " GROUP BY q ORDER BY c DESC LIMIT %s",
                    (days, limit),
                )
                return [row[0] for row in await cur.fetchall()]
    except Exception as exc:
        logger.warning("failed to fetch top queries: %s", exc)
        return []
