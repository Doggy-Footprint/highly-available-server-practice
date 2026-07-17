"""cart 데이터 접근."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CartItem, Product


async def upsert_cart_item(session: AsyncSession, user_id: int, product_id: int, qty: int) -> None:
    existing = await session.get(CartItem, (user_id, product_id))
    if existing is None:
        session.add(CartItem(user_id=user_id, product_id=product_id, qty=qty))
    else:
        existing.qty += qty
    await session.commit()


async def get_cart_items(session: AsyncSession, user_id: int) -> Sequence[tuple[CartItem, Product]]:
    # INTENDED-ISSUE: P1-11
    # 유저 카트를 LIMIT 없이 통째로 반환한다. 상한(max_limit)이 없어 카트가 큰 유저면
    # 직렬화·메모리가 응답 크기에 비례해 커진다. fix 에서 강제 페이지네이션 + 상한.
    # (주문 생성 플로우도 이 함수로 카트를 읽는다 — 거기선 크기보다 순서가 P2-03 소재다.)
    stmt = (
        select(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.user_id == user_id)
    )
    # .tuples() 로 Row 가 아니라 (CartItem, Product) 튜플 시퀀스로 받는다 (타입 정합).
    return (await session.execute(stmt)).tuples().all()
