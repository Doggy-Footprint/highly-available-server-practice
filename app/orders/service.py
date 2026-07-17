"""orders 도메인 로직.

주문 생성 플로우 하나에 여러 문제가 겹쳐 심겨 있다:
  P2-04  멱등성 부재 (같은 카트로 두 번 → 주문 두 개)
  P2-03  재고 차감 락을 카트 순서(임의)로 획득
  P1-08  order_items 를 건별 INSERT + 건별 commit
  P1-07  결제를 DB 트랜잭션 안에서 호출 (+ payments.client 의 P1-06/P2-07)
조회 플로우에는:
  P1-11  LIMIT 없는 전체 조회 (repository)
  P1-02  주문→아이템→상품 루프 개별 조회 (N+1)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart import repository as cart_repo
from app.models import Order, OrderStatus, PaymentStatus, User
from app.orders import repository, schemas
from app.payments import client as payment_client
from app.products import repository as product_repo

# 실시간 랭킹 집계 창(P2-09). 최근 이만큼의 주문만 집계한다.
_RANKING_WINDOW = timedelta(days=7)


async def create_order_from_cart(session: AsyncSession, user: User) -> Order:
    rows = await cart_repo.get_cart_items(session, user.id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cart is empty")

    # INTENDED-ISSUE: P2-04
    # 멱등성 장치가 없다. 같은 유저가 같은 카트로 POST /orders 를 두 번(더블클릭/재시도)
    # 보내면 주문이 두 개 생긴다 — 카트를 비우지도, Idempotency-Key 를 확인하지도 않는다.
    # (dup_orders.sql 이 "같은 유저·같은 아이템 구성·수 초 내" 짝으로 이걸 잡는다.)
    # fix 에서 Idempotency-Key 헤더 + unique 제약 + 응답 재생.
    order = await repository.create_order(session, user.id)

    total = Decimal(0)
    # INTENDED-ISSUE: P2-03
    # 재고 차감 락을 카트에 담은 순서(cart repository 가 ctid=삽입 순서로 반환)로
    # 획득한다. 같은 상품 쌍을 반대 순서로 담은 두 카트(seed 의 교차 카트 쌍)가 동시에
    # 주문하면 락 획득 순서가 엇갈려 deadlock 이 난다.
    # 지금은 아래 P1-08 의 건별 commit 이 매 아이템마다 락을 즉시 풀어 마스킹되어 있고,
    # P1-08 fix 로 트랜잭션이 하나로 합쳐지면 그때 발현한다. fix 는 PK 정렬 후 잠금.
    for cart_item, product in rows:
        await repository.decrement_stock(session, product.id, cart_item.qty)
        await repository.add_order_item(session, order.id, product.id, cart_item.qty, product.price)
        total += product.price * cart_item.qty
        # INTENDED-ISSUE: P1-08
        # 아이템을 한 건씩 INSERT 하고 건마다 commit 한다. 아이템 10개면 INSERT 10 왕복 +
        # commit 10회. fix 에서 단일 트랜잭션 + bulk insert 로 주문당 왕복 1회.
        await session.commit()

    await repository.set_order_total(session, order.id, total)
    await session.commit()

    # INTENDED-ISSUE: P1-07
    # 결제(외부 API)를 DB 트랜잭션 안에서 호출한다. "결제하는 동안 주문이 안 바뀌게"
    # SELECT ... FOR UPDATE 로 주문 로우를 잠근 뒤(이때 실제 SQL 이 나가 커넥션이
    # 체크아웃된다), 그 커넥션과 로우 락을 쥔 채 동기 결제(P1-06, ~800ms)를 기다린다.
    # 풀 기본값(pool_size=5 + max_overflow=10)에 주문 200vu 면 pool timeout 이 쏟아진다.
    # (주의: identity map 히트인 session.get 은 SQL 이 안 나가 커넥션을 잡지 않는다 —
    #  verify-break 에서 그 형태로는 문제가 성립하지 않음을 확인하고 FOR UPDATE 로 재심음.)
    # fix 에서 결제를 트랜잭션 밖으로 빼고 주문 상태머신(PENDING→PAID)으로 분리한다.
    async with session.begin():
        locked = await repository.get_order_for_update(session, order.id)  # 커넥션+로우 락 점유
        result = payment_client.pay(order.id, float(total))  # P1-06 블로킹 + P2-07 재시도
        if locked is not None:
            locked.status = OrderStatus.PAID
        await repository.create_payment(session, order.id, PaymentStatus.PAID, result["pg_tx_id"])

    await session.refresh(order)
    return order


async def _build_order_view(session: AsyncSession, order: Order) -> schemas.OrderView:
    # INTENDED-ISSUE: P1-02
    # 주문마다 아이템을 개별 쿼리로, 아이템마다 상품을 또 개별 쿼리로 가져온다 (N+1).
    # 주문 N개·평균 아이템 M개면 1 + N + N*M 쿼리. async lazy-load 는 에러라(models
    # lazy="raise"), 루프 내 명시적 개별 쿼리로 심는다. fix 에서 selectinload/JOIN.
    items = await repository.get_order_items(session, order.id)
    item_views: list[schemas.OrderItemView] = []
    for it in items:
        product = await product_repo.get_product(session, it.product_id)  # N+1 의 +M
        item_views.append(
            schemas.OrderItemView(
                product_id=it.product_id,
                name=product.name if product is not None else "?",
                qty=it.qty,
                unit_price=it.unit_price,
            )
        )
    return schemas.OrderView(
        id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        created_at=order.created_at,
        items=item_views,
    )


async def list_orders(session: AsyncSession, user: User) -> schemas.OrderListResponse:
    # P1-11: LIMIT 없이 전체를 가져온 뒤,
    orders = await repository.list_orders_for_user(session, user.id)
    # P1-02: 그 전체를 루프 돌며 아이템·상품을 개별 조회한다.
    views = [await _build_order_view(session, order) for order in orders]
    return schemas.OrderListResponse(user_id=user.id, order_count=len(views), orders=views)


async def get_order_detail(
    session: AsyncSession, user: User, order_id: int
) -> schemas.OrderView | None:
    order = await repository.get_order(session, order_id)
    if order is None or order.user_id != user.id:
        return None
    return await _build_order_view(session, order)


async def realtime_ranking(session: AsyncSession, limit: int) -> list[schemas.RankingEntry]:
    since = datetime.now(UTC) - _RANKING_WINDOW
    rows = await repository.ranking_realtime(session, since, limit)
    return [
        schemas.RankingEntry(product_id=pid, name=name, sold_qty=sold) for pid, name, sold in rows
    ]
