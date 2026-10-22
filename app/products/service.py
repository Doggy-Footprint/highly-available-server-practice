from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.products import repository, schemas


# =====================================================================
# [P1-04 REVIEW & FEEDBACK for learner — 3/4: service.py]
#
# 1. 작성하신 코드 피드백:
#    - `size + 1`개를 조회해서 마지막 페이지 경계(`len(further_items) > size`)를 판별하고
#      `further_items[size - 1].id`를 `next_cursor`로 뽑아낸 핵심 로직이 정확합니다!
#      덕분에 마지막 20개(`cursor=199980, size=20`) 조회 시 `next_cursor=None`이 정확히 반환되었습니다.
#
# 2. [Bad Practice & 성능 영향] — DB 중복 쿼리 호출 (Lines 11-12):
#    - 현재 코드:
#      `items = await repository.search_products(session, q, category_id, cursor, size)`
#      `further_items = await repository.search_products(session, q, category_id, cursor, size + 1)`
#    - 무엇이 문제인가? (Bad Practice):
#      1) **DB 왕복(Round-trip) 2배 낭비**: 똑같은 조건의 `SELECT` 쿼리를 `LIMIT 20`으로 한 번,
#         `LIMIT 21`로 또 한 번, 총 2번 실행하고 있습니다.
#         실제로 `pg_stat_statements`를 확인해보니 6,310번의 API 요청 동안 목록 SELECT 쿼리가
#         정확히 2배인 **12,620번** 실행되었습니다.
#      2) **두 쿼리 사이의 동시성 불일치(Race Condition)**: 첫 번째 `items` 조회와 두 번째 `further_items`
#         조회 사이의 찰나에 상품이 추가/삭제되면 `items`와 `further_items`의 기준 행이 어긋날 수 있습니다.
#    - 어떻게 고치면 되는가? (Best Practice):
#      `further_items`는 이미 앞의 `size`개 아이템을 똑같이 포함하고 있습니다!
#      따라서 `search_products(..., size + 1)` **단 한 번만** 호출한 뒤, 파이썬 리스트 슬라이싱으로
#      잘라 쓰면 쿼리 1번으로 끝납니다:
#        ```python
#        rows = await repository.search_products(session, q, category_id, cursor, size + 1)
#        has_next = len(rows) > size
#        items = rows[:size]
#        next_cursor = items[-1].id if has_next and items else None
#        ```
#
# 3. 파이썬 문법 스타일 팁:
#    - 파이썬에서는 `if (further_items and len(further_items) > size):` 처럼 조건문 바깥에 C/Java 스타일
#      소괄호 `(...)`를 치지 않습니다 (`ruff format`이 경고를 낸 이유).
#    - 또한 `len(further_items) > size`가 참이려면(`size >= 1`이므로) `further_items`는 빈 리스트일 수가
#      없어서 `if len(further_items) > size:` 만으로도 충분합니다.
# =====================================================================
async def list_products(
    session: AsyncSession, q: str | None, category_id: int | None, cursor: int | None, size: int
) -> schemas.ProductListResponse:
    items = await repository.search_products(session, q, category_id, cursor, size)
    further_items = await repository.search_products(session, q, category_id, cursor, size + 1)

    if (further_items and len(further_items) > size):
        next_cursor = further_items[size - 1].id
    else:
        next_cursor = None

    # P1-05: 목록을 뽑은 뒤 total 을 또 COUNT(*) 로 구한다 (매 요청).
    total = await repository.count_products(session, q, category_id)
    return schemas.ProductListResponse(
        total=total,
        next_cursor=next_cursor,
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
