"""seed — COPY 기반 대량 적재 (§1 seed 규모).

    users 5만 / products 20만(카테고리 50) / reviews 100만 / orders 300만 / order_items 800만

seed 는 실험 대상이 아니다. 루프 INSERT 금지, COPY 로 수 분 안에 끝내는 것이 목표다.

메모리: order_items 800만 행을 리스트로 만들면 터진다. 전부 제너레이터로 흘려보낸다.
  orders.total_amount 는 자기 아이템들의 합이어야 하는데, 두 테이블을 각각 COPY 하면서
  아이템을 버퍼링할 수는 없다. 그래서 order_id 를 시드로 한 RNG 로 같은 아이템 구성을
  두 번(총액 계산용 / 아이템 적재용) 재생성한다 — 결정적이고 메모리가 평탄하다.

실행:  make seed
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import bcrypt

N_CATEGORIES = 50
N_USERS = 50_000
N_PRODUCTS = 200_000
N_REVIEWS = 1_000_000
N_ORDERS = 3_000_000
N_CART_ITEMS = 20_000

# P1-11(LIMIT 없는 목록 응답) 소재: 주문 수천 건짜리 헤비 유저를 섞어 둔다.
# 유저 1..200 이 각 3,000건, 나머지 49,800명이 나머지를 나눠 갖는다.
HEAVY_USERS = 200
HEAVY_USER_ORDERS = 3_000

# 딜 전용 상품을 뒤쪽에 따로 떼어 둔다. 일반 주문은 이 상품을 절대 참조하지 않는다.
# 그래야 oversell 검증(load/checks/oversell.sql)이 "이 상품의 판매량 = 딜 판매량" 으로
# 모호함 없이 성립한다.
N_DEALS = 20
DEAL_PRODUCT_START = N_PRODUCTS - N_DEALS + 1  # 199_981 .. 200_000
NORMAL_PRODUCT_MAX = DEAL_PRODUCT_START - 1  # 일반 주문이 고르는 범위

# P2-01 의 기본 시나리오: 딜 수량 1,000 에 3,000vu 스파이크
SPIKE_DEAL_QTY = 1_000

SEED = 20260717

# seed 된 유저 전원의 로그인 비밀번호. k6 로그인 시나리오가 이 값을 쓴다.
# 해시 비용(cost 12)은 P1-10 의 소재이므로 낮추지 않는다.
SEED_PASSWORD = "flashmart-pw"
BCRYPT_ROUNDS = 12

# 상품명은 "형용사 명사 접미사 {id}" 로 만든다. k6 검색 시나리오(P1-03)가 명사 하나를
# q 로 던지면 20만 건 중 약 1/20 이 매칭된다 — 매칭 비율이 예측 가능해야 전/후 비교가 된다.
_ADJ = (
    "무선 초경량 프리미엄 휴대용 스마트 정품 리퍼 친환경 고속 저소음 방수 접이식 인체공학 대용량"
).split()
_NOUN = (
    "이어폰 키보드 모니터 마우스 충전기 백팩 텀블러 스탠드 케이블 스피커 "
    "웹캠 허브 의자 램프 패드 커피머신 청소기 선풍기 이불 프라이팬"
).split()
_SUFFIX = "Pro Max Lite Air Plus SE Mini Ultra".split()

_CATEGORY_NAMES = (
    "가전 컴퓨터 모바일 주방 가구 패션 뷰티 식품 스포츠 도서 완구 반려동물 자동차 공구 office"
).split()


def dsn_from_env() -> str:
    """app 과 같은 DATABASE_URL 을 쓰되, asyncpg 가 직접 이해하는 형태로 바꾼다."""
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://flashmart:flashmart@db:5432/flashmart")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _price_for(product_id: int) -> Decimal:
    # 1,000 ~ 500,000 원, 백원 단위.
    rng = random.Random(SEED ^ product_id)
    return Decimal(rng.randrange(10, 5_000)) * 100


def _user_for_order(order_id: int) -> int:
    heavy_total = HEAVY_USERS * HEAVY_USER_ORDERS
    if order_id <= heavy_total:
        return ((order_id - 1) % HEAVY_USERS) + 1
    rest = order_id - heavy_total - 1
    return HEAVY_USERS + 1 + (rest % (N_USERS - HEAVY_USERS))


def _order_items_for(order_id: int, prices: list[Decimal]) -> list[tuple[int, int, Decimal]]:
    """(product_id, qty, unit_price) 목록. order_id 만으로 결정된다."""
    rng = random.Random(SEED * 31 + order_id)
    # 평균 약 2.67개 → 300만 주문 x 2.67 ≈ 800만 아이템
    n_items = rng.choices([1, 2, 3, 4, 5], weights=[20, 27, 27, 19, 7], k=1)[0]
    items = []
    for pid in rng.sample(range(1, NORMAL_PRODUCT_MAX + 1), n_items):
        items.append((pid, rng.randint(1, 3), prices[pid]))
    return items


def _created_at_for(order_id: int, now: datetime) -> datetime:
    rng = random.Random(SEED * 17 + order_id)
    return now - timedelta(seconds=rng.randrange(0, 365 * 24 * 3600))


# --------------------------------------------------------------------------- 행 제너레이터


def gen_categories() -> Iterator[tuple[int, str]]:
    for i in range(1, N_CATEGORIES + 1):
        base = _CATEGORY_NAMES[(i - 1) % len(_CATEGORY_NAMES)]
        yield (i, f"{base}-{i:02d}")


def gen_users(now: datetime, pw_hash: str) -> Iterator[tuple[int, str, str, datetime]]:
    # 5만 명 전원이 같은 해시를 공유한다. 해시를 5만 번 계산하면 cost 12 기준으로
    # seed 에만 3시간 이상 걸리는데, 로그인 부하(P1-10)가 지불하는 비용은
    # "검증 1회" 라서 해시가 같아도 실험에는 아무 영향이 없다.
    rng = random.Random(SEED + 1)
    for i in range(1, N_USERS + 1):
        created = now - timedelta(seconds=rng.randrange(0, 730 * 24 * 3600))
        yield (i, f"user{i}@flashmart.test", pw_hash, created)


ProductRow = tuple[int, int, str, str, Decimal, int, datetime]
OrderRow = tuple[int, int, str, Decimal, datetime]
OrderItemRow = tuple[int, int, int, int, Decimal]
DealRow = tuple[int, int, Decimal, int, int, datetime, datetime]


def gen_products(now: datetime, prices: list[Decimal]) -> Iterator[ProductRow]:
    rng = random.Random(SEED + 2)
    for i in range(1, N_PRODUCTS + 1):
        adj = _ADJ[rng.randrange(len(_ADJ))]
        noun = _NOUN[rng.randrange(len(_NOUN))]
        suffix = _SUFFIX[rng.randrange(len(_SUFFIX))]
        name = f"{adj} {noun} {suffix} {i}"
        description = (
            f"{name} 상품 설명. {adj} 소재와 {noun} 특유의 마감. "
            f"모델번호 FM-{i:06d}. 재고 소진 시 조기 종료될 수 있습니다."
        )
        created = now - timedelta(seconds=rng.randrange(0, 365 * 24 * 3600))
        yield (
            i,
            rng.randrange(1, N_CATEGORIES + 1),
            name,
            description,
            prices[i],
            rng.randrange(0, 5_000),
            created,
        )


def gen_reviews() -> Iterator[tuple[int, int, int, int, str]]:
    rng = random.Random(SEED + 3)
    for i in range(1, N_REVIEWS + 1):
        rating = rng.choices([1, 2, 3, 4, 5], weights=[5, 8, 17, 35, 35], k=1)[0]
        yield (
            i,
            rng.randrange(1, N_PRODUCTS + 1),
            rng.randrange(1, N_USERS + 1),
            rating,
            f"리뷰 본문 {i}. 별점 {rating}점. 배송과 마감 상태에 대한 평가입니다.",
        )


def gen_orders(now: datetime, prices: list[Decimal]) -> Iterator[OrderRow]:
    for oid in range(1, N_ORDERS + 1):
        items = _order_items_for(oid, prices)
        total = sum((qty * price for _, qty, price in items), Decimal(0))
        rng = random.Random(SEED * 13 + oid)
        status = rng.choices(["PAID", "PENDING", "FAILED"], weights=[92, 5, 3], k=1)[0]
        yield (oid, _user_for_order(oid), status, total, _created_at_for(oid, now))


def gen_order_items(prices: list[Decimal]) -> Iterator[OrderItemRow]:
    item_id = 0
    for oid in range(1, N_ORDERS + 1):
        # gen_orders 와 같은 RNG 시드 → 같은 아이템 구성이 재생성된다.
        for pid, qty, price in _order_items_for(oid, prices):
            item_id += 1
            yield (item_id, oid, pid, qty, price)


def gen_deals(now: datetime, prices: list[Decimal]) -> Iterator[DealRow]:
    for n in range(N_DEALS):
        deal_id = n + 1
        product_id = DEAL_PRODUCT_START + n
        # 딜 1번이 스파이크 실험(P2-01/02)의 기본 대상이다: 수량 1,000, 지금 열려 있음.
        qty = SPIKE_DEAL_QTY if deal_id == 1 else 200 * ((n % 5) + 1)
        yield (
            deal_id,
            product_id,
            (prices[product_id] * Decimal("0.5")).quantize(Decimal("0.01")),
            qty,
            qty,
            now - timedelta(hours=1),
            now + timedelta(days=30),
        )


def gen_cart_items() -> Iterator[tuple[int, int, int]]:
    # P2-03(교차 장바구니 동시 주문 → deadlock) 의 소재.
    # 같은 상품 조합을 서로 다른 순서로 담은 카트가 있어야 락 순서가 엇갈린다.
    rng = random.Random(SEED + 5)
    seen: set[tuple[int, int]] = set()
    made = 0
    while made < N_CART_ITEMS:
        user_id = rng.randrange(1, N_USERS + 1)
        product_id = rng.randrange(1, NORMAL_PRODUCT_MAX + 1)
        if (user_id, product_id) in seen:
            continue
        seen.add((user_id, product_id))
        made += 1
        yield (user_id, product_id, rng.randint(1, 3))


# --------------------------------------------------------------------------- 적재


async def _copy(
    conn: asyncpg.Connection,
    table: str,
    columns: list[str],
    records: Iterator[tuple[object, ...]],
    label: str,
) -> None:
    started = time.monotonic()
    result = await conn.copy_records_to_table(table, records=records, columns=columns)
    elapsed = time.monotonic() - started
    print(f"  {label:<14} {result:>20}  ({elapsed:6.1f}s)", flush=True)


async def main() -> None:
    now = datetime.now(UTC)
    print(f"seed 시작 — {dsn_from_env().split('@')[-1]}", flush=True)
    started = time.monotonic()

    conn = await asyncpg.connect(dsn_from_env())
    try:
        # prices[product_id] 를 미리 만들어 둔다. orders/order_items 두 패스가 같은 값을 봐야 한다.
        prices: list[Decimal] = [Decimal(0)] * (N_PRODUCTS + 1)
        for pid in range(1, N_PRODUCTS + 1):
            prices[pid] = _price_for(pid)

        print("기존 데이터 정리", flush=True)
        await conn.execute(
            "TRUNCATE payments, order_items, orders, cart_items, deals, "
            "reviews, products, users, categories RESTART IDENTITY CASCADE"
        )

        # COPY 중 FK 트리거를 끈다. 800만 order_items x FK 2개 = 1,600만 번의
        # 부모 PK 확인을 건너뛴다. 데이터는 생성 단계에서 이미 정합하다.
        # (superuser 필요 — compose 의 POSTGRES_USER 가 부트스트랩 superuser 다.)
        await conn.execute("SET session_replication_role = replica")

        # 전원이 공유할 해시를 딱 한 번 계산한다.
        pw_hash = bcrypt.hashpw(
            SEED_PASSWORD.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        ).decode()

        print("COPY", flush=True)
        await _copy(conn, "categories", ["id", "name"], gen_categories(), "categories")
        await _copy(
            conn,
            "users",
            ["id", "email", "pw_hash", "created_at"],
            gen_users(now, pw_hash),
            "users",
        )
        await _copy(
            conn,
            "products",
            ["id", "category_id", "name", "description", "price", "stock", "created_at"],
            gen_products(now, prices),
            "products",
        )
        await _copy(
            conn,
            "reviews",
            ["id", "product_id", "user_id", "rating", "body"],
            gen_reviews(),
            "reviews",
        )
        await _copy(
            conn,
            "orders",
            ["id", "user_id", "status", "total_amount", "created_at"],
            gen_orders(now, prices),
            "orders",
        )
        await _copy(
            conn,
            "order_items",
            ["id", "order_id", "product_id", "qty", "unit_price"],
            gen_order_items(prices),
            "order_items",
        )
        await _copy(
            conn,
            "deals",
            [
                "id",
                "product_id",
                "deal_price",
                "total_qty",
                "remaining_qty",
                "opens_at",
                "closes_at",
            ],
            gen_deals(now, prices),
            "deals",
        )
        await _copy(
            conn, "cart_items", ["user_id", "product_id", "qty"], gen_cart_items(), "cart_items"
        )

        await conn.execute("SET session_replication_role = origin")

        # COPY 로 id 를 명시 적재했으므로 시퀀스가 1 에 멈춰 있다.
        # 이대로 두면 앱의 첫 INSERT 가 PK 중복으로 터진다.
        print("시퀀스 정렬", flush=True)
        for table in (
            "categories",
            "users",
            "products",
            "reviews",
            "deals",
            "orders",
            "order_items",
            "payments",
        ):
            await conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )

        # ANALYZE 를 빠뜨리면 플래너가 통계 없이 계획을 세운다.
        # 그러면 P1-03 의 EXPLAIN 이 "인덱스가 없어서 seq scan" 인지
        # "통계가 없어서 seq scan" 인지 구분이 안 된다. 실험의 전제다.
        print("ANALYZE", flush=True)
        await conn.execute("ANALYZE")

        rows = await conn.fetch(
            """
            SELECT relname, n_live_tup
            FROM pg_stat_user_tables
            ORDER BY n_live_tup DESC
            """
        )
        print("\n적재 결과 (n_live_tup, ANALYZE 기준 추정)", flush=True)
        for r in rows:
            print(f"  {r['relname']:<14} {r['n_live_tup']:>12,}", flush=True)

    finally:
        await conn.close()

    print(f"\nseed 완료 — {time.monotonic() - started:.1f}s", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
