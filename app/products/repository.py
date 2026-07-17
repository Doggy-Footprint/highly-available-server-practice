"""products 데이터 접근.

검색/목록/집계가 전부 인덱스 없는 컬럼을 타서 seq scan 이 된다 (P1-03/04/05, P2-05).
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
        # INTENDED-ISSUE: P1-03
        # name/description 에 인덱스가 없어 `ILIKE '%q%'` 가 20만 행을 전부 seq scan 한다.
        # 선행 와일드카드(%q%)라 btree 로도 못 타고, fix 에서 pg_trgm GIN + 복합 btree 를 만든다.
        pattern = f"%{q}%"
        stmt = stmt.where(Product.name.ilike(pattern) | Product.description.ilike(pattern))
    return stmt


async def search_products(
    session: AsyncSession, q: str | None, category_id: int | None, page: int, size: int
) -> Sequence[Product]:
    # INTENDED-ISSUE: P1-04
    # OFFSET 페이지네이션. 깊은 페이지(page 5000급)면 앞의 page*size 행을 스캔해서 버린다 —
    # 페이지가 깊어질수록 선형으로 느려진다. fix 에서 keyset(cursor)로 바꾼다.
    stmt = _filtered(q, category_id).order_by(Product.id).limit(size).offset(page * size)
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
