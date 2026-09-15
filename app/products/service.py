from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.products import repository, schemas


async def list_products(
    session: AsyncSession, q: str | None, category_id: int | None, page: int, size: int
) -> schemas.ProductListResponse:
    items = await repository.search_products(session, q, category_id, page, size)
    # P1-05: 목록을 뽑은 뒤 total 을 또 COUNT(*) 로 구한다 (매 요청).
    total = await repository.count_products(session, q, category_id)
    return schemas.ProductListResponse(
        total=total,
        page=page,
        size=size,
        items=[
            schemas.ProductSummary(
                id=p.id, category_id=p.category_id, name=p.name, price=p.price, stock=p.stock
            )
            for p in items
        ],
    )


async def get_product_detail(
    session: AsyncSession, product_id: int
) -> schemas.ProductDetail | None:
    product = await repository.get_product(session, product_id)
    if product is None:
        return None
    review_count, avg_rating = await repository.review_stats(session, product_id)
    return schemas.ProductDetail(
        id=product.id,
        category_id=product.category_id,
        name=product.name,
        description=product.description,
        price=product.price,
        stock=product.stock,
        created_at=product.created_at,
        review_count=review_count,
        avg_rating=avg_rating,
    )


async def popular(session: AsyncSession, limit: int) -> list[schemas.PopularProduct]:
    rows = await repository.popular_products(session, limit)
    return [
        schemas.PopularProduct(product_id=pid, name=name, sold_qty=sold) for pid, name, sold in rows
    ]
