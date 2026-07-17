"""orders 요청/응답 스키마."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class OrderItemView(BaseModel):
    product_id: int
    name: str
    qty: int
    unit_price: Decimal


class OrderView(BaseModel):
    id: int
    status: str
    total_amount: Decimal
    created_at: datetime
    items: list[OrderItemView]


class OrderListResponse(BaseModel):
    user_id: int
    order_count: int
    orders: list[OrderView]


class CreateOrderResponse(BaseModel):
    id: int
    status: str
    total_amount: Decimal


class RankingEntry(BaseModel):
    product_id: int
    name: str
    sold_qty: int
