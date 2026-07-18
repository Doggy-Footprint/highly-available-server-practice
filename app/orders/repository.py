"""orders 데이터 접근.

주문 생성(건별 commit·임의 순서 재고 차감), 주문 조회(selectinload 로 items·product 를
한 번에 적재), 실시간 랭킹(집계)의 저수준 쿼리들.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem, OrderStatus, Payment, PaymentStatus, Product


async def create_order(session: AsyncSession, user_id: int) -> Order:
    order = Order(user_id=user_id, status=OrderStatus.PENDING, total_amount=Decimal(0))
    session.add(order)
    await session.commit()  # 주문 헤더를 먼저 커밋해 order.id 를 확보한다
    await session.refresh(order)
    return order


async def decrement_stock(session: AsyncSession, product_id: int, qty: int) -> None:
    # 재고 차감 한 건. 호출부(service)가 카트 순서대로 이걸 반복하면서 상품 로우 락을
    # 임의 순서로 잡는다 — P2-03 의 소재다.
    await session.execute(
        update(Product).where(Product.id == product_id).values(stock=Product.stock - qty)
    )


async def add_order_item(
    session: AsyncSession, order_id: int, product_id: int, qty: int, unit_price: Decimal
) -> None:
    session.add(OrderItem(order_id=order_id, product_id=product_id, qty=qty, unit_price=unit_price))


async def set_order_total(session: AsyncSession, order_id: int, total: Decimal) -> None:
    await session.execute(update(Order).where(Order.id == order_id).values(total_amount=total))


async def create_payment(
    session: AsyncSession, order_id: int, status: PaymentStatus, pg_tx_id: str
) -> None:
    session.add(Payment(order_id=order_id, status=status, pg_tx_id=pg_tx_id))


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    return (await session.scalars(stmt)).first()


async def get_order_for_update(session: AsyncSession, order_id: int) -> Order | None:
    # SELECT ... FOR UPDATE — 주문 로우 락을 잡은 채 반환한다. `session.get` 과 달리
    # identity map 에 객체가 있어도 반드시 SQL 이 나가므로, 호출 시점의 트랜잭션이
    # 커넥션을 체크아웃해 커밋까지 쥐게 된다. P1-07(트랜잭션 안 결제 호출)의 소재.
    stmt = select(Order).where(Order.id == order_id).with_for_update()
    return (await session.scalars(stmt)).first()


async def list_orders_for_user(session: AsyncSession, user_id: int) -> Sequence[Order]:
    # INTENDED-ISSUE: P1-11
    # LIMIT 없이 유저의 주문 전체를 가져온다. seed 의 헤비 유저(3,000건)면 이 한 방에
    # 수천 로우가 나온다. 이어지는 N+1(service) 과 겹쳐 응답 크기·쿼리 수가 동시에 폭증한다.
    # (P1-02 와 독립 검증: fix 는 강제 페이지네이션 + max_limit.)
    stmt = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.id.desc())
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    return (await session.scalars(stmt)).all()


async def ranking_realtime(
    session: AsyncSession, since: datetime, limit: int
) -> Sequence[tuple[int, str, int]]:
    # INTENDED-ISSUE: P2-09
    # 요청마다 orders x order_items 를 상품별로 GROUP BY 해서 실시간 랭킹을 만든다.
    # 인덱스 없는 orders.created_at 필터 + 대량 집계라, 주문 트래픽과 동시에 돌면
    # OLTP(주문 경로)를 간섭한다. fix 에서 Redis sorted set 집계(또는 배치 테이블/replica 격리).
    sold = func.sum(OrderItem.qty).label("sold")
    stmt = (
        select(Product.id, Product.name, sold)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status != OrderStatus.FAILED, Order.created_at >= since)
        .group_by(Product.id, Product.name)
        .order_by(sold.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(int(r[0]), str(r[1]), int(r[2])) for r in rows]
