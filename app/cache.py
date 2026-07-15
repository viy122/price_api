"""
TTL cache for per-source search results, persisted to SQLite.

Repeated searches for the same term within the TTL window skip the live
scrape entirely. Only successful source responses are stored — timeouts and
failures always retry live on the next request. Cached empty lists ARE
stored (the site genuinely had no match for the query).

Entries past their TTL are kept for a grace window and reported as stale so
callers can serve them immediately while refreshing in the background
(stale-while-revalidate). The SQLite mirror means the cache survives server
restarts and redeploys; expirations use wall-clock time for that reason.
"""

import json
import sqlite3
import time
from pathlib import Path

from app.models import NormalizedResult

TTL_SECONDS = 12 * 60 * 60  # fresh window: 12 hours
STALE_GRACE_SECONDS = 7 * 24 * 60 * 60  # serve stale up to 7 days past TTL

_DB_PATH = Path(__file__).resolve().parent.parent / "price_cache.sqlite3"

# key -> (expires_at, results)
_store: dict[str, tuple[float, list[NormalizedResult]]] = {}

_db = sqlite3.connect(_DB_PATH, check_same_thread=False)
_db.execute(
    "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, expires_at REAL, results TEXT)"
)
_db.commit()


def _load_from_disk() -> None:
    hard_deadline = time.time() - STALE_GRACE_SECONDS
    _db.execute("DELETE FROM cache WHERE expires_at < ?", (hard_deadline,))
    _db.commit()
    for key, expires_at, raw in _db.execute("SELECT key, expires_at, results FROM cache"):
        try:
            results = [NormalizedResult.model_validate(r) for r in json.loads(raw)]
        except Exception:
            continue  # schema changed or row corrupted — drop silently, will re-scrape
        _store[key] = (expires_at, results)


_load_from_disk()


def make_key(source_name: str, query: str) -> str:
    return f"{source_name}:{query.lower().strip()}"


def get(key: str) -> tuple[list[NormalizedResult], bool] | None:
    """Return (results, is_stale), or None on a miss.

    Stale entries (past TTL but within the grace window) are still returned;
    the caller is expected to refresh them in the background.
    """
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, results = entry
    now = time.time()
    if now >= expires_at + STALE_GRACE_SECONDS:
        _store.pop(key, None)
        _db.execute("DELETE FROM cache WHERE key = ?", (key,))
        _db.commit()
        return None
    return results, now >= expires_at


def set(key: str, results: list[NormalizedResult]) -> None:
    _purge_expired()
    expires_at = time.time() + TTL_SECONDS
    _store[key] = (expires_at, results)
    raw = json.dumps([r.model_dump(mode="json") for r in results])
    _db.execute(
        "INSERT OR REPLACE INTO cache (key, expires_at, results) VALUES (?, ?, ?)",
        (key, expires_at, raw),
    )
    _db.commit()


def _purge_expired() -> None:
    hard_deadline = time.time() - STALE_GRACE_SECONDS
    for key in [k for k, (exp, _) in _store.items() if exp < hard_deadline]:
        _store.pop(key, None)
    _db.execute("DELETE FROM cache WHERE expires_at < ?", (hard_deadline,))
    _db.commit()
