from __future__ import annotations

from pydantic import BaseModel, Field


class PurchaseRequest(BaseModel):
    qty: int = Field(default=1, ge=1)


class PurchaseResponse(BaseModel):
    deal_id: int
    order_id: int
    qty: int
    remaining_qty: int
