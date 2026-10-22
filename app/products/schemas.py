from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ProductSummary(BaseModel):
    id: int
    category_id: int
    name: str
    price: Decimal
    stock: int


# =====================================================================
# [P1-04 REVIEW & FEEDBACK for learner — 1/4: schemas.py]
#
# 1. 작성하신 코드 피드백:
#    - `next_cursor: int | None` 타입 선언이 정확합니다!
#    - 남겨주신 질문 (`# What about previous?`)에 대한 답변:
#      - 무한 스크롤(모바일 피드, 커머스 상품 목록)에서는 보통 다음 페이지(`next_cursor`)만 씁니다.
#      - 만약 관리자 화면처럼 "이전 페이지(<)" 버튼도 필요하다면 `prev_cursor: int | None`을 추가하고,
#        이전 페이지 요청 시 `WHERE id < :prev_cursor ORDER BY id DESC LIMIT size + 1`로
#        역방향 인덱스 스캔을 한 뒤 결과 리스트만 다시 오름차순으로 뒤집어(`reversed`) 내려줍니다.
#
# 2. 프레임워크/라이브러리(Pydantic v2) API 설명:
#    - `BaseModel`: FastAPI에서 HTTP 응답/요청 JSON 직렬화(Serialization)와 스키마 검증을 담당합니다.
#    - `int | None`: Python 3.10+의 Union 타입 문법(`Optional[int]`와 동일)입니다.
#      Pydantic v2에서는 기본값(`= None`)을 안 적어두면 "값은 None일 수 있지만 생성자 인자로
#      `next_cursor=...` 키 자체는 반드시 넘겨야 하는 필수 필드"로 동작해 실수로 빼먹는 것을 막아줍니다.
#
# 3. 성능 및 Bad Practice 체크:
#    - [Good]: 불필요해진 `page` 필드를 제거해 응답 페이로드 계약을 명확히 했습니다.
#    - [Nit (포맷팅)]: `# What about previous?` 주석 앞에 공백이 1칸이라 `ruff format`에서
#      PEP 8 기준(코드 뒤 인라인 주석은 공백 2칸 이상) 경고가 발생했습니다.
# =====================================================================
class ProductListResponse(BaseModel):
    total: int  # P1-05: 매 요청 COUNT(*) 로 채운다
    next_cursor: int | None  # What about previous?
    size: int
    items: list[ProductSummary]


class ProductDetail(BaseModel):
    id: int
    category_id: int
    name: str
    description: str
    price: Decimal
    stock: int
    created_at: datetime
    review_count: int
    avg_rating: float | None


class PopularProduct(BaseModel):
    product_id: int
    name: str
    sold_qty: int
