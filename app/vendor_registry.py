"""
Persistent store for manually-submitted vendor sources awaiting approval.

Mirrors the SQLite pattern in cache.py, reusing the same DB file. A vendor
starts "pending" after successful platform detection (see
app/sources/discovery.py) and only becomes part of the live SOURCES list
once approved via /admin/vendors/{id}/approve.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "price_cache.sqlite3"

_db = sqlite3.connect(_DB_PATH, check_same_thread=False)
_db.execute(
    """
    CREATE TABLE IF NOT EXISTS vendor_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        base_url TEXT UNIQUE NOT NULL,
        seller TEXT NOT NULL,
        department TEXT,
        platform TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        decided_at TEXT
    )
    """
)
_db.commit()


@dataclass
class VendorSource:
    id: int
    base_url: str
    seller: str
    department: str | None
    platform: str
    status: str
    created_at: str
    decided_at: str | None


_COLUMNS = "id, base_url, seller, department, platform, status, created_at, decided_at"


def _row_to_vendor(row: tuple) -> VendorSource:
    return VendorSource(*row)


def add_pending(base_url: str, seller: str, department: str | None, platform: str) -> VendorSource:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = _db.execute(
        "INSERT INTO vendor_sources (base_url, seller, department, platform, status, created_at)"
        " VALUES (?, ?, ?, ?, 'pending', ?)",
        (base_url, seller, department, platform, now),
    )
    _db.commit()
    return get(cur.lastrowid)


def get(vendor_id: int) -> VendorSource | None:
    row = _db.execute(
        f"SELECT {_COLUMNS} FROM vendor_sources WHERE id = ?", (vendor_id,)
    ).fetchone()
    return _row_to_vendor(row) if row else None


def get_by_base_url(base_url: str) -> VendorSource | None:
    row = _db.execute(
        f"SELECT {_COLUMNS} FROM vendor_sources WHERE base_url = ?", (base_url,)
    ).fetchone()
    return _row_to_vendor(row) if row else None


def list_pending() -> list[VendorSource]:
    rows = _db.execute(
        f"SELECT {_COLUMNS} FROM vendor_sources WHERE status = 'pending' ORDER BY created_at"
    ).fetchall()
    return [_row_to_vendor(r) for r in rows]


def list_approved() -> list[VendorSource]:
    rows = _db.execute(
        f"SELECT {_COLUMNS} FROM vendor_sources WHERE status = 'approved' ORDER BY created_at"
    ).fetchall()
    return [_row_to_vendor(r) for r in rows]


def approve(vendor_id: int, department: str | None = None) -> VendorSource | None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if department is not None:
        _db.execute(
            "UPDATE vendor_sources SET status = 'approved', decided_at = ?, department = ?"
            " WHERE id = ? AND status = 'pending'",
            (now, department, vendor_id),
        )
    else:
        _db.execute(
            "UPDATE vendor_sources SET status = 'approved', decided_at = ?"
            " WHERE id = ? AND status = 'pending'",
            (now, vendor_id),
        )
    _db.commit()
    return get(vendor_id)


def reject(vendor_id: int) -> VendorSource | None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _db.execute(
        "UPDATE vendor_sources SET status = 'rejected', decided_at = ?"
        " WHERE id = ? AND status = 'pending'",
        (now, vendor_id),
    )
    _db.commit()
    return get(vendor_id)
