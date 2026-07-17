"""deals 라우터 — 선착순 딜 구매."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_current_user
from app.core.deps import get_db
from app.deals import schemas, service
from app.models import User

router = APIRouter(prefix="/deals", tags=["deals"])


@router.post("/{deal_id}/purchase", response_model=schemas.PurchaseResponse)
async def purchase(
    deal_id: int,
    body: schemas.PurchaseRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> schemas.PurchaseResponse:
    order, deal = await service.purchase(session, user, deal_id, body.qty)
    return schemas.PurchaseResponse(
        deal_id=deal.id, order_id=order.id, qty=body.qty, remaining_qty=deal.remaining_qty
    )
