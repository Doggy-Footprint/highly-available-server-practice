from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ProductSummary(BaseModel):
    id: int
    category_id: int
    name: str
    price: Decimal
    stock: int


class ProductListResponse(BaseModel):
    total: int  # P1-05: 매 요청 COUNT(*) 로 채운다
    page: int
    size: int
    items: list[ProductSummary]


class ProductDetail(BaseModel):
    id: int
    category_id: int
    name: str
    description: str
    price: Decimal
    stock: int
    created_at: datetime
    review_count: int
    avg_rating: float | None


class PopularProduct(BaseModel):
    product_id: int
    name: str
    sold_qty: int
