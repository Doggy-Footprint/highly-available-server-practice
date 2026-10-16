# FlashMart AI 리뷰어 채점 기준표 & 솔루션 가이드 (Answer Key & Rubric)

> **문서 용도 및 열람 규칙**
> - **AI 에이전트 (필수 열람)**: 과제 시작(`Step 1`), 설계 리뷰(`Step 2`), 적대적 테스트 작성(`Step 4`), 프로덕션 코드 리뷰(`Step 5`) 수행 전 **반드시 이 문서에서 해당 이슈 ID의 섹션을 먼저 읽고** 기준에 맞춰 질문·테스트·채점을 수행한다.
> - **사용자 (열람 주의)**: 스스로 설계·구현(`Lv.2 ~ Lv.4`)할 때는 스포일러 방지를 위해 열람하지 않는다.

---

## 0. AI 리뷰어 공통 원칙

1. **단일 정답 강요 금지**: 아래 명시된 `표준 해법` 외에도 사용자가 `허용 대안`을 선택하고 트레이드오프를 합리적으로 방어했으며 SLO를 충족한다면 `APPROVED` 판정을 내린다.
2. **함정(Pitfall) 집중 점검**: 단순히 "k6가 돌아간다"로 통과시키지 않고, 각 이슈의 **`[코드 리뷰 필수 체크 (Pitfalls)]`**에 적힌 프로덕션 안티패턴이 코드에 남아 있으면 `CHANGES REQUESTED`로 분류한다.
3. **적대적 테스트 자동화**: 각 이슈의 **`[적대적 테스트 포인트]`**를 바탕으로 `tests/adversarial/test_<id>.py`를 작성해 경계값·동시성·예외 처리를 실제로 타격한다.

---

## 1. Phase 1 이슈별 채점 기준 (`P1-01 ~ P1-12`)

### P1-01 ~ P1-03 (완료됨)
- **P1-01 (로그인 세션)**: 프로세스 내 `dict` → Redis 세션 스토어(또는 JWT) 전환으로 다중 인스턴스 stateless 달성.
- **P1-02 (주문 내역 N+1)**: 루프 내 개별 조회 → `selectinload`(또는 JOIN) 전환으로 쿼리 수 상수화(≤3).
- **P1-03 (상품 검색 인덱스)**: `pg_trgm` GIN 인덱스(`ix_products_name_trgm`, `ix_products_description_trgm`) + `category_id` B-Tree 인덱스 도입.

---

### P1-04: 상품 목록 깊은 페이지 탐색 지연 (`OFFSET` → Keyset/Cursor)
- **표준 해법**: Keyset(Cursor) 페이지네이션 도입 (`WHERE id > :cursor ORDER BY id ASC LIMIT :limit` 또는 정렬 기준 복합 커서).
- **허용 대안**:
  - 기존 `?page=` 쿼리 파라미터 하위 호환성을 유지하면서 `?cursor=` 파라미터가 들어올 때 Keyset 경로를 타도록 하이브리드 구성 (또는 `page` 상한 제한 + `cursor` 전면 전환).
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. `ORDER BY` 절과 `WHERE` 커서 비교 방향이 정확히 일치하는가? (`ORDER BY id ASC`인데 `WHERE id < :cursor`이거나 `ORDER BY`가 누락되면 순서가 깨짐)
  2. 마지막 페이지 도달 시 `next_cursor=None`(또는 빈 값) 처리가 정확한가? (`limit + 1`개를 조회해 다음 페이지 존재 여부를 판별하는지, 아니면 단순히 반환 개수가 `limit`와 같으면 무조건 `next_cursor`를 내려주어 빈 마지막 페이지 호출을 유발하는지 점검)
  3. `category`나 `q` 필터와 결합될 때도 커서 조건이 누락 없이 함께 적용되는가?
- **적대적 테스트 포인트 (`test_p1_04.py`)**:
  - 첫 페이지(`cursor=None`) → 중간 페이지(`cursor=마지막_id`) → 마지막 페이지까지 연속 순회 시 **중복 노출 상품 0건, 누락 상품 0건** 검증
  - 존재하지 않는 큰 커서값(`cursor=999999999`), 음수/0 등 비정상 커서 입력 시 빈 배열 또는 `422` 처리 검증

---

### P1-05: 상품 목록/검색 매 요청 `COUNT(*)` 병목 제거
- **표준 해법**:
  - 목록 API에서 매 요청 정확한 `SELECT COUNT(*)` 실행을 제거하고 `LIMIT (size + 1)` 조회를 통한 `has_next: bool` 반환 방식으로 전환하거나,
  - 전체/카테고리별 건수를 Redis에 TTL 캐싱(또는 필터 없는 경우 `pg_class.reltuples` 근사치 활용).
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 필터 없는 목록만 고치고 `?category=`나 `?q=` 검색 경로에 여전히 무거운 실시간 `COUNT(*)`를 남겨두지 않았는가?
  2. 응답 스키마(`ProductListResponse`) 변경 시 기존 클라이언트(예: `load/k6/mixed.js`, `p1-03.js`)가 깨지지 않도록 스키마 호환성(`total: int | None = None`, `has_next: bool` 등)을 고려했는가?
  3. Redis 캐시를 선택한 경우, 캐시 키에 `category`·`q` 조건이 정규화되어 포함되는가? (모든 검색어에 대해 무제한 캐시 키를 생성하면 Redis 메모리 오염 가능성)
- **적대적 테스트 포인트 (`test_p1_05.py`)**:
  - SQLAlchemy 쿼리 카운터(event listener)로 `GET /products` 호출 시 `COUNT(*)` 쿼리가 발생하지 않음을 단언(assert)

---

### P1-06: 결제 호출 동기 블로킹 제거 (`requests` → 비동기 I/O)
- **표준 해법**: `httpx.AsyncClient`를 사용하여 비동기 논블로킹 HTTP 호출로 전환하고, FastAPI `lifespan` 등을 통해 **앱 전역(프로세스 단위) 커넥션 풀을 재사용**.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. **[가장 흔한 실수]** 매 결제 요청마다 `async with httpx.AsyncClient() as client:`를 함수 내부에서 생성하고 닫는 경우 → 이벤트 루프는 안 막히지만 매번 TCP 연결/소켓 생성 오버헤드가 발생하고 고부하 시 포트 고갈 위험이 있음. 반드시 클라이언트 인스턴스(커넥션 풀)를 재사용해야 함.
  2. `httpx.Timeout`(connect, read, write, pool)이 명시적으로 설정되어 있는가?
  3. `httpx.RequestError` / `httpx.HTTPStatusError` 발생 시 날것의 500 크래시 대신 도메인 예외/상태로 안전하게 변환되는가?
  4. `pyproject.toml`에서 더 이상 쓰지 않는 `requests` 의존성 정리를 고려했는가?
- **적대적 테스트 포인트 (`test_p1_06.py`)**:
  - 결제 API가 800ms 지연되는 동안 동시에 `GET /products` 20건을 호출했을 때, 상품 조회가 결제 지연을 기다리지 않고 즉시(<100ms) 완료되는지 동시성 검증

---

### P1-07: DB 트랜잭션 내부의 외부 결제 API 호출 분리
- **표준 해법**:
  - **1단계 트랜잭션**: 재고 차감(또는 예약) + `Order(status="PENDING")` 생성 후 즉시 `commit`하여 DB 트랜잭션과 락을 해제.
  - **외부 I/O 구간**: DB 트랜잭션(혹은 세션 점유) 밖에서 `mockpg` 비동기 결제 호출.
  - **2단계 트랜잭션**: 결제 성공 시 `Order(status="PAID")` + `Payment` 기록 커밋 / 결제 실패·예외 시 `Order(status="FAILED")` 전이 및 **차감했던 상품 재고(`Product.stock`) 원복(보상 트랜잭션)** 커밋.
- **허용 대안**:
  - 두 단계를 아예 별도 DB 세션으로 분리하거나, 같은 세션 객체라도 `await session.commit()` 후 DB 커넥션을 풀에 반환(`expire_on_commit=False` 등 주의)한 뒤 재획득하는 구조.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. **[핵심 함정]** `await session.commit()`만 호출하면 SQLAlchemy `AsyncSession`이 커넥션을 풀에 즉시 돌려주는지, 아니면 세션이 살아있는 동안 커넥션을 계속 쥐고 있는지 확인했는가? (`mockpg` 대기 시간 800ms 동안 실제로 커넥션 풀의 `checkedout` 카운트가 0으로 떨어져야 `pool_size=10, 200vu`를 버팀!)
  2. **[정합성 함정]** 결제 실패(`mockpg` 에러/타임아웃) 시 1단계에서 차감한 `Product.stock`이 정확히 원복되는가? 원복 시 `product.stock = 원래값` 덮어쓰기(Lost Update 위험!)가 아니라 `Product.stock = Product.stock + qty` 원자적 증감을 사용했는가?
  3. 향후 **F1-01(주문 취소)** 및 **F2-02(웹훅 대사)**가 들어올 때 `PENDING → PAID / FAILED` 상태 전이가 중복 실행되지 않도록 조건부 상태 업데이트(`WHERE status = 'PENDING'`)가 되어 있는가?
- **적대적 테스트 포인트 (`test_p1_07.py`)**:
  - 결제 실패 주입 시 `Order.status == "FAILED"` 전이 및 상품 재고(`stock`)가 주문 전과 100% 동일한지 검증
  - 동시 다발 주문 중 일부 성공·일부 실패 시 `초기 재고 - 성공 주문 수량 합 == 최종 재고` 불변식 검증

---

### P1-08: 다품목 주문 저장 시 루프 `INSERT` 및 건별 `commit` 제거
- **표준 해법**: 주문 생성 시 `OrderItem`들을 루프마다 `flush`/`commit`하지 않고 `session.add_all(items)` 또는 `insert(OrderItem).values(...)`로 단일 트랜잭션 내 Bulk Insert 처리.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 여러 상품을 주문할 때 중간 상품에서 재고 부족 예외가 터지면 앞선 상품의 재고 차감과 주문 아이템이 **전부 롤백(All-or-Nothing)**되는가? (루프 중간에 `commit()`이 남아있으면 부분 커밋 장애 발생)
  2. 상품 조회 시에도 루프 내 단건 `SELECT` 대신 `WHERE id IN (...)` 일괄 조회를 사용해 왕복을 줄였는가?
- **적대적 테스트 포인트 (`test_p1_08.py`)**:
  - 5개 아이템 주문 중 4번째 아이템의 재고가 부족할 때, 1~3번째 아이템의 재고가 차감되지 않고 주문/주문아이템 레코드가 0건인지 원자성 검증

---

### P1-09: 인프라 스케일아웃 & 워커·커넥션 풀 수학적 튜닝
- **표준 해법**:
  - `deploy/Dockerfile.app`(또는 compose command)의 uvicorn `--workers` 수 조정
  - `app/core/db.py`의 `pool_size`, `max_overflow`, `pool_timeout`, `pool_pre_ping` 설정
  - 공식: `앱 인스턴스 수(3) × uvicorn 워커 수(W) × (pool_size + max_overflow) + 여유분 < PostgreSQL max_connections`
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. **산술 검증**: 설정한 `3 × W × (pool_size + max_overflow)` 값이 PG `max_connections`(기본 100, 또는 튜닝값)를 초과하여 피크 부하 시 `TooManyConnectionsError`를 유발하지 않는가?
  2. **메모리 한계 검증**: `deploy/compose.yaml`의 앱 컨테이너 메모리 제한(`512m`) 하에서 워커 수를 과도하게(예: 8개 이상) 늘려 OOM Kill이 발생하지 않는가?
  3. 환경변수(`Settings`)로 `db_pool_size`, `db_max_overflow`를 주입받을 수 있게 유연하게 구성했는가?

---

### P1-10: 로그인 `bcrypt` CPU 블로킹 오프로드
- **표준 해법**: `asyncio.to_thread(bcrypt.checkpw, ...)` 및 `asyncio.to_thread(bcrypt.hashpw, ...)` (또는 `loop.run_in_executor`)를 사용해 CPU 집약적인 해싱 연산을 워커 스레드풀로 오프로드. (필요 시 환경설정에 따른 bcrypt rounds 적정화 병행)
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. `login`(`checkpw`)만 오프로드하고 `signup`(`hashpw`)은 여전히 이벤트 루프에서 동기 실행하고 있지 않은가?
  2. 비동기 함수(`async def`)로 바꾼 뒤 호출부에서 `await`를 누락하지 않았는가?
- **적대적 테스트 포인트 (`test_p1_10.py`)**:
  - 동시 로그인/회원가입 요청 20건이 도는 와중에 가벼운 `GET /products/{id}` 요청의 응답 지연이 블로킹되지 않는지 검증

---

### P1-11: 장바구니·주문 내역 무제한 반환(`LIMIT` 부재) 방어
- **표준 해법**: `GET /orders` 및 `GET /cart`에 페이지네이션(`limit`, `cursor` 또는 `offset`) 및 최대 조회 상한(`Query(default=20, ge=1, le=100)`) 강제.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 클라이언트가 `?limit=100000`이나 `?limit=-1`, `?limit=0`을 보냈을 때 Pydantic/FastAPI 레벨에서 `422 Unprocessable Entity`로 즉시 차단되는가?
  2. DB 쿼리(`stmt.limit(...)`)에 실제로 `limit`가 걸려 있는가? (Python 메모리로 전체 행을 다 퍼올린 뒤 슬라이싱(`rows[:limit]`)하면 DB·메모리 병목이 전혀 해결되지 않음!)
  3. 정렬 순서(`ORDER BY created_at DESC, id DESC` 등)가 결정론적(Deterministic)이어서 페이지 간 순서 뒤섞임이 없는가?
- **적대적 테스트 포인트 (`test_p1_11.py`)**:
  - `limit=0`, `limit=-5`, `limit=10000` 요청 시 `422` 응답 검증 및 기본 호출 시 반환 건수 상한 동작 검증

---

### P1-12: 예외 발생 경로에서의 DB 세션/커넥션 누수 차단
- **표준 해법**: `app/core/deps.py`의 `get_db_session` 의존성 제너레이터에서 `async with AsyncSessionLocal() as session:` 컨텍스트 매니저(또는 `try ... except: await session.rollback(); raise finally: await session.close()`)를 사용하여 어떤 예외가 발생하더라도 롤백 및 커넥션 반환을 100% 보장.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. `HTTPException`(예: 400, 404, 409)이나 도메인 예외가 라우터/서비스에서 발생했을 때 제너레이터의 정리(`close`) 블록이 반드시 실행되는가?
  2. 트랜잭션 도중 예외가 발생했을 때 `idle in transaction` 상태로 커넥션이 남지 않고 명시적으로 롤백·종료되는가?
- **적대적 테스트 포인트 (`test_p1_12.py`)**:
  - 의도적으로 에러(404/400/500)를 유발하는 요청을 `pool_size + max_overflow` 횟수의 3배 이상 연속 호출한 뒤에도 커넥션 풀이 고갈되지 않고 정상 요청이 즉시 처리되는지 검증

---

## 2. Phase 2 이슈별 채점 기준 (`P2-01 ~ P2-15`)

### P2-01: 선착순 딜 구매 초과 판매(Oversell) 1차 방어 (RDB 원자 연산)
- **표준 해법**:
  - `UPDATE deals SET remaining_qty = remaining_qty - :qty WHERE id = :deal_id AND remaining_qty >= :qty AND opens_at <= NOW() AND closes_at >= NOW() RETURNING remaining_qty` (조건부 원자 UPDATE), 또는
  - `SELECT ... FROM deals WHERE id = :deal_id FOR UPDATE` 비관적 락 획득 후 차감.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. Python 코드에서 먼저 `deal = await repo.get(deal_id)`로 읽어서 `if deal.remaining_qty < qty:`를 체크한 뒤, 조건 없는 `UPDATE`를 날리는 Check-Then-Act 패턴이 조금이라도 남아있는가?
  2. `UPDATE`의 영향받은 행 수(`rowcount == 0` 또는 `RETURNING` 결과가 `None`)를 확인하여 품절(`409 Conflict` 등)과 딜 미오픈/종료 상태를 정확히 구분해 처리하는가?
- **적대적 테스트 포인트 (`test_p2_01.py`)**:
  - `remaining_qty = 10`인 딜에 대해 `asyncio.gather`로 50개의 동시 구매 요청을 발사했을 때, **정확히 10개만 성공(200/201)하고 40개는 품절 실패**하며 최종 `remaining_qty == 0`인지 검증

---

### P2-02: 선착순 딜 스파이크 흡수 (Redis Lua 선점 + Streams 큐 + Worker + 202 접수)
- **표준 해법**:
  - API 계층: Redis Lua 스크립트로 (1) 중복 구매 여부 확인(필요 시), (2) 잔여 수량(`remaining_qty >= qty`) 확인 및 차감(`DECRBY`), (3) 스트림 큐(`XADD`) 또는 선점 성공 반환을 원자적으로 수행 후 즉시 `202 Accepted` + `request_id` 반환.
  - Worker 계층 (`app/workers/`): Redis Streams Consumer Group(`XREADGROUP`)으로 이벤트를 읽어 DB에 딜 주문 확정 기록 및 `XACK`.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. **[원자성 함정]** Redis에서 `GET`으로 재고를 확인한 뒤 파이썬에서 비교하고 `DECR`을 호출하면 Redis 레벨에서 다시 Race Condition(Oversell)이 터짐! 반드시 **단일 Lua 스크립트** 또는 `DECRBY` 후 음수 시 즉시 `INCRBY` 복구 패턴을 써야 함.
  2. Lua 선점은 성공했는데 `XADD`(스트림 발행) 전에 앱이 죽거나 에러가 나면 재고만 증발(Under-sell)함 — Lua 스크립트 내부에서 재고 차감과 `XADD`를 한 번에 수행하거나 보상 로직이 있는지 점검.
  3. Worker가 DB 반영에 실패했을 때 Redis 선점 재고를 कैसे 복구(Compensation)하는가?

---

### P2-03: 다중 상품 장바구니 동시 주문 데드락(Deadlock) 차단
- **표준 해법**: 장바구니 아이템들의 재고를 잠그거나 차감하기 전에 **항상 `product_id` 오름차순(`sorted(items, key=lambda x: x.product_id)`)으로 정렬**하여 락 획득 순서를 전역적으로 고정.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 동일한 상품이 장바구니에 여러 줄로 나뉘어 들어왔을 때(또는 합산 필요 시) `product_id`별로 수량을 합산·정렬하여 처리하는가?
  2. `SELECT ... FOR UPDATE`와 `UPDATE` 순서가 모든 주문 경로에서 일관되게 PK 오름차순을 따르는가?
- **적대적 테스트 포인트 (`test_p2_03.py`)**:
  - 유저 A는 `[상품 1, 상품 2]` 순서, 유저 B는 `[상품 2, 상품 1]` 순서로 동시에 20회 교차 주문을 실행했을 때 `DeadlockDetectedError`가 0건인지 검증

---

### P2-04: 주문 생성 멱등성 (`Idempotency-Key`)
- **표준 해법**:
  - `Idempotency-Key` 헤더 수신 → `(user_id, idempotency_key)` 복합 Unique 제약(DB 테이블 또는 Redis `SET NX` + DB 영속화)으로 선점.
  - 이미 완료된 키면 저장된 응답(상태코드·본문)을 그대로 재생(Replay).
  - 현재 처리 중(`IN_PROGRESS`)인 동시 따닥 요청이면 `409 Conflict`(또는 완료 대기 후 동일 응답 반환)로 중복 실행 차단.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. **[동시 따닥 함정]** 첫 번째 요청이 아직 결제 진행 중(응답 저장 전)일 때 0.01초 차이로 두 번째 동일 키 요청이 들어오면 어떻게 되는가? 단순 `SELECT`로 키 존재 여부를 확인하면 둘 다 통과해 중복 결제가 발생함! 반드시 **선점 INSERT(Unique 제약) 또는 `SET NX`**가 선행되어야 함.
  2. **[페이로드 위변조 방어]** 동일한 `Idempotency-Key`를 재사용하면서 요청 본문(상품/수량 등)을 다르게 보냈을 때 `422/409` 에러로 거부하는가? (요청 페이로드 해시 비교)
  3. 키 스코프가 전역이 아니라 `(user_id, idempotency_key)`로 유저별 격리되어 있는가?
- **적대적 테스트 포인트 (`test_p2_04.py`)**:
  - 동일한 `Idempotency-Key`로 동시에 5개 요청 발사 시 실제 생성된 주문·결제는 정확히 1건인지 검증
  - 동일한 `Idempotency-Key`에 다른 상품 페이로드를 담아 재전송 시 에러 반환 검증

---

### P2-05: 인기 상품 캐시 스탬피드(Cache Stampede) 방어
- **표준 해법**: Single-flight(분산 락 또는 프로세스 내 `asyncio.Lock` + Redis 락)로 캐시 미스 시 단 1개의 요청만 DB 집계 쿼리를 실행하게 하고, TTL에 랜덤 Jitter 추가(또는 Soft TTL + 백그라운드 갱신).
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 락을 획득한 후 DB를 조회하기 전에 **Double-Checked Locking**(락 대기 동안 앞선 요청이 이미 채워놓은 캐시가 있는지 재확인)을 수행하는가? 이게 없으면 락을 기다리던 요청들이 차례대로 전부 DB 쿼리를 다시 날림!
  2. 분산 락을 쓴 경우, 락을 잡은 프로세스가 죽었을 때 영원히 잠기지 않도록 락 자체에 짧은 만료시간(`PX`/`EX`)과 소유자 검증(Lua 해제)이 있는가?

---

### P2-06: Read Replica 분산 라우팅 & Read-Your-Writes 정합성
- **표준 해법**:
  - `get_write_db_session`(Primary)과 `get_read_db_session`(Replica) 분리.
  - 사용자가 주문 생성 등 쓰기 작업을 수행하면 Redis(또는 쿠키/헤더)에 짧은 TTL(예: 3~5초)로 `recent_write:{user_id}` 플래그를 기록하고, 해당 플래그가 존재하는 동안 그 사용자의 조회 요청은 Primary로 강제 라우팅(Sticky Primary).
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 쓰기 트랜잭션 내부에서 수행하는 조회나 정합성이 생명인 재고 확인 쿼리가 실수로 Replica로 라우팅되지 않았는가?
  2. Replica 장애/지연 시 Primary로 안전하게 폴백할 수 있는가?

---

### P2-07: 외부 결제 장애 격리 (Retry with Backoff + Circuit Breaker)
- **표준 해법**:
  - 짧은 요청 타임아웃 + 지수 백오프(Full Jitter 포함) + 최대 재시도 횟수 상한(예: 2~3회).
  - 연속 실패율/실패 횟수가 임계치를 넘으면 서킷을 `OPEN`하여 `mockpg` 호출 없이 즉시 Fast-fail(`503 Service Unavailable` 등) 처리하고, `reset_timeout` 후 `HALF_OPEN`으로 탐색 및 자동 복구(`CLOSED`).
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. **[재시도 폭풍 함정]** `4xx`(잘못된 요청, 잔액 부족 등 비즈니스 거절) 에러까지 재시도하고 있지 않은가? (네트워크 타임아웃 및 `5xx` 일시 장애만 제한적으로 재시도해야 함)
  2. **[백오프 동기화 함정]** Jitter 없는 고정 대기시간 재시도는 동시 실패한 요청들이 정확히 같은 시각에 다시 몰려 2차 스파이크를 유발함.
  3. `HALF_OPEN` 상태에서 수백 개의 요청이 동시에 시험 호출로 통과하지 않도록 시험 요청 수(예: 1~N개)를 제한하는가?

---

### P2-08 ~ P2-15 핵심 채점 포인트 요약
- **P2-08 (무중단 종료/헬스체크)**: Readiness 헬스체크가 단순히 `{"status": "ok"}`만 반환하는지, 아니면 종료 시그널(`SIGTERM`) 수신 시 즉시 헬스체크를 실패(503)시켜 nginx가 새 트래픽을 끊게 한 뒤 in-flight 요청을 드레이닝하는지 점검.
- **P2-09 (실시간 랭킹 분리)**: 주문 확정 시 Redis `ZINCRBY` 반영 + 조회 시 `ZREVRANGE` 사용. DB `orders` 테이블 실시간 `GROUP BY` 완전 제거 여부 확인.
- **P2-10 (Worker 멱등성)**: Consumer가 메시지를 재처리(`XAUTOCLAIM` 또는 재시작 후 미-ACK 메시지 재수신)할 때 DB Unique 제약(`request_id` 등)으로 중복 주문 생성을 막고 정상 `XACK` 처리하는지 점검.
- **P2-11 (큐 운영 & DLQ)**: 파싱 불가능한 Poison 메시지 유입 시 무한 루프에 빠지지 않고 재시도 횟수(Delivery Count) 초과 시 DLQ 스트림(`deals:dlq` 등)으로 이관 후 원본 스트림에서 `XACK`하여 큐가 막히지 않는지 점검.
- **P2-12 (핫로우 Bloat)**: `deals` 테이블에 `fillfactor`(70~80) 및 테이블 레벨 `autovacuum_vacuum_scale_factor` / `autovacuum_vacuum_threshold` 마이그레이션 적용 여부 및 HOT Update 조건(인덱스 컬럼 미수정) 준수 확인.
- **P2-13 (Redis 장애 폴백)**: Redis 커넥션에 짧은 `socket_timeout` / `socket_connect_timeout`이 설정되어 있는지, `RedisError` 발생 시 상품 목록/인기 상품/랭킹 등 조회 API가 `500`으로 죽지 않고 DB 조회 또는 기본값으로 Graceful Degradation 되는지 점검.
- **P2-14 (타임아웃 계층 정렬)**: `k6 timeout > nginx proxy_read_timeout > app/httpx timeout > PostgreSQL statement_timeout` 순서가 지켜지는지, DB 세션/엔진에 `statement_timeout`이 실제 적용되었는지 확인.
- **P2-15 (무중단 마이그레이션)**: Alembic 마이그레이션에서 `with op.get_context().autocommit_block():` 내부에 `postgresql_concurrently=True`로 인덱스를 생성·삭제하는지 확인.

---

## 3. 현업 도메인 기능 과제 채점 기준 (`F1-01 ~ F2-02`)

### F1-01: 주문 취소 및 환불 상태머신 (`POST /orders/{id}/cancel`)
- **핵심 요구사항 & 표준 설계**:
  - 본인의 주문만 취소 가능(타인 주문 취소 시도 시 `403`/`404`).
  - 취소 가능 상태: `PENDING`, `PAID`. 이미 `CANCELED`/`REFUNDED`/`FAILED`인 경우 `409 Conflict`.
  - `PAID` 주문 취소 시:
    1. 먼저 원자적으로 주문 상태를 `CANCEL_REQUESTED`(또는 비관적 락)로 선점하여 **동시 중복 취소 요청 차단**.
    2. DB 트랜잭션 밖에서 `mockpg` 환불 API 호출.
    3. 환불 성공 시 주문 상태 `CANCELED`(또는 `REFUNDED`), 결제 상태 업데이트, 그리고 **주문 아이템들의 `Product.stock` 원자적 원복(`stock + qty`)** 수행 (`PK` 오름차순 정렬로 P2-03 데드락 예방).
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 동시에 같은 주문에 대해 `POST /orders/{id}/cancel`을 10번 호출했을 때, **재고가 10배로 불어나거나 `mockpg` 환불이 10번 호출되는 치명적 버그**가 없는가?
  2. `mockpg` 환불 호출 동안 DB 커넥션과 상품 로우 락을 잡고 있지 않은가? (P1-07 원칙 준수)
- **적대적 테스트 포인트 (`test_f1_01.py`)**:
  - `PAID` 주문 1건에 대해 동시에 10개의 취소 요청 발사 → 정확히 1번만 성공하고 상품 재고는 주문 수량만큼만 정확히 1회 복구되는지 검증

---

### F1-02: 선착순 프로모션 쿠폰 발급 & 주문 할인 적용 (`POST /coupons/{id}/claim`, `POST /orders`)
- **핵심 요구사항 & 표준 설계**:
  - `coupons` 테이블(`total_qty`, `issued_qty`, `discount_amount`, `min_order_amount`) 및 `user_coupons` 테이블(`user_id`, `coupon_id`, `status[AVAILABLE|USED]`, `order_id`, `UniqueConstraint(user_id, coupon_id)`).
  - 발급 시: `(user_id, coupon_id)` 중복 발급 차단 + `UPDATE coupons SET issued_qty = issued_qty + 1 WHERE id = :id AND issued_qty < total_qty` 원자적 수량 차감.
  - 주문 적용 시: `UPDATE user_coupons SET status = 'USED', order_id = :order_id WHERE id = :uc_id AND user_id = :uid AND status = 'AVAILABLE'` 원자적 선점.
  - 결제 실패 또는 주문 취소(F1-01) 시: 사용된 쿠폰 상태를 다시 `AVAILABLE`(`order_id = NULL`)로 복원.
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 유저 1명이 같은 쿠폰으로 동시에 2개의 주문을 넣었을 때 두 주문 모두 할인을 받는 **쿠폰 이중 사용(Double Spending)**이 완벽히 차단되는가?
  2. 할인 금액이 주문 총액보다 클 때 결제 금액이 음수가 되지 않도록 방어(`max(0, total - discount)` 또는 최소 주문 금액 검증)했는가?
  3. 주문 결제 실패(P1-07) 또는 취소(F1-01) 시 쿠폰 복원이 누락되지 않았는가?

---

### F2-01: 비동기 딜 구매 상태 폴링 & 미확정 재고 회수 (`GET /deals/{id}/requests/{req_id}`)
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. 접수 직후(아직 Worker가 DB에 쓰기 전) 클라이언트가 폴링했을 때 `404`가 뜨지 않고 `QUEUED` 상태가 정상 조회되는가?
  2. Worker 처리 실패 또는 만료 시 선점된 재고가 회수될 때, 이미 회수된 요청이 뒤늦게 다시 확정되거나 이중 회수되어 재고가 원래 `total_qty`보다 많아지지 않는가?

---

### F2-02: 결제 웹훅 수신 및 미결제 주문 대사 (`POST /webhooks/pg`)
- **코드 리뷰 필수 체크 (Pitfalls)**:
  1. PG사가 동일한 성공 웹훅을 3번 중복 전송했을 때 멱등하게 `200 OK`를 반환하며 부작용(중복 결제 기록 등)이 없는가?
  2. 원래의 `POST /orders` 응답 경로와 웹훅 경로가 동시에 같은 주문을 `PAID`로 업데이트하려 할 때 Race Condition 없이 하나만 상태 전이를 수행하는가?
  3. 이미 타임아웃/취소 처리되어 재고가 원복된 주문(`FAILED`/`CANCELED`)에 대해 뒤늦게 PG 결제 성공 웹훅이 도착했을 때, 무시하지 않고 **자동 망취소(환불) 호출 또는 대사 불일치 상태 기록**을 남기는가?
