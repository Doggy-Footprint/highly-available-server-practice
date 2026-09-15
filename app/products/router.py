from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.products import schemas, service

router = APIRouter(prefix="/products", tags=["products"])
main_router = APIRouter(prefix="/main", tags=["main"])


@router.get("", response_model=schemas.ProductListResponse)
async def list_products(
    category: int | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> schemas.ProductListResponse:
    return await service.list_products(session, q, category, page, size)


@router.get("/{product_id}", response_model=schemas.ProductDetail)
async def get_product(
    product_id: int, session: AsyncSession = Depends(get_db)
) -> schemas.ProductDetail:
    detail = await service.get_product_detail(session, product_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return detail


@main_router.get("/popular", response_model=list[schemas.PopularProduct])
async def popular(
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[schemas.PopularProduct]:
    return await service.popular(session, limit)
