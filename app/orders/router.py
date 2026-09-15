from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_current_user
from app.core.deps import get_db
from app.models import User
from app.orders import schemas, service

router = APIRouter(prefix="/orders", tags=["orders"])
rankings_router = APIRouter(prefix="/rankings", tags=["rankings"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=schemas.CreateOrderResponse)
async def create_order(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> schemas.CreateOrderResponse:
    order = await service.create_order_from_cart(session, user)
    return schemas.CreateOrderResponse(
        id=order.id, status=order.status, total_amount=order.total_amount
    )


@router.get("", response_model=schemas.OrderListResponse)
async def list_orders(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> schemas.OrderListResponse:
    return await service.list_orders(session, user)


@router.get("/{order_id}", response_model=schemas.OrderView)
async def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> schemas.OrderView:
    view = await service.get_order_detail(session, user, order_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    return view


@rankings_router.get("/realtime", response_model=list[schemas.RankingEntry])
async def realtime(
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[schemas.RankingEntry]:
    return await service.realtime_ranking(session, limit)
