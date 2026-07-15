import asyncio
import io
import re
import time
from datetime import datetime, timezone, timedelta

import httpx
import openpyxl
from bs4 import BeautifulSoup

from app.models import NormalizedResult
from app.sources.base import BaseSource
from app.sources._common import get_client, words_match, HTTP_TIMEOUT

_DOWNLOADS_URL = "https://www.ps-philgeps.gov.ph/home/index.php/downloads"
_SOURCE_PAGE = "https://www.ps-philgeps.gov.ph/home/index.php/what-we-sell/3-pricelist"
_BASE_URL = "https://www.ps-philgeps.gov.ph"
_SELLER = "Procurement Service (PS-DBM)"
_TZ_MNL = timezone(timedelta(hours=8))

# Fallback if scraping the downloads page fails
_FALLBACK_XLSX_PATH = "/home/images/Downloads/2025/APP-CSE 2026 Form.xlsx"

# One Excel download a day instead of one per new search term; see psdbm.py.
_CATALOGUE_TTL = 24 * 60 * 60
_STALE_GRACE = 7 * 24 * 60 * 60


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


def _year_in(s: str) -> int:
    """Return the highest 4-digit year found in a string, else 0."""
    years = re.findall(r"20\d{2}", s)
    return max(int(y) for y in years) if years else 0


class PSDBMExcelSource(BaseSource):
    def __init__(self) -> None:
        # (product_code, description, uom, price) per pricelist item
        self._rows: list[tuple[str, str, str, float]] | None = None
        self._loaded_at = 0.0
        self._scraped_at = _now_mnl()
        self._lock = asyncio.Lock()

    async def _resolve_xlsx_url(self, client: httpx.AsyncClient) -> tuple[str, bool]:
        """Scrape the downloads page for the latest APP-CSE form link.

        Returns (url, used_fallback) — used_fallback means the page scrape
        failed and the hardcoded (possibly outdated-year) path is in use.
        """
        try:
            resp = await client.get(_DOWNLOADS_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            candidates: list[str] = []
            for a in soup.find_all("a", href=True):
                href: str = a["href"]
                combined = href + a.get_text(" ", strip=True)
                if href.lower().endswith(".xlsx") and "app-cse" in combined.lower():
                    candidates.append(href)
            if candidates:
                # Prefer the link referencing the highest year
                candidates.sort(key=_year_in, reverse=True)
                href = candidates[0]
                url = (_BASE_URL + href) if href.startswith("/") else href
                return url, False
        except Exception:
            pass
        return _BASE_URL + _FALLBACK_XLSX_PATH, True

    async def _get_catalogue(self) -> tuple[list[tuple[str, str, str, float]], str | None]:
        """Returns (rows, warning-or-error).

        rows + warning together means the catalogue loaded but via the
        hardcoded fallback file — surfaced once so /admin/sources shows it.
        """
        async with self._lock:
            age = time.monotonic() - self._loaded_at
            if self._rows is not None and age < _CATALOGUE_TTL:
                return self._rows, None

            used_fallback = False
            try:
                client = get_client()
                xlsx_url, used_fallback = await self._resolve_xlsx_url(client)
                resp = await client.get(xlsx_url)
                resp.raise_for_status()
                rows = self._parse_xlsx(resp.content)
            except httpx.TimeoutException:
                error = f"PS-DBM Pricelist: request timed out after {HTTP_TIMEOUT}s"
            except httpx.HTTPStatusError as exc:
                error = f"PS-DBM Pricelist: HTTP {exc.response.status_code} from Excel URL"
            except Exception as exc:
                error = f"PS-DBM Pricelist: download/parse failed — {exc}"
            else:
                self._rows = rows
                self._loaded_at = time.monotonic()
                self._scraped_at = _now_mnl()
                if used_fallback:
                    return rows, (
                        "PS-DBM Pricelist: downloads-page scrape failed; using the "
                        "hardcoded APP-CSE 2026 fallback file — baka hindi na ito "
                        "ang pinakabagong pricelist"
                    )
                return rows, None

            if self._rows is not None and age < _CATALOGUE_TTL + _STALE_GRACE:
                return self._rows, None  # refresh failed; serve the last good copy
            return [], error

    async def search(self, query: str, limit: int) -> tuple[list[NormalizedResult], str | None]:
        rows, error = await self._get_catalogue()
        if error is not None and not rows:
            return [], error

        results: list[NormalizedResult] = []
        for product_code, description, uom, price in rows:
            if not words_match(query, description.lower()):
                continue
            results.append(NormalizedResult(
                item=query,
                source="PS-DBM Pricelist",
                product_code=product_code,
                description=description,
                uom=uom,
                price_php=price,
                seller=_SELLER,
                is_official=True,
                url=_SOURCE_PAGE,
                scraped_at=self._scraped_at,
            ))
            if len(results) >= limit:
                break
        return results, error

    def _parse_xlsx(self, xlsx_bytes: bytes) -> list[tuple[str, str, str, float]]:
        rows: list[tuple[str, str, str, float]] = []

        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
        ws = wb.active

        # Single-pass: detect header row, then stream data rows.
        # APP-CSE form layout (stable across years):
        #   col 0 = row number  |  col 1 = product_code  |  col 2 = description
        #   col 3 = UOM  |  col ~25 = "Unit Price as of …"
        # Header detection relies on finding a row containing "unit price".

        price_col: int | None = None
        uom_col: int = 3
        in_data = False
        subheader_skip = 0  # rows to skip after the header row (sub-header row)

        for row in ws.iter_rows(values_only=True):
            if not in_data:
                row_text = " ".join(str(v).lower() for v in row if v is not None)
                if "unit price" in row_text:
                    for j, v in enumerate(row):
                        if v is None:
                            continue
                        s = str(v).lower()
                        if "unit price" in s and "amount" not in s:
                            price_col = j
                        elif "unit of measure" in s:
                            uom_col = j
                    in_data = True
                continue

            # Skip the sub-header row that immediately follows the main header
            if subheader_skip < 1:
                subheader_skip += 1
                continue

            if price_col is None or not row or len(row) <= price_col:
                continue

            raw_desc = row[2]
            if not raw_desc:
                continue
            description = str(raw_desc).strip()
            if not description:
                continue

            # Section header rows have content only in col 0; col 1/2 are None
            if row[1] is None:
                continue

            price = _clean_price(row[price_col])
            if price is None or price <= 0:
                continue

            product_code = str(row[1]).strip() if row[1] else ""
            uom = str(row[uom_col]).strip() if len(row) > uom_col and row[uom_col] else ""

            rows.append((product_code, description, uom, price))

        return rows
