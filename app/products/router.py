from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.products import schemas, service

router = APIRouter(prefix="/products", tags=["products"])
main_router = APIRouter(prefix="/main", tags=["main"])


# =====================================================================
# [P1-04 REVIEW & FEEDBACK for learner — 2/4: router.py]
#
# 1. 작성하신 코드 피드백:
#    - `cursor: int | None = Query(default=None, ge=1)` 작성이 완벽합니다!
#    - 적대적 테스트에서 `cursor=0`, `cursor=-1`, `cursor=-999`를 공격했을 때
#      DB까지 쿼리가 내려가지 않고 라우터 입구에서 즉시 `422 Unprocessable Entity`로 방어되었습니다.
#
# 2. 프레임워크/라이브러리(FastAPI) API 설명:
#    - `Query(default=None, ge=1)`:
#      - URL 쿼리 스트링(`?cursor=100`)을 파싱·검증하는 FastAPI 선언형 헬퍼입니다.
#      - `default=None`: 쿼리 파라미터가 생략되면(`GET /products`) `cursor` 변수에 `None`이 들어옵니다.
#      - `ge=1` (greater than or equal to 1): 값이 전달되었을 때 `1` 이상인지 자동 검증합니다.
#        (`gt=0`도 동일하게 동작하며, `le`는 less than or equal, `lt`는 less than 입니다.)
#    - `Depends(get_db)`:
#      - FastAPI의 의존성 주입(Dependency Injection)입니다. 요청이 들어올 때 `get_db()` 제너레이터를
#        실행해 비동기 DB 세션(`AsyncSession`)을 만들어 넣어주고, 응답이 끝나면 정리합니다.
#
# 3. 성능 및 Bad Practice 체크:
#    - [Bad Practice 방어 성공]: 만약 라우터에서 `ge=1` 검증을 안 하고 음수/0 커서를 DB로 그대로 흘려보내면,
#      불필요한 DB 커넥션 점유와 인덱스 스캔이 발생합니다. 입구(Edge)에서 잘못된 입력을 쳐낸 점이 좋습니다.
# =====================================================================
@router.get("", response_model=schemas.ProductListResponse)
async def list_products(
    category: int | None = Query(default=None),
    q: str | None = Query(default=None),
    cursor: int | None = Query(default=None, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> schemas.ProductListResponse:
    return await service.list_products(session, q, category, cursor, size)


@router.get("/{product_id}", response_model=schemas.ProductDetail)
async def get_product(
    product_id: int, session: AsyncSession = Depends(get_db)
) -> schemas.ProductDetail:
    detail = await service.get_product_detail(session, product_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return detail


@main_router.get("/popular", response_model=list[schemas.PopularProduct])
async def popular(
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[schemas.PopularProduct]:
    return await service.popular(session, limit)
