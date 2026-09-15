from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_current_user
from app.cart import schemas, service
from app.core.deps import get_db
from app.models import User

router = APIRouter(prefix="/cart", tags=["cart"])


@router.post("/items", status_code=status.HTTP_201_CREATED, response_model=schemas.CartResponse)
async def add_item(
    body: schemas.AddCartItemRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> schemas.CartResponse:
    await service.add_item(session, user.id, body.product_id, body.qty)
    return await service.get_cart(session, user.id)


@router.get("", response_model=schemas.CartResponse)
async def get_cart(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> schemas.CartResponse:
    return await service.get_cart(session, user.id)
