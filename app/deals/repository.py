"""deals 데이터 접근."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Deal, Order, OrderItem, OrderStatus


async def get_deal(session: AsyncSession, deal_id: int) -> Deal | None:
    return await session.get(Deal, deal_id)


async def create_deal_order(session: AsyncSession, user_id: int, deal: Deal, qty: int) -> Order:
    # 딜 판매를 order_items 에 기록한다 — oversell 검증(load/checks/oversell.sql)이
    # "deals.product_id 를 참조하는 order_items 의 합" 으로 판매량을 세기 때문이다.
    total = deal.deal_price * qty
    order = Order(user_id=user_id, status=OrderStatus.PAID, total_amount=total)
    session.add(order)
    await session.flush()  # order.id 확보
    session.add(
        OrderItem(
            order_id=order.id, product_id=deal.product_id, qty=qty, unit_price=deal.deal_price
        )
    )
    return order


async def decrement_remaining(session: AsyncSession, deal_id: int, qty: int) -> None:
    # P2-01 의 ACT 부분. `AND remaining_qty >= qty` 가드가 없어서, 이미 stale 해진
    # 앱-레벨 검사를 통과한 여러 요청이 전부 여기까지 내려와 재고를 음수로 만든다.
    await session.execute(
        update(Deal).where(Deal.id == deal_id).values(remaining_qty=Deal.remaining_qty - qty)
    )
