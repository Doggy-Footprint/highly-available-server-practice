"""products 데이터 접근.

검색(P1-03)은 인덱스가 붙었다. 목록 페이지네이션(P1-04)·목록 total(P1-05)·인기 상품
집계(P2-05)는 아직 인덱스 없는 컬럼을 타거나 매 요청 무거운 쿼리를 실행한다.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderItem, OrderStatus, Product, Review


def _filtered(q: str | None, category_id: int | None) -> Select[tuple[Product]]:
    stmt = select(Product)
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if q:
        # P1-03 fix: name/description 에 pg_trgm GIN 인덱스가 있어 선행 와일드카드
        # `ILIKE '%q%'` 도 인덱스를 탄다 (마이그레이션 0002).
        pattern = f"%{q}%"
        stmt = stmt.where(Product.name.ilike(pattern) | Product.description.ilike(pattern))
    return stmt


# =====================================================================
# [P1-04 REVIEW & FEEDBACK for learner — 4/4: repository.py]
#
# 1. 작성하신 코드 피드백:
#    - `Product.id > cursor` 조건과 `.order_by(Product.id).limit(size)` 조합을 정확히 구현하셨습니다!
#    - 정렬 방향(`ASC`)과 비교 방향(`>`)이 일치하여 PostgreSQL 플래너가 `products_pkey` B-Tree 인덱스를
#      정방향으로 즉시 탐색(Index Cond)합니다.
#
# 2. 프레임워크/라이브러리(SQLAlchemy 2.0 Async) API 설명:
#    - `Select` 객체의 불변성(Immutability)과 체이닝 패턴:
#      SQLAlchemy 2.0의 `select(...)` 객체는 `.where()`, `.order_by()`, `.limit()`를 호출할 때마다
#      새로운 `Select` 객체를 반환합니다.
#      따라서 지금처럼 `if/else`로 전체 체인을 두 번 적는 것도 잘 동작하지만, 실무에서는 중복을 줄이기 위해
#      아래처럼 조건부로 `.where()`만 덧붙이는(Query Building) 패턴을 많이 씁니다:
#        ```python
#        stmt = _filtered(q, category_id)
#        if cursor is not None:
#            stmt = stmt.where(Product.id > cursor)
#        stmt = stmt.order_by(Product.id).limit(size)
#        ```
#      이렇게 짜면 나중에 정렬 기준이나 `.limit()` 로직을 바꿀 때 두 군데(if/else)를 다 고치지 않아도 되어
#      실수(if쪽만 고치고 else쪽은 안 고치는 버그)를 예방할 수 있습니다.
#    - `await session.scalars(stmt)`:
#      - `session.execute(stmt)`는 행을 튜플(`Row(Product,)`) 형태로 반환하지만,
#      - `session.scalars(stmt)`는 첫 번째 컬럼(여기선 `Product` ORM 엔티티 객체 자체)만 바로 꺼내주어
#        `.all()` 호출 시 깔끔하게 `Sequence[Product]` 리스트를 얻을 수 있습니다.
#
# 3. 성능 측면에서 실제로 어떻게 작용했는가? (Before vs After 실측):
#    - [Before — `OFFSET(page * size)`]:
#      `page=5000`(`OFFSET 100000`) 요청 시 DB가 `products_pkey` 인덱스를 처음(`id=1`)부터
#      `100,020`건 읽고 앞의 `100,000`건을 버렸습니다.
#      -> 호출당 평균 **4,414개 버퍼 블록(약 35MB)** 스캔, 쿼리 평균 **185.15ms** 소요.
#    - [After — `WHERE Product.id > cursor` (작성하신 코드)]:
#      B-Tree 인덱스의 루트 → 브랜치 → 리프 노드로 `id = cursor` 위치를 $O(\log N)$으로 단번에 찾아간 뒤
#      그 바로 다음 옆 칸부터 딱 20(`size`)개만 읽고 즉시 멈춥니다.
#      -> 호출당 평균 **4개 버퍼 블록(약 32KB)**만 읽음 (**1,103배 감소**),
#         쿼리 평균 **0.43ms** (**430배 단축**)!
#      -> 결과적으로 첫 페이지(`shallow`)와 9,500페이지(`deep`)의 응답 속도가 완전히 똑같아졌습니다.
# =====================================================================
async def search_products(
    session: AsyncSession, q: str | None, category_id: int | None, cursor: int | None, size: int
) -> Sequence[Product]:
    if cursor is not None:
        stmt = _filtered(q, category_id).where(Product.id > cursor).order_by(Product.id).limit(size)
    else:
        stmt = _filtered(q, category_id).order_by(Product.id).limit(size)
    return (await session.scalars(stmt)).all()


async def count_products(session: AsyncSession, q: str | None, category_id: int | None) -> int:
    # INTENDED-ISSUE: P1-05
    # 목록 응답의 total 을 매 요청 COUNT(*) 로 구한다. 필터가 seq scan 이라 목록 경로의
    # 지배적 비용이 된다. fix 에서 count 제거/캐시/근사치(reltuples)로 바꾼다.
    stmt = select(func.count()).select_from(_filtered(q, category_id).subquery())
    return (await session.scalar(stmt)) or 0


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def review_stats(session: AsyncSession, product_id: int) -> tuple[int, float | None]:
    stmt = select(func.count(Review.id), func.avg(Review.rating)).where(
        Review.product_id == product_id
    )
    row = (await session.execute(stmt)).one()
    avg = float(row[1]) if row[1] is not None else None
    return int(row[0]), avg


async def popular_products(session: AsyncSession, limit: int) -> Sequence[tuple[int, str, int]]:
    # INTENDED-ISSUE: P2-05
    # 인기 상품 = 전 기간 판매량 상위. 800만 order_items 를 상품별로 GROUP BY 하는 무거운
    # 집계를 매 요청 실행한다. Phase 0 엔 Redis 가 없어 캐시도 없다. P2-05 fix 에서
    # 캐시 + single-flight 락 + TTL jitter 를 붙이고, 그 "고정 TTL 캐시" 가 만료 순간
    # 동시 miss 로 DB 를 때리는 스탬피드를 재현/수정한다.
    sold = func.sum(OrderItem.qty).label("sold")
    stmt = (
        select(Product.id, Product.name, sold)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status != OrderStatus.FAILED)
        .group_by(Product.id, Product.name)
        .order_by(sold.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(int(r[0]), str(r[1]), int(r[2])) for r in rows]
