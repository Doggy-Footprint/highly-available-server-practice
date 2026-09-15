from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, text
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
    #
    # INTENDED-ISSUE: P2-03
    # 카트를 "담은 순서"로 반환한다. §1 스키마의 cart_items 엔 담은 시각 컬럼이 없으므로
    # ctid(물리 삽입 순서)로 그 순서를 표현한다 — 실험 장치임을 명시해 둔다.
    # 이 순서가 문제인 이유: 주문 생성이 반환 순서 그대로 재고 락을 잡는데(orders/service),
    # ORDER BY 없이 두면 PG 가 PK(user_id, product_id) 인덱스 순서(= product_id 정렬)로
    # 돌려줘 사실상 "PK 정렬 후 잠금"(= P2-03 의 fix 상태)이 되어 deadlock 이 아예 성립
    # 하지 않는다. 담은 순서를 유지해야 교차 카트의 락 순서가 실제로 엇갈린다.
    # (한계: upsert 로 qty 가 갱신되면 새 튜플로 ctid 가 바뀌어 순서가 흐트러진다 —
    #  재현 시나리오는 새로 담은 카트를 쓴다.)
    stmt = (
        select(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.user_id == user_id)
        .order_by(text("cart_items.ctid"))
    )
    # .tuples() 로 Row 가 아니라 (CartItem, Product) 튜플 시퀀스로 받는다 (타입 정합).
    return (await session.execute(stmt)).tuples().all()
