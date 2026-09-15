from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.cart import repository, schemas


async def add_item(session: AsyncSession, user_id: int, product_id: int, qty: int) -> None:
    await repository.upsert_cart_item(session, user_id, product_id, qty)


async def get_cart(session: AsyncSession, user_id: int) -> schemas.CartResponse:
    rows = await repository.get_cart_items(session, user_id)
    items = [
        schemas.CartItemView(
            product_id=product.id, name=product.name, price=product.price, qty=cart_item.qty
        )
        for cart_item, product in rows
    ]
    return schemas.CartResponse(user_id=user_id, item_count=len(items), items=items)
