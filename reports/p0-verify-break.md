# P0 verify-break — Phase 0 심은 문제 전수 검증 및 재심기 기록

- **검증 대상**: `28f23c2` (feat(P0): Phase 0 기능 구현 — verify-break 전 체크포인트)
- **일시**: 2026-07-18
- **판정**: `INTENDED-ISSUE` 표식 22곳 전수 대조 — **20건 합격 / 2건 불합격(P1-07, P2-03) → 재심기 완료**
- **상태**: 재심기 반영본에 대한 사용자 승인 대기 (§7-2 게이트)

---

## 1. 검증 방법

§7-2 점검 항목 (a)~(d)를 기준으로:

1. `grep -rn "INTENDED-ISSUE"` 로 표식 전수 조회 (app 21곳 + deploy/Dockerfile.app 1곳 = 22곳).
2. 각 표식 지점의 실제 코드를 §6 백로그의 "심는 문제" 정의와 대조 — 표면 형태가 아니라
   **그 코드가 실제로 백로그의 문제 신호를 만들어낼 수 있는지**(런타임 의미)를 검증.
3. 문제 외 코드의 정상성 확인: models(인덱스 0개), metrics(카디널리티 그룹핑),
   invariant SQL 2종(oversell·dup_orders)의 검증 논리.
4. 재심기 후 정적 검증(mypy strict, ruff) + seed 생성기 실행 검증 + SQL 렌더링 확인.

---

## 2. 불합격 1 — P1-07: 결제 대기 중 커넥션을 실제로 쥐지 않았음

### 발견 (before)

```python
# 28f23c2 시점, app/orders/service.py
async with session.begin():
    locked = await repository.get_order(session, order.id)  # 커넥션 확보 + 트랜잭션 시작
    result = payment_client.pay(order.id, float(total))
```

- `repository.get_order` = `session.get(Order, pk)`. 이 order 는 `create_order` 에서
  add→commit→refresh 를 거쳐 **identity map 에 존재**하고, `expire_on_commit=False` 라
  만료되지도 않는다 → `session.get` 은 **SQL 을 전혀 내보내지 않고** 캐시 객체를 반환.
- SQLAlchemy 의 `session.begin()` 은 lazy — **첫 SQL 실행 시점에야 커넥션을 체크아웃**한다.
- 결과: `pay()` 블로킹(~800ms) 동안 이 세션이 점유한 풀 커넥션은 **0개**.
  커넥션은 블록 종료 commit 의 flush(UPDATE+INSERT) 때 잠깐만 잡힌다.
- 판정: 주석("커넥션 확보")이 사실과 다르고, 백로그의 재현 조건
  ("pool 기본값에 주문 200vu → pool timeout 다발")이 성립 불가.
  특히 P1-06 fix(httpx 전환) 이후 P1-07 의 독립 재현이 불가능해진다. → **break 재작업**

### 재심기 (after)

- `app/orders/repository.py:55` — `get_order_for_update` 추가:
  `SELECT ... FOR UPDATE`. identity map 에 객체가 있어도 반드시 SQL 이 나가므로,
  트랜잭션이 커넥션을 체크아웃해 **커밋까지 쥔다** (+ 주문 로우 락).
- `app/orders/service.py:70-71` — begin 블록 안에서 `get_order_for_update` 호출로 교체.
  순진한 코드로서의 명분: "결제하는 동안 주문이 안 바뀌게 잠근다" — 실제로 흔한 안티패턴.
- 표식 주석에 verify-break 에서의 발견 경위(왜 session.get 형태로는 성립하지 않는지)를 명시.

이제 결제 대기 동안 **커넥션 1개 + 주문 로우 락**이 점유되므로, 주문 동시성이
풀 크기(5+10)를 넘는 순간 pool timeout 이 백로그 정의대로 발생할 수 있다.

---

## 3. 불합격 2 — P2-03: 락 순서가 사실상 PK 정렬이라 교차가 성립하지 않았음

### 발견 (before) — 두 겹의 문제

1. **조회 순서**: `get_cart_items` 의 SELECT 에 ORDER BY 가 없었다. cart_items 의 PK 가
   `(user_id, product_id)` 이고 `WHERE user_id = X` 는 선택도가 높아 PG 는 거의 확실히
   PK 인덱스 스캔을 택한다 → 반환 순서 = **product_id 오름차순** = 백로그 fix
   ("PK 정렬 후 잠금")와 동일. 즉 deadlock 이 P1-08 커밋 마스킹과 **별개로, 구조적으로도**
   발현 불가능한 상태였다.
2. **seed 주장 불일치**: `gen_cart_items` 주석은 "같은 상품 조합을 서로 다른 순서로 담은
   카트"를 만든다고 했지만, 실제로는 50,000 유저 × 약 20만 상품에서 무작위 20,000쌍
   (유저당 기대 카트 0.4개) — 두 유저가 상품 2개 이상을 공유할 확률은 사실상 0.
   **교차 카트는 의도적으로 만들어지지 않았다.**

### 재심기 (after)

- `app/cart/repository.py:41` — 카트 조회를 `ORDER BY cart_items.ctid` (물리 삽입 순서 =
  담은 순서)로 정렬. §1 스키마의 cart_items 엔 담은 시각 컬럼이 없으므로 ctid 가
  "담은 순서"의 대리 표현이다 — **실험 장치임을 표식 주석에 명시**했다.
- `seed/seed.py:43-45, 212` — 유저 **201..1200** (헤비 유저 1..200 과 분리)을
  교차 카트 쌍 500개로 구성: 쌍의 두 유저가 같은 상품 두 개(p1, p2)를 **서로 반대
  순서로** 담는다. COPY 는 yield 순서 그대로 적재(=ctid 순서)하므로, 이 두 카트로
  동시에 주문하면 재고 락 획득 순서가 실제로 교차한다 (A: p1→p2, B: p2→p1).
  나머지 18,000건 무작위 카트는 교차 유저 범위 밖에서만 뽑아 오염을 방지.
- `app/orders/service.py:44` — P2-03 표식 주석을 실제 메커니즘에 맞게 정정.

### 유지된 설계와 한계

- **P1→P2 마스킹 의존은 그대로**: P1-08(건별 commit)이 매 아이템마다 락을 즉시 풀어
  지금은 deadlock 이 발현하지 않고, P1-08 fix 로 트랜잭션이 합쳐지는 Phase 2 에 발현한다.
- ctid 는 upsert 로 qty 가 갱신되면 새 튜플로 바뀌어 순서가 흐트러진다 —
  P2-03 재현 시나리오는 seed 교차 카트(주문해도 카트가 안 비워지므로 반복 사용 가능,
  P2-04 부재의 부수 효과) 또는 k6 가 새로 담은 카트를 쓴다.
- **seed 변경분은 `make seed` 재실행 후에만 DB 에 반영된다** (P2-03 measure 전 필수).

---

## 4. 합격 20건 — 백로그 정의와 일치 확인

| ID | 위치 | 확인 내용 |
|---|---|---|
| P1-01 | app/auth/service.py:19 | 프로세스 dict 세션 + /me 가 그 dict 조회. instance_id 로 관찰 가능 |
| P1-02 | app/orders/service.py:82 | 루프 내 명시적 개별 쿼리 (1+N+N·M). lazy="raise" 로 노이즈 차단 |
| P1-03 | app/models.py:70 + app/products/repository.py:21 | PK 외 인덱스 0개(UNIQUE 포함 미설정, 근거 주석), 선행 와일드카드 ILIKE |
| P1-04 | app/products/repository.py:32 | offset=page×size, page 상한 없음 (ge=0 만) |
| P1-05 | app/products/repository.py:40 | 매 요청 필터 위 COUNT(*) |
| P1-06 | app/payments/client.py:19 | 동기 requests(timeout 미설정)를 async 경로에서 직접 호출 |
| P1-08 | app/orders/service.py:54 | 루프 내 건별 INSERT + 건별 commit |
| P1-09 | app/core/db.py:16 + deploy/Dockerfile.app:29 | 풀 기본값(5+10) + uvicorn 워커 1 |
| P1-10 | app/auth/service.py:44 | bcrypt cost 12 checkpw 를 이벤트 루프에서 직접 실행 |
| P1-11 | app/cart/repository.py:23 + app/orders/repository.py:64 | 양쪽 모두 LIMIT 없음, 헤비 유저(3,000건) seed 존재 |
| P1-12 | app/core/deps.py:17 | try/finally 없는 yield — 예외 시 close 미도달 |
| P2-01 | app/deals/service.py:17 + app/deals/repository.py | check-then-act, 가드 없는 UPDATE |
| P2-04 | app/orders/service.py:36 | 멱등 장치 부재 + 카트 미비움 (컬럼 미리 안 넣음 — §1 준수) |
| P2-05 | app/products/repository.py:61 | 전 기간 800만 행 GROUP BY, 캐시 없음 |
| P2-07 | app/payments/client.py:24 | while True 즉시 재시도, 백오프·상한·timeout 없음 |
| P2-08 | app/main.py:6 + deploy/compose.yaml:151 | 헬스체크·graceful shutdown 구조적 부재 표식 |
| P2-09 | app/orders/repository.py:80 | 요청마다 orders×order_items 창 집계, created_at 인덱스 없음 |

문제 외 코드 정상성: metrics 는 라우트 템플릿 라벨링 + untemplated 그룹핑(§9 카디널리티 주의 준수),
invariant SQL 은 oversell(ledger_mismatch 포함)·dup_orders(시간창 페어링) 모두 검증 논리 타당.

---

## 5. 참고사항 (measure 설계 시 유의 — plant 는 유지)

- **P1-12**: (i) 세션은 첫 SQL 전엔 커넥션이 없으므로 **"DB 쿼리 이후에 나는 에러"만
  누수를 만든다** — 401(쿼리 전 의존성 에러) 유발 요청으로는 안 샌다. k6 에러 믹스 설계에 반영.
  (ii) CPython refcount 가 버려진 세션을 회수하면 SQLAlchemy 가 non-checked-in 커넥션을
  terminate 시켜 "서서히 고갈" 대신 "경고 로그 + 커넥션 churn"으로 나타날 수 있다.
  재현이 약하면 §0-7 대로 조건 조정 과정을 기록한다.
- **P1-03 백로그 문구**: 백로그의 "status/기간 필터"는 §1 스키마(products 에 status 없음)와
  맞지 않는다. 구현(카테고리+ILIKE)은 §1 API 표와 일치 — fix 의 복합 btree 는 category_id 기준.
- **사소(수용)**: deals 구매가 opens_at/closes_at 창을 검사하지 않음(seed 딜이 항상 열려
  있어 실험 무해). 딜 주문이 결제 호출 없이 즉시 PAID(P2-02 의 202 패턴 전환 예정이라 단순화 수용).

---

## 6. 재심기 후 재검증

- `grep -rn "INTENDED-ISSUE"` — 22곳 → **23곳** (P2-03 표식이 cart/repository.py 에 추가됨).
  모든 ID 가 백로그와 1:1 대응, 잔여 불일치 없음.
- 정적 검증: `mypy` strict **no issues (39 files)**, `ruff check` / `ruff format --check` 통과.
- seed 생성기 실행 검증: 총 20,000행, PK(user_id, product_id) 중복 0,
  교차 쌍 500개 전부 "정확히 역순" 확인 (`by_user[a] == reversed(by_user[b])`),
  무작위분은 교차 유저 범위(201..1200) 밖에서만 생성.
- SQL 렌더링 확인: 카트 조회가 `... WHERE cart_items.user_id = :p ORDER BY cart_items.ctid` 로 컴파일.
- 런타임(부하) 재현 확인은 verify-break 범위가 아니다 — 각 이슈의 measure 단계에서 수행.

## 7. 후속

- [ ] 사용자 승인 (§7-2 게이트) — 승인 기록은 각 이슈 measure 시작 시
      `docs/experiments/<id>.md` 의 "재현 조건" 위에 남긴다.
- [ ] 승인 후: §14-5 `load/k6/mixed.js` + smoke(10vu·1m) → `git tag phase-0`.
- [ ] P2-03 measure 전 `make seed` 재실행 (교차 카트 반영).
