from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NormalizedResult(BaseModel):
    item: str
    source: str
    product_code: str
    description: str
    uom: str
    price_php: float
    seller: str
    is_official: bool
    url: str
    image_url: Optional[str] = None
    scraped_at: datetime


class SearchResponse(BaseModel):
    query: str
    limit: int
    total: int
    results: list[NormalizedResult]
    errors: list[str]
