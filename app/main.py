import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal, Optional

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from app import cache, db
from app.canvass import build_canvass_xlsx
from app.models import NormalizedResult, SearchResponse
from app.sources import SOURCES
from app.sources.base import BaseSource

Department = Literal[
    "appliances", "medical", "office", "it", "janitorial", "hardware", "furniture", "sports"
]

# Every source is always scraped and cached at this size, regardless of the
# request's `limit`, so the cache key can ignore `limit` entirely and repeat
# searches with a different limit still hit the cache.
SOURCE_FETCH_LIMIT = 20

# Failed lookups are remembered briefly so one dead site doesn't drag every
# request out to its full timeout; the source is retried live after cooldown.
FAILURE_COOLDOWN_SECONDS = 5 * 60
# key -> (retry_at, error_message)
_recent_failures: dict[str, tuple[float, str]] = {}

# Keys with a stale-while-revalidate refresh already in flight.
_refreshing: set[str] = set()

# Max simultaneous live scrapes per retailer site, across all user requests.
# Keeps a burst of users from hitting one site with dozens of requests.
PER_SOURCE_CONCURRENCY = 4
_scrape_sems: dict[str, asyncio.Semaphore] = {}

# Cache pre-warming: refresh the most-searched terms in the background so
# users almost never hit a cold scrape.
PREWARM_INTERVAL_SECONDS = 6 * 60 * 60
PREWARM_TOP_QUERIES = 20
PREWARM_WINDOW_DAYS = 30


# Per-source live-scrape health, keyed by source class name. Only real
# scrapes count — cache hits say nothing about whether the site still works.
_source_stats: dict[str, dict] = {}


def _note_outcome(source_name: str, error: str | None) -> None:
    st = _source_stats.setdefault(
        source_name,
        {"last_success": None, "last_error": None, "last_error_at": None, "consecutive_failures": 0},
    )
    if error is None:
        st["last_success"] = time.time()
        st["consecutive_failures"] = 0
    else:
        st["last_error"] = error
        st["last_error_at"] = time.time()
        st["consecutive_failures"] += 1


def _sem_for(source: BaseSource) -> asyncio.Semaphore:
    name = type(source).__name__
    sem = _scrape_sems.get(name)
    if sem is None:
        sem = _scrape_sems[name] = asyncio.Semaphore(PER_SOURCE_CONCURRENCY)
    return sem


async def _scrape(
    source: BaseSource, item: str
) -> tuple[list[NormalizedResult], str | None]:
    async with _sem_for(source):
        results, error = await source.search(item, SOURCE_FETCH_LIMIT)
    _note_outcome(type(source).__name__, error)
    return results, error


def _record_history(
    source: BaseSource, item: str, department: str | None, results: list[NormalizedResult]
) -> None:
    if results:
        asyncio.create_task(
            db.record_snapshots(results, item, department or source.department)
        )


def _schedule_refresh(
    key: str, source: BaseSource, item: str, department: str | None
) -> None:
    if key in _refreshing:
        return
    _refreshing.add(key)

    async def _refresh() -> None:
        try:
            results, error = await _scrape(source, item)
            if error is None:
                cache.set(key, results)
                _record_history(source, item, department, results)
            else:
                _recent_failures[key] = (time.monotonic() + FAILURE_COOLDOWN_SECONDS, error)
        finally:
            _refreshing.discard(key)

    asyncio.create_task(_refresh())


async def _search_with_cache(
    source: BaseSource, item: str, department: str | None
) -> tuple[list[NormalizedResult], str | None]:
    key = cache.make_key(source.__class__.__name__, item)
    cached = cache.get(key)
    if cached is not None:
        results, is_stale = cached
        if is_stale:
            _schedule_refresh(key, source, item, department)
        return results, None

    failed = _recent_failures.get(key)
    if failed is not None:
        retry_at, message = failed
        if time.monotonic() < retry_at:
            return [], message
        _recent_failures.pop(key, None)

    results, error = await _scrape(source, item)
    if error is None:
        cache.set(key, results)
        _recent_failures.pop(key, None)
        _record_history(source, item, department, results)
    else:
        _recent_failures[key] = (time.monotonic() + FAILURE_COOLDOWN_SECONDS, error)
    return results, error


async def _fan_out(
    item: str, department: str | None
) -> tuple[list[list[NormalizedResult]], list[str]]:
    """Query every applicable source concurrently (cache-aware)."""
    selected = [
        s for s in SOURCES
        if department is None or s.department is None or s.department == department
    ]
    outcomes = await asyncio.gather(
        *[_search_with_cache(source, item, department) for source in selected],
        return_exceptions=True,
    )

    per_source: list[list[NormalizedResult]] = []
    errors: list[str] = []
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            errors.append(f"Unexpected error: {outcome}")
            continue
        results, error = outcome
        if results:
            per_source.append(results)
        if error:
            errors.append(error)
    return per_source, errors


async def _prewarm_once() -> None:
    queries = await db.top_queries(PREWARM_TOP_QUERIES, PREWARM_WINDOW_DAYS)
    for query in queries:
        # Same fan-out as a real search: fresh entries are skipped, stale
        # ones refresh in the background, missing ones scrape now.
        await asyncio.gather(
            *[_search_with_cache(source, query, None) for source in SOURCES],
            return_exceptions=True,
        )
        await asyncio.sleep(2)  # be polite between fan-outs


async def _prewarm_loop() -> None:
    await asyncio.sleep(30)  # let the server finish starting up first
    while True:
        try:
            await _prewarm_once()
        except Exception:
            pass
        await asyncio.sleep(PREWARM_INTERVAL_SECONDS)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await db.init()
    prewarm_task = asyncio.create_task(_prewarm_loop())
    yield
    prewarm_task.cancel()
    await db.close()


app = FastAPI(
    title="PRISM Price Aggregator API",
    description=(
        "Philippine school/government procurement market scoping. "
        "Aggregates price data from PS-DBM and other official sources."
    ),
    version="1.2.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/search", response_model=SearchResponse, summary="Search for item prices")
async def search(
    item: Annotated[str, Query(description="Item name or keyword to search for", min_length=1)],
    limit: Annotated[int, Query(description="Maximum number of results to return", ge=1, le=100)] = 10,
    department: Annotated[
        Optional[Department],
        Query(description="Restrict search to sources serving this department; official PS-DBM sources are always included"),
    ] = None,
) -> SearchResponse:
    asyncio.create_task(db.log_search(item, department))

    per_source, errors = await _fan_out(item, department)

    # Round-robin across sources so later-registered sources still surface
    # instead of the first few sources consuming every slot.
    merged = []
    i = 0
    while len(merged) < limit:
        added = False
        for results in per_source:
            if i < len(results):
                merged.append(results[i])
                added = True
                if len(merged) >= limit:
                    break
        if not added:
            break
        i += 1

    return SearchResponse(
        query=item,
        limit=limit,
        total=len(merged),
        results=merged,
        errors=errors,
    )


@app.get("/canvass", summary="Generate a market canvass sheet (Excel)")
async def canvass(
    items: Annotated[
        list[str],
        Query(description="Item to canvass; repeat the parameter for multiple items", min_length=1, max_length=50),
    ],
    department: Annotated[Optional[Department], Query()] = None,
    quotes: Annotated[int, Query(description="Supplier quotes per item", ge=1, le=5)] = 3,
) -> Response:
    sheet_rows: list[tuple[str, list[NormalizedResult]]] = []
    for raw in items:
        item = raw.strip()
        if not item:
            continue
        asyncio.create_task(db.log_search(item, department))
        per_source, _ = await _fan_out(item, department)
        flat = [r for results in per_source for r in results]

        # Predictive search returns loosely related products (a "laptop"
        # query surfaces laptop sleeves), and pure price sorting favors
        # those accessories. Require every query word in the description;
        # fall back to unfiltered when the filter leaves nothing.
        words = [w for w in item.lower().split() if len(w) >= 3]
        relevant = [r for r in flat if all(w in r.description.lower() for w in words)]
        pool = relevant or flat

        cheapest_per_seller: dict[str, NormalizedResult] = {}
        for r in sorted(pool, key=lambda r: r.price_php):
            cheapest_per_seller.setdefault(r.seller, r)
        top = sorted(cheapest_per_seller.values(), key=lambda r: r.price_php)[:quotes]
        sheet_rows.append((item, top))

    filename = f"canvass_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return Response(
        content=build_canvass_xlsx(sheet_rows),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/admin/sources", summary="Per-source scraper health")
async def admin_sources(
    probe: Annotated[
        bool, Query(description="Live-test every source with a canary query right now")
    ] = False,
):
    if probe:
        async def _probe(source: BaseSource):
            async with _sem_for(source):
                try:
                    _, error = await source.search("paper", 3)
                except Exception as exc:
                    error = f"{type(source).__name__}: {exc}"
            _note_outcome(type(source).__name__, error)

        await asyncio.gather(*[_probe(s) for s in SOURCES])

    def _iso(ts: float | None) -> str | None:
        return datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None

    report = []
    for s in SOURCES:
        name = type(s).__name__
        st = _source_stats.get(name, {})
        consecutive = st.get("consecutive_failures", 0)
        if consecutive >= 2:
            status = "failing"
        elif st.get("last_success"):
            status = "ok"
        else:
            status = "unknown"
        report.append({
            "source": name,
            "department": s.department,
            "status": status,
            "last_success": _iso(st.get("last_success")),
            "last_error": st.get("last_error"),
            "last_error_at": _iso(st.get("last_error_at")),
            "consecutive_failures": consecutive,
        })

    failing = [r["source"] for r in report if r["status"] == "failing"]
    return {"total": len(report), "failing": failing, "sources": report}


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "sources": len(SOURCES)}
