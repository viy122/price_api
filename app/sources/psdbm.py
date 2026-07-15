import asyncio
import io
import re
import time
from datetime import datetime, timezone, timedelta

import httpx
import pdfplumber

from app.models import NormalizedResult
from app.sources.base import BaseSource
from app.sources._common import get_client, words_match, HTTP_TIMEOUT

_CATALOGUE_URL = "https://sys.ps-philgeps.gov.ph/catalogue/cse-list/"
_SELLER = "Procurement Service (PS-DBM)"
_TZ_MNL = timezone(timedelta(hours=8))

# The catalogue is query-independent: download + parse it once and answer
# every query from memory. One PDF download a day instead of one per new
# search term.
_CATALOGUE_TTL = 24 * 60 * 60
# When a refresh fails, keep serving the last good catalogue up to this long
# past its TTL — old official prices beat none. Beyond it, report the error.
_STALE_GRACE = 7 * 24 * 60 * 60


def _now_mnl() -> datetime:
    return datetime.now(_TZ_MNL)


def _clean_price(raw: str) -> float | None:
    cleaned = re.sub(r"[^\d.]", "", str(raw).strip())
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _find_col_indices(header_row: list) -> dict[str, int] | None:
    """Return column index map from a header row, or None if unrecognised."""
    mapping = {}
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        val = str(cell).lower().strip()
        if "product code" in val or val == "code":
            mapping["product_code"] = i
        elif "description" in val:
            mapping["description"] = i
        elif "uom" in val or "unit of measure" in val:
            mapping["uom"] = i
        elif "price" in val:
            mapping["price"] = i
    required = {"product_code", "description", "uom", "price"}
    return mapping if required.issubset(mapping) else None


class PSDBMSource(BaseSource):
    def __init__(self) -> None:
        # (product_code, description, uom, price) per catalogue item
        self._rows: list[tuple[str, str, str, float]] | None = None
        self._loaded_at = 0.0
        self._scraped_at = _now_mnl()
        self._lock = asyncio.Lock()

    async def _get_catalogue(self) -> tuple[list[tuple[str, str, str, float]], str | None]:
        async with self._lock:
            age = time.monotonic() - self._loaded_at
            if self._rows is not None and age < _CATALOGUE_TTL:
                return self._rows, None

            try:
                resp = await get_client().get(_CATALOGUE_URL)
                resp.raise_for_status()
                rows = self._parse_pdf(resp.content)
            except httpx.TimeoutException:
                error = f"PS-DBM: request timed out after {HTTP_TIMEOUT}s"
            except httpx.HTTPStatusError as exc:
                error = f"PS-DBM: HTTP {exc.response.status_code} from catalogue URL"
            except Exception as exc:
                error = f"PS-DBM: catalogue download/parse failed — {exc}"
            else:
                self._rows = rows
                self._loaded_at = time.monotonic()
                self._scraped_at = _now_mnl()
                return rows, None

            if self._rows is not None and age < _CATALOGUE_TTL + _STALE_GRACE:
                return self._rows, None  # refresh failed; serve the last good copy
            return [], error

    async def search(self, query: str, limit: int) -> tuple[list[NormalizedResult], str | None]:
        rows, error = await self._get_catalogue()
        if error is not None:
            return [], error

        results: list[NormalizedResult] = []
        for product_code, description, uom, price in rows:
            if not words_match(query, description.lower()):
                continue
            results.append(NormalizedResult(
                item=query,
                source="PS-DBM",
                product_code=product_code,
                description=description,
                uom=uom,
                price_php=price,
                seller=_SELLER,
                is_official=True,
                url=_CATALOGUE_URL,
                scraped_at=self._scraped_at,
            ))
            if len(results) >= limit:
                break
        return results, None

    def _parse_pdf(self, pdf_bytes: bytes) -> list[tuple[str, str, str, float]]:
        rows: list[tuple[str, str, str, float]] = []
        col: dict[str, int] | None = None

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if not table:
                    continue

                for row in table:
                    if row is None or all(c is None or str(c).strip() == "" for c in row):
                        continue

                    # (Re-)detect header row on every page — PS-DBM repeats it
                    candidate = _find_col_indices(row)
                    if candidate is not None:
                        col = candidate
                        continue

                    if col is None:
                        continue

                    def get(key: str) -> str:
                        idx = col.get(key)  # type: ignore[union-attr]
                        if idx is None or idx >= len(row) or row[idx] is None:
                            return ""
                        return str(row[idx]).strip()

                    description = get("description")
                    if not description:
                        continue

                    price = _clean_price(get("price"))
                    if price is None or price <= 0:
                        continue

                    rows.append((get("product_code"), description, get("uom"), price))

        return rows
