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
4. **이슈 사이클 고정: break → measure → fix → verify → log.** 단계 생략 금지. (§7)
5. **Phase와 이슈는 사용자가 지시할 때만 진행한다.** 세션 시작 시 현재 이슈 ID를 확인하고,
   한 번에 하나의 이슈만 다룬다.
6. **실험 로그 없으면 미완료.** `docs/experiments/<ID>.md`가 갱신되어야 이슈 완료로 간주한다.
7. **결과를 조작하지 않는다.** 문제가 재현되지 않으면 그대로 기록하고,
   재현 조건(데이터량·동시성·리소스 제한)을 조정한 과정도 로그에 남긴다.

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

각 fix에는 트레이드오프가 있다 (예: 202 접수 패턴은 클라이언트 복잡도↑, replica는 지연 정합성 문제 발생).
실험 로그의 "트레이드오프" 항목에 반드시 기록한다.

---

## 7. 워크플로우 — 이슈 1개 처리 사이클

사용자가 "P1-03 하자"라고 하면:

1. **break** — Phase 0에 이미 심어져 있으면 코드 위치만 확인. 없으면 이 커밋에서 심는다.
2. **measure** — `load/k6/<id>.js` 작성·실행. k6 summary + Grafana + pg_stat_statements + `EXPLAIN (ANALYZE, BUFFERS)` 수집.
   핵심 수치를 measure 커밋 메시지에 요약. 재현 실패 시 조건 조정 과정도 기록.
3. **fix** — 백로그의 "수정 방향"으로 **최소 수정**. `INTENDED-ISSUE` 주석 제거. 전→후 수치를 커밋 메시지에.
4. **verify** — 동일 시나리오 재실행 + invariant 체크(`load/checks/`) + mixed 스모크로 회귀 확인.
5. **log** — `docs/experiments/<id>.md` 작성.

### 커밋 컨벤션
```
<type>(<ISSUE-ID>): <요약>        # type ∈ break | measure | fix | verify | feat | chore | docs
```
- Phase 0 기능 구현: `feat(P0)[P1-02,P1-08]: 주문 API (N+1·루프 INSERT 포함)` — 심은 이슈 ID 병기
- 이력 조회: `git log --oneline --grep P1-02` → 문제→재현→해결이 한 줄기로 보여야 한다
- Phase 경계 태그: `phase-0`, `phase-1-fixed`, `phase-2-fixed`

### 실험 로그 템플릿 (`docs/experiments/_template.md`)
```markdown
# <ID> <제목>
## 증상 / 가설
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
- 프로파일 3종: `smoke`(10vu·1m) / `target`(관문 수치·5m) / `limit`(한계까지 ramp)
- 표준 지표: TPS, p50/p95/p99, error rate, DB active connections, lock waits, CPU
- **리소스 제한 필수**: compose에서 app `cpus:1.0, mem:512m`, db `cpus:2.0` 수준으로 고정.
  제한 없으면 로컬 사양에 묻혀 문제가 안 터진다. k6 자체 CPU 소모도 감안할 것.
- 스파이크 실험 전 `make reset-deal`로 상태 초기화. invariant는 부하 후 `make check`로 검증.
- 기능 정확성 pytest는 최소한으로. 이 프로젝트의 "테스트"는 부하 시나리오 + invariant SQL이다.

## 9. 관측 (Observability)
- app: prometheus-fastapi-instrumentator / DB: postgres_exporter / Redis: redis_exporter
- Grafana 프로비저닝 대시보드: 요청량·p95·에러, DB 커넥션·락·slow query, Redis
- PostgreSQL: `pg_stat_statements` 활성(shared_preload_libraries), `log_min_duration_statement=200ms`
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

## 13. 첫 세션 절차 (Phase 0)

1. 저장소 스캐폴딩(§3 구조) + `deploy/compose.yaml`(app·db·redis·nginx·mockpg) + `compose.obs.yaml`(관측 스택) + Makefile
2. Alembic 초기 마이그레이션 — §1 스키마 그대로. **PK 외 인덱스·수정용 컬럼 금지**
3. seed 스크립트(COPY 기반) + `make seed`
4. Phase 0 기능 구현 — §6의 "심는 문제"를 **정확히 포함**해서. 각 지점에 `INTENDED-ISSUE` 주석
5. `load/k6/mixed.js` + smoke 통과 확인 → `git tag phase-0`

Phase 0의 코드 리뷰 기준은 "잘 짰는가"가 아니라 **"백로그의 문제를 정확히 포함하는가"**다.
