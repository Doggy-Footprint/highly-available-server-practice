from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class AddCartItemRequest(BaseModel):
    product_id: int
    qty: int = Field(default=1, ge=1)


class CartItemView(BaseModel):
    product_id: int
    name: str
    price: Decimal
    qty: int


class CartResponse(BaseModel):
    user_id: int
    item_count: int
    items: list[CartItemView]
