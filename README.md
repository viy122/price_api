# prism-price-api

Philippine school/government procurement market scoping API.

## Setup

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000 --reload
```

## Usage

```
GET /search?item=printer&limit=5
GET /health
GET /docs   ← Swagger UI
```

## Sources

| Source | Method | URL |
|--------|--------|-----|
| PS-DBM CSE Catalogue | PDF scrape | https://sys.ps-philgeps.gov.ph/catalogue/cse-list/ |

## Adding a new source

1. Create `app/sources/mysource.py` extending `BaseSource`
2. Implement `async def search(self, query, limit) -> tuple[list[NormalizedResult], str | None]`
3. Add to `SOURCES` list in `app/sources/__init__.py`
