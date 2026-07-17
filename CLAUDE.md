# CLAUDE.md — FlashMart: 부하·확장성 실험실 (Fail & Fix Lab)

선착순 특가 커머스를 소재로 한 **학습용 부하 실험 프로젝트**다.
실서비스가 아니다. 의도적으로 문제 있는 코드를 심고 → 부하로 터뜨리고 → 측정하고 → 고친 뒤,
그 전 과정을 **git 히스토리와 실험 로그로 추적 가능하게 남기는 것**이 목적이다.

로컬 docker compose에서 시작해 Phase 3에서 AWS로 이전한다.

---

## 0. 최상위 규칙 — 다른 모든 관례보다 우선한다

1. **의도된 문제를 미리 고치지 말 것.**
   이슈 백로그(§6)에 "심는 문제"로 명시된 코드는 Phase 0에서 반드시 그 문제를 포함한 채 작성한다.
   베스트 프랙티스로 "개선"하지 않는다. 수정은 해당 이슈의 measure(재현·측정) 이후에만 허용된다.
2. **문제를 심은 지점에는 주석 표식을 남긴다.** `# INTENDED-ISSUE: P1-02` 형식.
   fix 단계에서 해당 주석을 제거한다. (`grep -rn "INTENDED-ISSUE"`로 남은 문제를 조회)
3. **모든 fix 커밋에는 전/후 수치를 남긴다.**
   예: `fix(P1-02): selectinload 적용 (쿼리 201→3회, p95 1.9s→160ms @100vu)`
4. **이슈 사이클 고정: break → verify-break(검증·승인) → measure → fix → verify → log.** 단계 생략 금지. 특히 verify-break의 사용자 승인 없이는 measure로 넘어가지 않는다. (§7)
5. **Phase와 이슈는 사용자가 지시할 때만 진행한다.** 세션 시작 시 현재 이슈 ID를 확인하고,
   한 번에 하나의 이슈만 다룬다.
6. **실험 로그 없으면 미완료.** `docs/experiments/<ID>.md`가 갱신되어야 이슈 완료로 간주한다.
7. **결과를 조작하지 않는다.** 문제가 재현되지 않으면 그대로 기록하고,
   재현 조건(데이터량·동시성·리소스 제한)을 조정한 과정도 로그에 남긴다.
8. **세션 시작 시 이슈에 맞는 모델을 사용자에게 제안한다.** (§15) 실행 중인 모델은 스스로 모델을 바꿀 수 없으므로,
   현재 이슈가 상향/하향 대상이면 "이 작업은 <모델>(effort <레벨>) 권장 — `/model`로 전환 후 진행하시겠어요?"라고 먼저 묻는다.
   사용자가 유지하겠다면 현재 모델로 진행한다.

---

## 1. 서비스 정의

**FlashMart** — 선착순 특가 딜이 있는 미니 커머스. 프론트엔드 없음, REST API 전용 (클라이언트는 k6).
도메인은 수단이다. 각 기능은 특정 부하 문제를 재현하기 위해 존재한다 (§6 매핑 참고).

### 기능 / API
| 기능 | 엔드포인트 | 재현 목적 (이슈) |
|---|---|---|
| 회원가입/로그인/내정보 | `POST /auth/signup` `POST /auth/login` `GET /auth/me` | 세션 상태 → stateless (P1-01) |
| 상품 목록·검색 | `GET /products?category=&q=&page=` | 인덱스, OFFSET, COUNT (P1-03~05) |
| 상품 상세 | `GET /products/{id}` | 읽기 트래픽 소재 |
| 메인 인기 상품 | `GET /main/popular` | 집계 쿼리 + 캐시 스탬피드 (P2-05) |
| 장바구니 | `POST /cart/items` `GET /cart` | 다중 상품 락 순서 (P2-03) |
| 주문 생성/내역 | `POST /orders` `GET /orders` `GET /orders/{id}` | 트랜잭션 경계, N+1, 멱등성 (P1-02,06~08, P2-04) |
| 선착순 딜 구매 | `POST /deals/{id}/purchase` | 핫 로우, oversell, 스파이크 (P2-01,02) |
| 실시간 판매 랭킹 | `GET /rankings/realtime` | OLTP 위 집계 간섭 (P2-09) |
| 결제 mock (별도 앱) | `POST /pay` — `LATENCY_MS`, `FAIL_RATE` env로 제어 | 외부 의존성 지연·장애 주입 (P1-06,07, P2-07) |

### 데이터 모델 (초기 스키마)
- `users(id, email, pw_hash, created_at)`
- `categories(id, name)` / `products(id, category_id, name, description, price, stock, created_at)`
- `reviews(id, product_id, user_id, rating, body)` — 목록에 평점·리뷰수 노출용 (N+1·집계 소재)
- `deals(id, product_id, deal_price, total_qty, remaining_qty, opens_at, closes_at)` — 핫 로우
- `cart_items(user_id, product_id, qty)`
- `orders(id, user_id, status[PENDING|PAID|FAILED], total_amount, created_at)` / `order_items(id, order_id, product_id, qty, unit_price)`
- `payments(id, order_id, status, pg_tx_id, created_at)`

주의: **Phase 0 스키마에는 PK 외 인덱스를 만들지 않는다** (P1-03의 소재).
`idempotency_key` 같은 수정용 컬럼도 미리 넣지 않는다 — 해당 이슈의 fix 마이그레이션에서 추가.

### seed 규모 (문제가 보이려면 데이터가 커야 한다)
users 5만 / products 20만(카테고리 50) / reviews 100만 / orders 300만 / order_items 800만.
seed는 실험 대상이 아니므로 **COPY 기반**으로 빠르게 (루프 INSERT 금지). `make seed`, 목표 수 분 내.

---

## 2. 기술 스택
- Python 3.12+, FastAPI, uvicorn
- SQLAlchemy 2.0 (async) + asyncpg, Alembic
- PostgreSQL 16, Redis 7 (세션/캐시/큐 — Phase에 따라 도입)
- nginx — L7 LB (로컬에서 ALB 역할)
- k6 (부하), Prometheus + Grafana + postgres_exporter + redis_exporter (관측)
- docker compose로 전 구성 실행. mockpg는 초경량 FastAPI 별도 앱.
- toxiproxy — app↔DB/Redis 사이 네트워크 지연·단절 주입 (P2-13/14 및 Phase 3 AZ 장애 리허설을 로컬에서 미리 재현)

## 3. 저장소 구조
```
flashmart/
├── app/
│   ├── main.py
│   ├── core/            # config, db, redis, deps, metrics
│   ├── auth/ products/ deals/ cart/ orders/ payments/   # 모듈별 router/service/repository
│   └── workers/         # Phase 2: 딜 주문 확정 consumer
├── mockpg/              # 외부 결제 mock
├── migrations/          # alembic
├── seed/
├── load/
│   ├── k6/              # mixed.js, p1-03.js, p2-01.js ...
│   └── checks/          # oversell.sql, dup_orders.sql (invariant 검증)
├── deploy/
│   ├── compose.yaml  compose.obs.yaml
│   └── nginx/  prometheus/  grafana/
├── docs/experiments/    # _template.md, P1-01.md ...
├── Makefile
└── CLAUDE.md
```

## 4. 명령어 (Makefile로 제공할 것)
```
make up            # 기본 기동 (app 1대)
make up N=3        # app N대 + nginx LB
make down / logs
make migrate / make revision m="..."
make seed / make reset-deal        # 딜 수량·주문 초기화 (스파이크 실험 전 필수)
make load S=p1-03  # load/k6/p1-03.js 실행
make check S=oversell              # load/checks/oversell.sql 실행
make psql / make redis-cli
make kill-one      # 부하 중 앱 인스턴스 1대 강제 종료 (P2-08)
make pause-redis / make unpause-redis   # Redis 장애 주입/복구 (P2-13)
make stats         # docker stats — 리소스 제한 실제 적용 확인 (§13)
make grafana       # localhost:3000
```

---

## 5. Phase 로드맵 & 관문

수치는 리소스 제한 하의 로컬 기본값이다. 머신 성능에 따라 절대치보다 **전/후 상대 비교**가 본질.
(TPM 표기가 필요하면 TPM = TPS × 60으로 병기)

| Phase | 주제 | 구성 | 관문 (통과 조건) |
|---|---|---|---|
| **0** | 부하 미고려 순진한 구현 | app 1대 + PG 1대 | 전 기능 동작, smoke(10vu·1m) 통과, 심는 문제 전부 포함 + `INTENDED-ISSUE` 주석 → tag `phase-0` |
| **1** | 수백 TPS — scale-out과 쿼리 기초 체력 | nginx + app 3대 + PG + Redis(세션·캐시) | mixed 300 TPS 5분: p95<300ms, err<1% → tag `phase-1-fixed` |
| **2** | 수천 TPS + 스파이크 — 동시성·비동기·복제·장애 | + worker(Redis Streams) + PG replica + 장애 주입 | 평시 1,000 TPS + 딜 오픈 5,000 req/s 10초: oversell 0, 중복주문 0, err<1%, 인스턴스 kill 중 err<0.5% → tag `phase-2-fixed` |
| **3** | AWS 이전 | §13 매핑 + Terraform | 로컬과 동일 시나리오 재현, RDS failover 실험 |

### 아키텍처 진화 (목표 상태)
```
Phase 0:  k6 → app ──────────────→ PostgreSQL
Phase 1:  k6 → nginx → app×3 ────→ PostgreSQL
                        └────────→ Redis (session, cache)
Phase 2:  k6 → nginx → app×3 ─┬──→ PG primary ──(streaming)──→ PG replica(읽기)
                              ├──→ Redis (session/cache/딜 선점/Streams 큐)
                              │         └→ worker×N → PG primary (주문 확정)
                              └──→ mockpg (지연·실패율 주입)
```
설계 원칙: app은 완전 stateless(상태는 전부 PG/Redis), 어떤 인스턴스가 죽어도 서비스 지속,
쓰기는 primary·읽기는 replica 분산, 스파이크는 큐로 흡수(202 접수 패턴).

---

## 6. 이슈 백로그 — 심는 문제와 터뜨리는 방법

### Phase 1: 수백 TPS에서 터지는 것들
| ID | 기능 | 심는 문제 (Phase 0) | 재현 방법 | 수정 방향 | 완료 기준 |
|---|---|---|---|---|---|
| P1-01 | 로그인 세션 | 프로세스 내 dict에 세션 저장 | app 2대(또는 워커 2)에서 로그인 후 `/auth/me` 반복 → 랜덤 401 | Redis 세션(또는 JWT) → stateless화 | app 3대 + 롤링 재시작에도 세션 유지 |
| P1-02 | 주문 내역 | 주문→아이템→상품을 루프 내 개별 조회 (N+1) | 주문 30건 유저로 `GET /orders` 부하, 쿼리 로그·pg_stat 확인 | selectinload/JOIN, 필요 시 요약 컬럼 | 요청당 쿼리 수 상수(≤3), p95 전/후 기록 |
| P1-03 | 상품 검색 | `ILIKE '%q%'` + status/기간 필터에 인덱스 없음 | 20만 상품에서 검색 50vu → seq scan, p95 수 초 | 복합 btree + pg_trgm GIN | EXPLAIN에서 Index Scan, p95<200ms |
| P1-04 | 상품 목록 | OFFSET 페이지네이션 | 깊은 페이지(page 5000급) 시나리오 | keyset(cursor) 페이지네이션 | 깊은 페이지에서도 p95 평탄 |
| P1-05 | 목록 total | 매 요청 `COUNT(*)` | 목록 부하 중 pg_stat_statements 상위 쿼리 확인 | count 제거/캐시/근사치(reltuples) | 목록 경로에서 COUNT 소멸 |
| P1-06 | 결제 호출 | 동기 `requests`로 mockpg 호출 (이벤트 루프 블로킹) | mockpg LATENCY=800ms, 주문 50vu → **무관한 GET까지** 지연 | httpx AsyncClient | 주문 부하 중 `GET /products` p95 영향 없음 |
| P1-07 | 주문 트랜잭션 | DB 트랜잭션 내부에서 결제 API 호출 | pool_size=10, 주문 200vu → pool timeout 다발 | 트랜잭션 분리 + 주문 상태머신(PENDING→PAID) | pool wait 0, 주문 처리량 회복 |
| P1-08 | 주문 저장 | order_items를 루프 INSERT(건별 commit) | 아이템 10개 주문 부하 | bulk insert + 단일 트랜잭션 | 주문당 INSERT 왕복 1회 |
| P1-09 | 인프라 | uvicorn 워커 1, 풀 기본값, 단일 인스턴스 | mixed 300 TPS 시도 → 한계 확인 | nginx + app 3대, 워커·풀·nginx 튜닝 | **P1 관문** 통과 |
| P1-10 | 로그인 해싱 | bcrypt(cost 12+)를 async 핸들러에서 직접 실행 (CPU 블로킹) | 로그인 100vu 스파이크 → **무관한 GET까지** 지연 (P1-06과 달리 CPU-bound) | `run_in_executor`/스레드풀 오프로드 (또는 해싱 워커 분리) | 로그인 부하 중 `GET /products` p95 영향 없음 |
| P1-11 | 목록 응답 크기 | `GET /cart`·`GET /orders`에 LIMIT 없이 전체 반환 | 주문 수천 건 헤비 유저 섞어 부하 → 직렬화·메모리 폭증 | 강제 페이지네이션 + `max_limit` 상한 | 응답 크기·p95 상한, N+1(P1-02)과 독립 검증 |
| P1-12 | 세션 누수 | 예외 경로에서 DB 세션/커넥션 미반환 | mixed에 5% 에러 유발 요청 섞어 장시간 → 풀이 **서서히** 고갈 | 요청 스코프 세션의 확실한 정리(context manager/finally) | 장시간 부하에도 active connection 평탄, 누수 0 |

### Phase 2: 수천 TPS + 스파이크에서 터지는 것들
| ID | 기능 | 심는 문제 / 상황 | 재현 방법 | 수정 방향 | 완료 기준 |
|---|---|---|---|---|---|
| P2-01 | 선착순 구매 | `SELECT` 재고 확인 후 `UPDATE` (check-then-act) | 딜 수량 1,000에 3,000vu 10초 스파이크 | 1차: 조건부 원자 UPDATE `... AND remaining_qty>0` | `check S=oversell` 결과 0 |
| P2-02 | 〃 (후속) | 원자 UPDATE도 단일 로우 락 직렬화 → TPS 한계, p99 폭발 | 동일 스파이크에서 lock wait·p99 관찰 | Redis Lua 선점 차감 + Streams 큐 + worker 확정, API는 202 접수 | 스파이크 흡수, oversell 0 유지, 접수 p95<100ms |
| P2-03 | 장바구니 주문 | 재고 차감 락을 담은 순서(임의)로 획득 | 교차 장바구니 동시 주문 → deadlock 로그 | PK 정렬 후 잠금 (또는 단일 원자 배치 UPDATE) | deadlock 0 |
| P2-04 | 주문 생성 | 재시도·더블클릭 시 중복 주문 | k6에서 동일 요청 2연발 | `Idempotency-Key` 헤더 + unique 제약 + 응답 재생 | `check S=dup_orders` 0 |
| P2-05 | 인기 상품 | 무거운 집계 + 고정 TTL 캐시 | TTL 만료 시점에 부하 정렬 → 동시 miss로 DB 폭주 | single-flight 락 + TTL jitter (+soft TTL) | 만료 순간 원본 쿼리 1회 |
| P2-06 | 읽기 확장 | 모든 읽기가 primary | 읽기 부하 증대 → primary 포화. replica 도입 후 "방금 주문이 안 보임" 재현 | replica 라우팅 + read-your-writes(쓰기 직후 primary 고정) | 읽기 분산 + 정합성 시나리오 통과 |
| P2-07 | 결제 장애 | 실패 시 즉시 무한 재시도 | mockpg FAIL_RATE=0.5 → 재시도 폭풍으로 자체 과부하 | timeout + 지수 백오프 + 시도 상한 + circuit breaker | 장애 중 fast-fail, 복구 후 자동 정상화 |
| P2-08 | 배포·장애 | 종료 시그널 무시, 헬스체크 없음 | 부하 중 `make kill-one` / 롤링 재시작 → 5xx | graceful shutdown + nginx health check | kill 중 err<0.5%, 롤링 무중단 |
| P2-09 | 실시간 랭킹 | 요청마다 orders GROUP BY | 주문 부하와 동시 조회 → OLTP 간섭 | Redis sorted set 집계 (대안: 배치 테이블, replica 격리) | 랭킹 조회가 주문 p95에 영향 없음 |
| P2-10 | worker 확정 | at-least-once 전달인데 consumer가 비멱등 (ack 전 죽으면 재처리) | P2-02 큐 도입 후 처리 도중 `make kill-one` → 같은 메시지 재전달로 중복 확정 | idempotent consumer(처리키 unique 제약/dedup) | 재전달 발생시에도 중복 확정 0 (P2-04와 다른 층위) |
| P2-11 | 큐 운영 | worker 처리량 < 유입량 + poison message 무방비 | 유입 > 처리 스파이크로 Streams 무한 성장, 파싱불가 메시지 1개로 crash loop | lag/PEL 모니터링, consumer 스케일아웃, 재시도 상한 + DLQ | 스파이크 후 lag 수렴, poison 격리(서비스 지속) |
| P2-12 | 핫로우 bloat | 스파이크 반복 후 딜 테이블 dead tuple 누적 (autovacuum 못 따라감) | P2-01/02 스파이크 여러 회 반복 → 딜 경로 점진적 성능 저하, `pg_stat_user_tables` 확인 | 테이블별 autovacuum 튜닝, fillfactor 조정(HOT update) | 반복 스파이크에도 딜 p95 안정, dead ratio 임계 이하 |
| P2-13 | Redis 장애 | 세션·캐시·큐·선점을 전부 Redis에 의존, 폴백 없음 | `docker pause redis` → 전면 장애 | 캐시 miss시 DB fallback, 랭킹 폴백, 짧은 timeout — 부분 열화(graceful degradation) | Redis 다운 중에도 핵심 읽기 경로 생존, 복구 후 자동 정상화 |
| P2-14 | 타임아웃 계층 | k6 < nginx < 앱 처리시간 불일치, DB `statement_timeout` 미설정 | 느린 요청에서 클라 타임아웃 후 재시도 → 서버는 좀비 작업 지속 → 부하 자기증폭 | 계층별 timeout 정렬(k6 > nginx > 앱 > DB) + `statement_timeout` | 타임아웃 시 좀비 작업 없음, 재시도 폭주 시 부하 발산 안 함 |
| P2-15 | 무중단 마이그레이션 | P1-03 인덱스 생성을 `CONCURRENTLY` 없이 부하 중 실행 | 부하 중 인덱스 생성 → 쓰기 블로킹으로 5xx (fix 자체가 장애를 냄) | `CREATE INDEX CONCURRENTLY` + alembic `autocommit_block` | 부하 중 인덱스 생성해도 err<1%, 쓰기 무중단 |

각 fix에는 트레이드오프가 있다 (예: 202 접수 패턴은 클라이언트 복잡도↑, replica는 지연 정합성 문제 발생).
실험 로그의 "트레이드오프" 항목에 반드시 기록한다.

---

## 7. 워크플로우 — 이슈 1개 처리 사이클

사용자가 "P1-03 하자"라고 하면:

1. **break** — Phase 0에 이미 심어져 있으면 코드 위치만 확인. 없으면 이 커밋에서 심는다.
2. **verify-break (검증·승인 게이트)** — 심은 문제가 백로그의 "심는 문제"와 정확히 일치하는지 스스로 점검한 뒤, **사용자 승인을 받고 나서** measure로 넘어간다. 승인 없이 진행하지 않는다.
   - 점검 항목: (a) 심은 위치·방식이 백로그 정의와 일치하는가 (예: N+1을 async lazy-load가 아니라 루프 내 명시적 개별 쿼리로 심었는가), (b) `INTENDED-ISSUE: <ID>` 주석이 정확한 지점에 있는가, (c) 실수로 미리 고치거나 관련 없는 개선을 하지 않았는가, (d) 문제 외의 코드는 정상적으로 작성됐는가(실험 노이즈 차단).
   - 산출물: 심은 지점 요약(파일·함수·라인), `grep -rn "INTENDED-ISSUE: <ID>"` 결과, "왜 이게 백로그의 그 문제인지" 1~2줄 근거를 사용자에게 제시.
   - **승인**: 사용자가 명시적으로 확인("맞다/진행")해야 measure로 진행. 어긋나면 break로 되돌아가 다시 심는다. (승인 기록을 `docs/experiments/<id>.md`의 "재현 조건" 위에 남긴다.)
3. **measure** — `load/k6/<id>.js` 작성·실행. k6 summary + Grafana + pg_stat_statements + `EXPLAIN (ANALYZE, BUFFERS)` 수집.
   핵심 수치를 measure 커밋 메시지에 요약. 재현 실패 시 조건 조정 과정도 기록.
   - 주의: 여기서 재현이 안 되면 원인은 둘 중 하나 — "문제가 제대로 안 심겨서"(→ break로 복귀) 또는 "재현 조건이 약해서"(→ 조건 강화). verify-break를 통과했으므로 후자부터 의심한다.
4. **fix** — 백로그의 "수정 방향"으로 **최소 수정**. `INTENDED-ISSUE` 주석 제거. 전→후 수치를 커밋 메시지에.
5. **verify** — 동일 시나리오 재실행 + invariant 체크(`load/checks/`) + mixed 스모크로 회귀 확인.
6. **log** — `docs/experiments/<id>.md` 작성.

### 커밋 컨벤션
```
<type>(<ISSUE-ID>): <요약>        # type ∈ break | verify-break | measure | fix | verify | feat | chore | docs
```
- Phase 0 기능 구현: `feat(P0)[P1-02,P1-08]: 주문 API (N+1·루프 INSERT 포함)` — 심은 이슈 ID 병기
- 이력 조회: `git log --oneline --grep P1-02` → 문제→재현→해결이 한 줄기로 보여야 한다
- Phase 경계 태그: `phase-0`, `phase-1-fixed`, `phase-2-fixed`

### 실험 로그 템플릿 (`docs/experiments/_template.md`)
```markdown
# <ID> <제목>
## 증상 / 가설
## 심은 지점 & 검증 승인 (파일·함수·라인, INTENDED-ISSUE 위치, 승인 일시)
## 재현 조건 (시나리오 파일, 데이터 상태, 리소스 제한)
## Before  — TPS, p50/p95/p99, err%, DB 지표 + 근거(EXPLAIN, 캡처 경로: assets/)
## 원인 분석
## 수정 (커밋 해시)
## After   — 동일 표
## 트레이드오프 & 남은 한계
## 배운 것 (한 줄)
```

---

## 8. 부하 테스트 규칙

- 도구: **k6**. 시나리오는 `load/k6/`에 이슈 ID로 저장 — 누구든 같은 명령으로 재현 가능해야 한다.
- 공용 트래픽 믹스 `mixed.js`: 목록 35 / 상세 25 / 검색 10 / 주문 15 / 내역 10 / 로그인 5 (%)
  - **Phase 2 믹스(`mixed-p2.js`)**: 인기 상품·실시간 랭킹 조회를 포함해야 P2-05/09 소재가 관문 트래픽에서 실제로 자극됨. 예: 목록 25 / 상세 20 / 검색 8 / 인기 10 / 랭킹 7 / 주문 20 / 내역 10 (딜 스파이크는 별도 시나리오로 중첩).
- 프로파일 3종: `smoke`(10vu·1m) / `target`(관문 수치·5m) / `limit`(한계까지 ramp)
- 표준 지표: TPS, p50/p95/p99, error rate, DB active connections, lock waits, CPU
- **리소스 제한 필수 — AWS 인스턴스 유사 환경으로 고정**: 제한 없으면 로컬 사양에 묻혀 문제가 안 터지고, 로컬↔AWS(Phase 3) 결과 비교도 무의미해진다. compose `deploy.resources.limits`로 컨테이너별 vCPU·RAM을 실제 인스턴스 타입에 맞춰 고정한다 (§13 참조). k6·관측 스택도 남은 코어를 소모하므로, **부하 대상 컨테이너 총합을 호스트 환경에 맞춰** 배분할 것.
- 스파이크 실험 전 `make reset-deal`로 상태 초기화. invariant는 부하 후 `make check`로 검증.
- 기능 정확성 pytest는 최소한으로. 이 프로젝트의 "테스트"는 부하 시나리오 + invariant SQL이다.

## 9. 관측 (Observability)
- app: prometheus-fastapi-instrumentator / DB: postgres_exporter / Redis: redis_exporter
- Grafana 프로비저닝 대시보드: 요청량·p95·에러, DB 커넥션·락·slow query, Redis
- PostgreSQL: `pg_stat_statements` 활성(shared_preload_libraries), `log_min_duration_statement=200ms`
- **메트릭 카디널리티 주의**: instrumentator가 path를 raw로 라벨링하면 `/products/{id}`가 20만 시계열이 되어 Prometheus가 먼저 죽는다. 반드시 라우트 템플릿(`/products/{id}`)으로 그룹핑할 것. (원한다면 이 자체를 미니 이슈로 심어 재현해도 좋다.)
- 실험 캡처 이미지는 `docs/experiments/assets/`에 저장

## 10. 코딩 컨벤션
- 레이어: router → service → repository. 트랜잭션 경계는 service 레이어 (Phase 0 의도 위반: P1-07)
- async 일관: 라우터~DB까지 async, 블로킹 호출 금지 (Phase 0 의도 위반: P1-06)
- 세션은 요청 스코프 의존성 주입. 설정은 env(pydantic-settings). 타입힌트 필수, ruff + mypy.
- 의도 위반 목록에 없는 코드는 정상적으로 잘 작성한다 — 실험 노이즈를 줄이기 위해.

## 11. 로컬 함정 노트 (미리 알아둘 것)
- **DB 총 커넥션 = 인스턴스 수 × uvicorn 워커 × (pool_size + max_overflow).** PG `max_connections`(기본 100) 초과 주의 — P1-09에서 직접 계산해 튜닝한다.
- nginx 업스트림은 docker DNS 동적 해석이 필요: `resolver 127.0.0.11 valid=5s;` + 변수 proxy_pass. 아니면 scale 시 구주소를 캐시한다.
- app 스케일은 `docker compose up --scale app=N` (호스트 포트 바인딩 제거, nginx만 노출).
- async SQLAlchemy는 lazy loading이 에러를 내므로, N+1은 **루프 내 명시적 개별 쿼리**로 심는다.
- PG replica(P2-06)는 bitnami/postgresql의 `POSTGRESQL_REPLICATION_MODE` env 구성이 가장 간단.
- macOS docker는 I/O 오버헤드가 크다 — 절대치보다 전/후 상대 비교 중심으로 해석.
- `CREATE INDEX CONCURRENTLY`는 트랜잭션 블록 안에서 못 돈다 — alembic에서는 `op.get_context().autocommit_block()`으로 감싸야 한다 (P2-15).
- Redis를 세션·캐시·큐에 함께 쓸 때 단일 장애점이 된다 — 장애 주입 실험(P2-13)은 `docker pause redis`로, 복구는 `docker unpause`로. `docker stop`은 커넥션 리셋이라 timeout 실험과 결이 다르니 구분할 것.
- `deploy.resources`는 Swarm 전용 키라 `docker compose up`(v2 standalone)에서 **조용히 무시될 수 있다** — 이때는 최상위 `cpus:`/`mem_limit:`로 대체하거나 `docker compose --compatibility up`을 쓴다. 리소스 제한이 실제 걸렸는지 `docker stats`로 반드시 확인(제한이 안 걸리면 문제가 안 터진다).

## 12. AWS 매핑 (Phase 3 개요 — 상세는 Phase 2 완료 후 확장)
| 로컬 | AWS |
|---|---|
| nginx | ALB |
| app 컨테이너 ×N | ECS Fargate + Auto Scaling |
| PG primary/replica | RDS PostgreSQL Multi-AZ + Read Replica |
| Redis | ElastiCache |
| Redis Streams 큐 + worker | SQS + ECS worker |
| mockpg | 컨테이너 유지 (또는 Lambda) |
| Prometheus/Grafana | CloudWatch + Managed Grafana |
Phase 3 과제: Terraform화 → 동일 k6 시나리오 재현 → RDS 강제 failover 실험 → ASG 스케일링 정책.

---

## 13. 리소스 프로파일 — AWS 인스턴스 유사 환경

컨테이너를 실제 AWS 인스턴스 타입에 맞춰 vCPU·RAM을 고정한다. 목적은 (1) 로컬에서 문제가 실제로 터지게 만들고, (2) Phase 3 AWS 이전 시 로컬↔클라우드 결과를 직접 비교 가능하게 하는 것. **절대치보다 전/후 상대 비교가 본질**이지만, 프로파일을 고정해두면 세션·머신 간 재현성이 확보된다.

### 기준 프로파일 (compose profile로 스위칭)
| 역할 | AWS 유사 타입 | vCPU (`cpus`) | RAM (`mem_limit`) | 비고 |
|---|---|---|---|---|
| app (Phase 0, 단일) | t3.small | 1.0 | 512m | P1-09 전, 한계 관찰용 |
| app ×N (Phase 1+) | t3.small ×N | 각 1.0 | 각 512m | N=3 기본. Fargate task와 매핑 |
| worker (Phase 2) | t3.small | 1.0 | 512m | Streams consumer |
| PostgreSQL primary | db.t3.medium | 2.0 | 4g | `shared_buffers`≈1g로 함께 튜닝 |
| PostgreSQL replica | db.t3.medium | 2.0 | 4g | Phase 2 |
| Redis | cache.t3.micro | 0.5 | 512m | `maxmemory` = mem_limit 90%, eviction 정책 명시 |
| nginx | — | 0.5 | 128m | LB |
| mockpg | — | 0.5 | 256m | 외부 의존성 mock |

### compose 표기 (예시)
```yaml
services:
  app:
    deploy:
      resources:
        limits:   { cpus: "1.0", memory: 512m }
        reservations: { cpus: "0.5", memory: 256m }
```
- **`limits`뿐 아니라 `reservations`도 설정** — 스케줄링 경합에서 최소 보장을 확보해 측정 노이즈를 줄인다.
- compose v2 standalone에서 `deploy.resources`가 무시되면 `cpus:`/`mem_limit:` 최상위 키로 대체(§ 함정 노트).
- **호스트 예산 계산**: 실행 기기에 따라 부하 대상 (app×3 + db + redis + nginx + mockpg)과 k6 + Prometheus/Grafana + 커널의 비율을 정해 부하 대상의 상한을 정한다.

- **RAM은 실측 후 조인다**: PG `shared_buffers`, work_mem, 커넥션당 메모리를 고려. mem_limit에 닿으면 OOM kill되므로, 처음엔 넉넉히 두고 안정 후 하향.
- Redis는 `maxmemory`와 eviction 정책(`allkeys-lru` 등)을 명시 — 미설정 시 mem_limit 도달로 컨테이너가 통째로 죽어 P2-13과 혼동된다.

### AWS 매핑 (Phase 3)
compose 리소스 = Fargate task의 `cpu`/`memory`, RDS 인스턴스 클래스로 그대로 이관. Phase 3에서 동일 프로파일의 인스턴스 타입을 골라 로컬 실험 수치와 나란히 비교한다.

---

## 14. 첫 세션 절차 (Phase 0)

1. 저장소 스캐폴딩(§3 구조) + `deploy/compose.yaml`(app·db·redis·nginx·mockpg) + `compose.obs.yaml`(관측 스택) + Makefile. **compose에 §13 리소스 프로파일(vCPU·RAM 제한)을 처음부터 걸고, `docker stats`로 실제 적용 확인.**
2. Alembic 초기 마이그레이션 — §1 스키마 그대로. **PK 외 인덱스·수정용 컬럼 금지**
3. seed 스크립트(COPY 기반) + `make seed`
4. Phase 0 기능 구현 — §6의 "심는 문제"를 **정확히 포함**해서. 각 지점에 `INTENDED-ISSUE` 주석. 구현 후 이슈별로 verify-break 자기 점검 결과를 사용자에게 제시하고 승인받는다(§7-2).
5. `load/k6/mixed.js` + smoke 통과 확인 → `git tag phase-0`

Phase 0의 코드 리뷰 기준은 "잘 짰는가"가 아니라 **"백로그의 문제를 정확히 포함하는가"**다.

---

## 15. 세션별 모델 가이드
`/model` 전환은 사람이 직접 하는 조작이다. 따라서 이 가이드의 역할은 두 가지다: (1) 사용자가 세션 시작 전 어떤 모델·effort로 열지 정하는 기준, (2) 실행 중인 모델이 §0-8에 따라 "지금 이 작업은 상향/하향이 낫다"고 **사용자에게 제안**하는 기준. 제안은 하되 결정과 전환은 사용자 몫이다.

### 기본 전략
- **기본값: Sonnet 5.** 대부분의 이슈 사이클(break·measure·정형 fix·verify·로그 작성)은 Sonnet 5로 충분하다.
- **상향: Opus 4.8 (effort `xhigh`).** 반직관적 제약 준수나 다층 리팩터가 필요한 작업.
- **하향: Haiku 4.5.** 판단보다 정형·반복 작업.

### 작업 → 모델 매핑
| 작업 | 권장 모델 | effort | 이유 |
|---|---|---|---|
| Phase 0 스캐폴딩 (문제 심기) | **Opus 4.8** | xhigh | "개선하지 말고 문제를 정확히 심어라"는 모델의 본능과 충돌 — 최고 난도. 실험 전체의 유일한 치명적 실패 지점 |
| verify-break (심은 문제 검증) | 현재 모델 유지 | — | 심은 직후 같은 세션에서 자기 점검. 단 Phase 0을 Opus로 했으면 그대로 |
| 얽히는 fix: P1-07, P2-02, P2-06, P2-10, P2-11 | **Opus 4.8** | xhigh | 트랜잭션 경계·큐·replica 정합성 등 다층 추론 |
| 일반 이슈 break·measure·fix·verify | **Sonnet 5** | 기본 | 수정 방향이 명시된 최소 수정. near-top 추론을 낮은 비용·빠른 속도로 |
| k6 스크립트·EXPLAIN 해석·실험 로그 | **Sonnet 5** | 기본 | 정형 분석/작성 |
| seed·Makefile·docker/nginx 설정·로그 요약 | **Haiku 4.5** | — | 실수 비용 낮고 범위 좁음 |

### 운용 흐름 (사용자 기준)
1. 세션 시작 → 이슈 ID 확인 (한 번에 하나, §0-5).
2. 위 표에서 해당 작업의 권장 모델 확인.
3. 현재 모델과 다르면 `/model`로 전환 (`/model opus` 등, 재시작 불필요·즉시 적용). Opus 코딩 작업은 effort `xhigh`.
4. 실행 중인 모델이 불일치를 감지하면 먼저 제안한다(§0-8). 사용자가 유지 선택 시 현재 모델로 진행.

> 하나로 고정해야 한다면 이 프로젝트는 "문제를 정확히 심는" 규율 리스크 때문에 **Opus 4.8 단독**이 가장 안전하다. 비용이 부담되면 Sonnet 5 단독도 대부분 감당하나, Phase 0 문제 심기만은 상향을 권한다.
