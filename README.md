# CLAUDE.md — FlashMart: 부하·확장성 실험실 & 실전 프로덕션 엔지니어링 트랙

선착순 특가 커머스를 소재로 한 **부하 실험 및 실전 아키텍처·코딩 훈련 프로젝트**다.
이 프로젝트는 두 가지 핵심 목적을 동시에 달성한다:

1. **부하·확장성 실험실 (Fail & Fix Lab)**: 의도적으로 심어진 병목을 부하로 터뜨리고 → 측정하고 → 해결한 뒤, 전 과정을 **git 히스토리와 실험 로그로 추적 가능하게 남기는 것**.
2. **실전 아키텍처 설계 & 프로덕션 코딩·평가 트랙 (Hands-on Production Engineering)**: AI에게 코딩을 위임하느라 무뎌진 엔지니어링 감각을 되찾기 위해, **사용자가 직접 아키텍처를 설계(`docs/designs/`)하고 요구사항에 따라 프로덕션 레벨 코드(`app/`, `migrations/`)를 작성하며, AI로부터 적대적 테스트와 현업 PR 수준의 코드 리뷰(`reports/<ID>-review.md`)를 받는 것**.

로컬 docker compose에서 시작해 Phase 3에서 AWS로 이전한다.

---

## 0. 최상위 규칙 — 프로젝트의 정체성을 위해 유념할 것

1. **아직 다루지 않은 미래 이슈의 의도된 문제를 미리 고치지 말 것.**
   이슈 백로그(§6)에 "심는 문제"로 명시된 코드는 해당 이슈 차례가 오기 전까지 건드리지 않는다.
   단, **현재 진행 중인 이슈를 해결할 때는 "최소 수정"에 얽매이지 않고 레이어 구조, 도메인 모델, 예외 처리, 타입 안정성을 실제 프로덕션 수준으로 자유롭게 리팩토링**한다.
2. **문제를 심은 지점에는 주석 표식을 남긴다.** `# INTENDED-ISSUE: P1-02` 형식.
   해당 이슈 해결(implement) 단계에서 주석을 제거한다. (`grep -rn "INTENDED-ISSUE"`로 남은 문제를 조회)
3. **역할 분담 및 코딩 경계 (User-First Coding & AI Reviewer)**:
   - **사용자**: 병목 원인 진단, 아키텍처 설계(`docs/designs/<ID>.md`), 프로덕션 애플리케이션 코드(`app/`, `migrations/`) 직접 구현 및 코드 리뷰 피드백 반영.
   - **AI 에이전트**: 개념 브리핑(난이도별), 부하 재현 및 관측(`load/k6/`), 설계 압박 리뷰(Design Critique), 적대적 엣지 케이스/동시성 테스트(`tests/adversarial/`) 작성·실행, 5대 프로덕션 루브릭 기반 PR 코드 리뷰(`reports/<ID>-review.md`).
   - **스포일러 금지 및 유연한 코칭**: AI는 `docs/reference/solution-guide.md`의 정답을 바로 누설하지 않고 선택된 난이도(`Lv.1~4`, §7)에 맞춰 브리핑과 힌트를 조절한다. 기본 원칙은 사용자가 직접 코드를 짜는 것이나, **사용자가 막혀서 힌트 3단계/예시 스니펫/페어 수정을 요청하거나 리뷰 반영을 위임할 때는 AI도 코드 수정을 도울 수 있다.**
4. **모든 fix/feat 커밋에는 전/후 수치(또는 핵심 설계 요약)를 남긴다.**
   예: `fix(P1-02): selectinload 적용 (쿼리 201→3회, p95 1.9s→160ms @100vu)`
5. **과제 수행 사이클 고정: `brief & measure → design (RFC) → implement → evaluate (Adversarial Test & PR Review) → log & report`.** 단계 생략 금지. 특히 **설계 승인(Design Approved)**과 **코드 리뷰 승인(Code Review Approved)**을 거쳐야 완료된다. (§7)
6. **Phase와 이슈/기능 과제는 사용자가 지시할 때만 진행한다.** 세션 시작 시 현재 이슈 ID와 **희망 난이도(`Lv.1 ~ Lv.4`)**를 확인하고, 한 번에 하나의 과제만 다룬다.
7. **산출물 누락 시 미완료.** 설계서(`docs/designs/<ID>.md`), 코드 리뷰 성적표(`reports/<ID>-review.md`), 실험 로그(`docs/experiments/<ID>.md`), 요약 리포트(`reports/<ID>.md`)가 갱신되어야 완료로 간주한다.
8. **결과를 조작하지 않는다.** 문제가 재현되지 않으면 그대로 기록하고, 재현 조건(데이터량·동시성·리소스 제한)을 조정한 과정도 로그에 남긴다.
9. **세션 시작 시 이슈에 맞는 모델을 사용자에게 제안한다.** (§15)

---

## 1. 서비스 정의

**FlashMart** — 선착순 특가 딜과 프로모션이 있는 미니 커머스. 프론트엔드 없음, REST API 전용 (클라이언트는 k6 및 pytest).
도메인은 부하 실험과 아키텍처 설계를 위한 무대다. 앞으로 추가될 도메인 기능(`F1-*`, `F2-*`)까지 고려해 확장 가능한 아키텍처를 설계해야 한다 (§6 매핑 참고).

### 기능 / API (기본 스캐폴딩 + 향후 구현할 Feature 로드맵)
| 기능 | 엔드포인트 | 연관 이슈 및 아키텍처 과제 |
|---|---|---|
| 회원가입/로그인/내정보 | `POST /auth/signup` `POST /auth/login` `GET /auth/me` | 세션 상태 → stateless (P1-01), CPU 해싱 오프로드 (P1-10) |
| 상품 목록·검색 | `GET /products?category=&q=&page=` (→ 커서 확장) | 인덱스(P1-03), 페이지네이션(P1-04), COUNT 병목(P1-05) |
| 상품 상세 | `GET /products/{id}` | 읽기 트래픽 소재, 복제본 라우팅 (P2-06) |
| 메인 인기 상품 | `GET /main/popular` | 집계 쿼리 + 캐시 스탬피드 방어 (P2-05) |
| 장바구니 | `POST /cart/items` `GET /cart` | 응답 상한(P1-11), 다중 상품 데드락 방어 (P2-03) |
| 주문 생성/내역 | `POST /orders` `GET /orders` `GET /orders/{id}` | N+1(P1-02), 외부호출·트랜잭션 분리(P1-06~08), 멱등성(P2-04) |
| **[신규]** 주문 취소·환불 | `POST /orders/{id}/cancel` | 상태머신 전이, 재고 복원, 외부 PG 환불 연동 정합성 (**F1-01**) |
| **[신규]** 프로모션 쿠폰 | `POST /coupons/{id}/claim` + `POST /orders` 할인 연동 | 선착순 1인 1매 발급 제약, 주문/취소 시 쿠폰 생명주기 (**F1-02**) |
| 선착순 딜 구매 | `POST /deals/{id}/purchase` | 핫 로우 원자성(P2-01), 비동기 큐 접수(P2-02), Bloat(P2-12) |
| **[신규]** 딜 접수 상태/만료 | `GET /deals/{id}/requests/{req_id}` + 만료 회수 | 비동기 접수(202) 상태 폴링 및 미확정 재고 보상 (**F2-01**) |
| 실시간 판매 랭킹 | `GET /rankings/realtime` | OLTP 위 집계 간섭 격리 (P2-09), Redis 장애 폴백 (P2-13) |
| **[신규]** 결제 웹훅·대사 | `POST /webhooks/pg` | PG 타임아웃 미결 주문의 비동기 최종 일관성 달성 (**F2-02**) |
| 결제 mock (별도 앱) | `POST /pay` (`POST /refund` 확장) — `LATENCY_MS`, `FAIL_RATE` 제어 | 외부 의존성 지연·장애 주입 및 서킷브레이커 (P1-06,07, P2-07) |

### 데이터 모델 (초기 스키마)
- `users(id, email, pw_hash, created_at)`
- `categories(id, name)` / `products(id, category_id, name, description, price, stock, created_at)`
- `reviews(id, product_id, user_id, rating, body)` — 목록에 평점·리뷰수 노출용 (N+1·집계 소재)
- `deals(id, product_id, deal_price, total_qty, remaining_qty, opens_at, closes_at)` — 핫 로우
- `cart_items(user_id, product_id, qty)`
- `orders(id, user_id, status[PENDING|PAID|FAILED], total_amount, created_at)` / `order_items(id, order_id, product_id, qty, unit_price)`
- `payments(id, order_id, status, pg_tx_id, created_at)`

주의: **Phase 0 스키마에는 PK 외 인덱스를 만들지 않는다** (P1-03의 소재).
`idempotency_key`나 쿠폰/환불 관련 테이블·컬럼도 미리 넣지 않고, 각 이슈/기능 과제의 아키텍처 설계 후 직접 Alembic 마이그레이션으로 추가한다.

### seed 규모 (문제가 보이려면 데이터가 커야 한다)
users 5만 / products 20만(카테고리 50) / reviews 100만 / orders 300만 / order_items 800만.
seed는 실험 대상이 아니므로 **COPY 기반**으로 빠르게 (루프 INSERT 금지). `make seed`, 목표 수 분 내.

---

## 2. 기술 스택
- Python 3.12+, FastAPI, uvicorn
- SQLAlchemy 2.0 (async) + asyncpg, Alembic
- PostgreSQL 16, Redis 7 (세션/캐시/큐 — Phase에 따라 도입)
- nginx — L7 LB (로컬에서 ALB 역할)
- k6 (부하), pytest + pytest-asyncio (기능 및 적대적 엣지 케이스 검증)
- Prometheus + Grafana + postgres_exporter + redis_exporter (관측)
- docker compose로 전 구성 실행. mockpg는 초경량 FastAPI 별도 앱.
- toxiproxy — app↔DB/Redis 사이 네트워크 지연·단절 주입 (P2-13/14 및 Phase 3 AZ 장애 리허설을 로컬에서 미리 재현)

## 3. 저장소 구조
```
flashmart/
├── app/
│   ├── main.py
│   ├── core/            # config, db, redis, deps, metrics
│   ├── auth/ products/ deals/ cart/ orders/ payments/   # 모듈별 router/service/repository
│   └── workers/         # Phase 2: 딜 주문 확정 consumer 및 백그라운드 워커
├── mockpg/              # 외부 결제 mock
├── migrations/          # alembic
├── seed/
├── tests/
│   └── adversarial/     # AI가 사용자 코드를 검증하는 적대적/동시성/엣지 케이스 테스트
├── load/
│   ├── k6/              # mixed.js, p1-03.js, p2-01.js ...
│   └── checks/          # oversell.sql, dup_orders.sql (invariant 검증)
├── deploy/
│   ├── compose.yaml  compose.obs.yaml
│   └── nginx/  prometheus/  grafana/
├── docs/
│   ├── designs/         # _template.md, P1-04.md ... (사용자의 아키텍처 설계 RFC)
│   ├── experiments/     # _template.md, P1-01.md ... (부하 측정 전/후 실험 로그)
│   └── reference/       # solution-guide.md (정답 스포일러 분리 보관소 — 열람 주의)
├── reports/             # _review_template.md, <ID>-review.md (성적표), <ID>.md (최종 요약)
├── Makefile
└── README.md
```

## 4. 명령어 (Makefile로 제공할 것)
```
make up            # 기본 기동 (app 1대)
make up N=3        # app N대 + nginx LB
make down / logs
make migrate / make revision m="..."
make seed / make reset-deal        # 딜 수량·주문 초기화 (스파이크 실험 전 필수)
make lint          # ruff check + ruff format --check + mypy (코딩 후 자가 점검)
make test          # pytest 실행 (T=tests/adversarial/test_p1_04.py 지정 가능)
make load S=p1-03  # load/k6/p1-03.js 실행
make check S=oversell              # load/checks/oversell.sql 실행
make psql / make redis-cli
make kill-one      # 부하 중 앱 인스턴스 1대 강제 종료 (P2-08)
make pause-redis / make unpause-redis   # Redis 장애 주입/복구 (P2-13)
make stats         # docker stats — 리소스 제한 실제 적용 확인 (§13)
make grafana       # localhost:33000
```

### 호스트 노출 포트 (충돌 방지를 위해 30000번대 사용)
컨테이너 내부 통신 포트(8000, 80, 5432, 6379 등)는 기본값을 유지하되, 호스트(`localhost`)로 바인딩되는 포트는 로컬 프로세스와의 충돌을 피하기 위해 모두 **30000번 이후**로 매핑한다.

| 서비스 | 호스트 포트 (`localhost`) | 컨테이너 내부 포트 | 비고 |
|---|---|---|---|
| **app** (단일, `N=1`) | `38000` | `8000` | `compose.direct.yaml` (`make up`) |
| **nginx** (LB, `N>1`) | `38080` | `80` | `make up N=3` |
| **mockpg** | `38100` | `8000` | 외부 결제 mock |
| **PostgreSQL** | `35432` | `5432` | 호스트 DB 클라이언트 접속용 |
| **Redis** | `36379` | `6379` | 호스트 Redis 클라이언트 접속용 |
| **Grafana** | `33000` | `3000` | `make grafana` (`admin` / `admin`) |
| **Prometheus** | `39090` | `9090` | 메트릭 수집기 UI |

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

## 6. 이슈 & 기능 백로그 — 심는 문제, 현업 요구사항, 그리고 완료 기준

> **스포일러 방지 안내**
> 직접 아키텍처를 고민하고 설계하는 훈련을 위해, 미해결 이슈(`P1-04 ~ P2-15`)의 구체적인 **수정 방향(정답 스포일러)**은 `docs/reference/solution-guide.md`로 분리되었다.
> 아래 표는 현업에서 주어지는 **문제 상황·비기능/비즈니스 요구사항·완료 기준(SLO)**만 정의한다. 아키텍처 설계 시 **§6.3의 향후 도메인 기능(Feature Missions)**까지 함께 고려해야 한다.

### 6.1 Phase 1: 수백 TPS에서 터지는 것들
| ID | 기능 | 심는 문제 (Phase 0) | 재현 방법 | 현업 요구사항 & 아키텍처 제약 조건 | 완료 기준 (SLO) |
|---|---|---|---|---|---|
| P1-01 | 로그인 세션 | 프로세스 내 dict에 세션 저장 | app 2대(또는 워커 2)에서 로그인 후 `/auth/me` 반복 → 랜덤 401 | **[완료]** 다중 인스턴스 수평 확장 및 롤링 배포 시 인증 상태 일관성 유지 | app 3대 + 롤링 재시작에도 세션 유지 |
| P1-02 | 주문 내역 | 주문→아이템→상품을 루프 내 개별 조회 (N+1) | 주문 30건 유저로 `GET /orders` 부하, 쿼리 로그·pg_stat 확인 | **[완료]** 유저의 주문 건수가 늘어나도 DB 왕복(Round-trip) 횟수가 일정해야 함 | 요청당 쿼리 수 상수(≤3), p95 전/후 기록 |
| P1-03 | 상품 검색 | `ILIKE '%q%'` + status/기간 필터에 인덱스 없음 | 20만 상품에서 검색 50vu → seq scan, p95 수 초 | **[완료]** 부분 문자열(`%q%`) 및 카테고리 복합 검색 시 Full Table Scan 제거 | EXPLAIN에서 Index Scan, 검색 쿼리 지연 해소 |
| P1-04 | 상품 목록 | OFFSET 페이지네이션 | 깊은 페이지(page 5000급) 시나리오 | 탐색 깊이가 깊어져도 일정한 응답 속도를 보장하는 페이지네이션 API 설계 (하위 호환성 또는 클라이언트 계약 정의 포함) | 깊은 탐색에서도 DB 스캔 행 수 및 p95 평탄 |
| P1-05 | 목록 total | 매 요청 `COUNT(*)` | 목록 부하 중 pg_stat_statements 상위 쿼리 확인 | 상품 목록/검색 API 호출 시 무거운 전체 건수 집계로 인한 DB 병목 제거 (UX 요구사항에 맞는 대안 설계) | 목록 경로에서 매 요청 `COUNT(*)` 소멸, p95<200ms |
| P1-06 | 결제 호출 | 동기 `requests`로 mockpg 호출 (이벤트 루프 블로킹) | mockpg LATENCY=800ms, 주문 50vu → **무관한 GET까지** 지연 | 외부 PG 연동 지연이 발생하더라도 서버의 다른 API(상품 조회 등) 처리량과 응답시간에 전파되지 않아야 함 (커넥션 생명주기 관리 포함) | 주문 부하 중 `GET /products` p95 영향 없음 |
| P1-07 | 주문 트랜잭션 | DB 트랜잭션 내부에서 결제 API 호출 | pool_size=10, 주문 200vu → pool timeout 다발 | 외부 네트워크 I/O 동안 DB 커넥션 및 로우 락을 점유하지 않도록 트랜잭션 경계 재설계. 향후 **주문 취소/환불(F1-01)** 및 **결제 웹훅(F2-02)** 확장을 고려한 주문 상태머신 도입 | pool wait 0, 주문 처리량 회복, 부분 실패 시 재고·주문 정합성 보장 |
| P1-08 | 주문 저장 | order_items를 루프 INSERT(건별 commit) | 아이템 10개 주문 부하 | 다품목 주문 저장 시 원자성(Atomicity) 보장 및 DB 네트워크 왕복 최소화 | 주문당 아이템 INSERT 왕복 1회, 부분 커밋 불가 |
| P1-09 | 인프라 | uvicorn 워커 1, 풀 기본값, 단일 인스턴스 | mixed 300 TPS 시도 → 한계 확인 | 컨테이너 리소스 제약(§13)과 PG `max_connections` 한도 내에서 인스턴스 수·워커 수·DB 커넥션 풀의 수학적 정합성 계산 및 튜닝 | **P1 관문** (mixed 300 TPS: p95<300ms, err<1%) 통과 |
| P1-10 | 로그인 해싱 | bcrypt(cost 12+)를 async 핸들러에서 직접 실행 (CPU 블로킹) | 로그인 100vu 스파이크 → **무관한 GET까지** 지연 (P1-06과 달리 CPU-bound) | CPU 집약적 암호화 연산이 비동기 이벤트 루프를 멈추지 않도록 격리 | 로그인 스파이크 중 `GET /products` p95 영향 없음 |
| P1-11 | 목록 응답 크기 | `GET /cart`·`GET /orders`에 LIMIT 없이 전체 반환 | 주문 수천 건 헤비 유저 섞어 부하 → 직렬화·메모리 폭증 | 헤비 유저 요청에서도 OOM 및 직렬화 지연을 막기 위한 API 응답 크기 상한 및 페이지네이션 강제 (경계값 검증 포함) | 응답 크기·메모리·p95 상한 확보, P1-02와 독립 검증 |
| P1-12 | 세션 누수 | 예외 경로에서 DB 세션/커넥션 미반환 | mixed에 5% 에러 유발 요청 섞어 장시간 → 풀이 **서서히** 고갈 | 비즈니스 예외나 런타임 오류 발생 시에도 DB 트랜잭션 롤백과 커넥션 반환이 100% 보장되는 생명주기 관리 | 장시간 에러 혼입 부하에도 active connection 평탄, 누수 0 |

### 6.2 Phase 2: 수천 TPS + 스파이크에서 터지는 것들
| ID | 기능 | 심는 문제 / 상황 | 재현 방법 | 현업 요구사항 & 아키텍처 제약 조건 | 완료 기준 (SLO) |
|---|---|---|---|---|---|
| P2-01 | 선착순 구매 (1차) | `SELECT` 재고 확인 후 `UPDATE` (check-then-act) | 딜 수량 1,000에 3,000vu 10초 스파이크 | 동시 구매 스파이크 상황에서 단일 RDB만 사용하여 초과 판매(Oversell)와 음수 재고를 완벽히 차단 | `check S=oversell` 결과 0 |
| P2-02 | 선착순 구매 (2차) | 원자 UPDATE도 단일 로우 락 직렬화 → TPS 한계, p99 폭발 | 동일 스파이크에서 lock wait·p99 관찰 | 5,000 req/s 스파이크를 DB 락 대기 없이 흡수하고 빠른 응답을 반환하는 비동기 선점·확정 아키텍처 설계 (**F2-01 상태 조회**와 연계) | 스파이크 흡수, oversell 0 유지, 접수 API p95<100ms |
| P2-03 | 장바구니 주문 | 재고 차감 락을 담은 순서(임의)로 획득 | 교차 장바구니 동시 주문 → deadlock 로그 | 여러 상품을 동시에 담고 주문하는 다중 트랜잭션 환경에서 교착 상태(Deadlock)가 구조적으로 발생할 수 없도록 설계 | 동시 교차 주문 시 deadlock 0 |
| P2-04 | 주문 생성 | 재시도·더블클릭 시 중복 주문 | k6에서 동일 요청 2연발 | 네트워크 타임아웃 재시도나 클라이언트 따닥(동시 중복 호출) 시에도 단 1건의 주문과 결제만 생성되도록 보장 (동일 키로 다른 페이로드 요청 시 방어 포함) | `check S=dup_orders` 0, 재시도 시 일관된 응답 반환 |
| P2-05 | 인기 상품 | 무거운 집계 + 고정 TTL 캐시 | TTL 만료 시점에 부하 정렬 → 동시 miss로 DB 폭주 | 캐시 만료 순간 수백 개의 동시 요청이 몰려도 DB 집계 쿼리는 단 1회만 실행되도록 방어 (Cache Stampede 차단) | 캐시 만료 순간 DB 원본 쿼리 1회, p99 튀지 않음 |
| P2-06 | 읽기 확장 | 모든 읽기가 primary | 읽기 부하 증대 → primary 포화. replica 도입 후 "방금 주문이 안 보임" 재현 | 읽기 트래픽을 Read Replica로 분산하되, 사용자가 방금 생성/수정한 데이터는 복제 지연(Replication Lag)에도 불구하고 즉시 조회 가능해야 함 | 읽기 부하 분산 + Read-Your-Writes 정합성 시나리오 통과 |
| P2-07 | 결제 장애 | 실패 시 즉시 무한 재시도 | mockpg FAIL_RATE=0.5 → 재시도 폭풍으로 자체 과부하 | 외부 PG 장애/지연 시 무분별한 재시도로 인한 자체 장애 증폭을 막고, 장애 시 빠른 실패(Fast-fail) 및 복구 시 자동 정상화 달성 (**F2-02 웹훅** 연계) | 장애 중 시스템 자원 보호 및 fast-fail, 복구 후 자동 정상화 |
| P2-08 | 배포·장애 | 종료 시그널 무시, 헬스체크 없음 | 부하 중 `make kill-one` / 롤링 재시작 → 5xx | 배포 또는 스케일 인/아웃 시 진행 중인 요청(In-flight)을 안전하게 마무리하고 무중단 트래픽 전환 보장 | 인스턴스 종료/재시작 중 err<0.5%, 롤링 무중단 |
| P2-09 | 실시간 랭킹 | 요청마다 orders GROUP BY | 주문 부하와 동시 조회 → OLTP 간섭 | 실시간 판매 랭킹 조회가 핵심 주문 트랜잭션(OLTP) 성능을 갉아먹지 않도록 읽기/집계 모델 분리 | 랭킹 고부하 조회 중에도 주문 API p95 영향 없음 |
| P2-10 | worker 확정 | at-least-once 전달인데 consumer가 비멱등 (ack 전 죽으면 재처리) | P2-02 큐 도입 후 처리 도중 `make kill-one` → 같은 메시지 재전달로 중복 확정 | 워커가 DB 반영 직후 ACK 전에 죽어 메시지가 재전달되더라도 중복 주문/결제가 발생하지 않는 멱등 컨슈머 구현 | 강제 재전달 시나리오에서도 중복 확정 0 |
| P2-11 | 큐 운영 | worker 처리량 < 유입량 + poison message 무방비 | 유입 > 처리 스파이크로 Streams 무한 성장, 파싱불가 메시지 1개로 crash loop | 비정상(Poison) 메시지 유입 시 워커 전체가 멈추지 않고 격리(DLQ)되어야 하며, 미처리 메시지(PEL) 복구 및 백프레셔/스케일링 체계 구축 | 스파이크 후 lag 수렴, poison 메시지 격리 및 서비스 지속 |
| P2-12 | 핫로우 bloat | 스파이크 반복 후 딜 테이블 dead tuple 누적 (autovacuum 못 따라감) | P2-01/02 스파이크 여러 회 반복 → 딜 경로 점진적 성능 저하, `pg_stat_user_tables` 확인 | 초고빈도 UPDATE가 발생하는 핫 테이블에서 MVCC Dead Tuple 누적으로 인한 점진적 성능 열화 방지 | 반복 스파이크 후에도 딜 p95 안정, dead tuple 비율 임계 이하 |
| P2-13 | Redis 장애 | 세션·캐시·큐·선점을 전부 Redis에 의존, 폴백 없음 | `docker pause redis` → 전면 장애 | Redis가 멈추거나 응답하지 않을 때 전체 커머스 서비스가 전면 마비되지 않도록 기능별 우아한 성능 저하(Graceful Degradation) 설계 | Redis pause 중에도 핵심 읽기 경로 생존, 복구 후 자동 정상화 |
| P2-14 | 타임아웃 계층 | k6 < nginx < 앱 처리시간 불일치, DB `statement_timeout` 미설정 | 느린 요청에서 클라 타임아웃 후 재시도 → 서버는 좀비 작업 지속 → 부하 자기증폭 | 클라이언트가 이미 포기한 요청이 앱과 DB에서 좀비 작업으로 남아 자원을 고갈시키지 않도록 전 계층 타임아웃 예산(Budget) 설계 | 타임아웃 발생 시 좀비 쿼리 0, 재시도 유입 시 부하 자기증폭 차단 |
| P2-15 | 무중단 마이그레이션 | P1-03 인덱스 생성을 `CONCURRENTLY` 없이 부하 중 실행 | 부하 중 인덱스 생성 → 쓰기 블로킹으로 5xx (fix 자체가 장애를 냄) | 라이브 트래픽이 흐르는 프로덕션 환경에서 테이블 쓰기 락(DDL Lock) 없이 안전하게 스키마/인덱스를 변경하는 마이그레이션 구현 | 부하 중 마이그레이션 실행 시 err<1%, 쓰기 무중단 |

### 6.3 현업 도메인 기능 백로그 (Feature Missions — 아키텍처 & 프로덕션 코딩 훈련)

단순 병목 튜닝만으로는 도메인 모델링과 모듈 설계 감각을 기르기 어렵다. 아래 4가지 현업 요구사항 과제는 기존 이슈들의 아키텍처가 얼마나 확장성 있게 설계되었는지 검증하고, 백지부터 프로덕션 코드를 작성하는 훈련을 제공한다. **P1/P2 이슈를 설계할 때 아래 기능들이 곧 들어온다는 점을 반드시 전제해야 한다.**

| ID | 권장 시점 | 기능명 (엔드포인트) | 현업 비즈니스 요구사항 & 불변식 (PRD / Invariants) | 완료 기준 (SLO & Verification) |
|---|---|---|---|---|
| **F1-01** | P1-07/08 완료 직후 | **주문 취소 및 환불 상태머신**<br/>(`POST /orders/{id}/cancel`) | - 유저는 자신의 `PENDING` 또는 `PAID` 주문을 취소할 수 있다 (`FAILED`, 이미 `CANCELED`/`REFUNDED`된 주문은 거부).<br/>- 취소 시 차감되었던 상품 재고(`stock`)가 정확히 원복되어야 한다.<br/>- `PAID` 주문 취소 시 외부 `mockpg`의 환불 API(`POST /refund`)를 호출해야 하며, DB 트랜잭션 점유 없이(P1-07 원칙) 부분 실패 및 동시 중복 취소 요청(레이스 컨디션)에 안전해야 한다. | 동시 취소 폭격 시 재고 초과 복구 0건, 중복 환불 호출 0건, `mockpg` 지연 시 커넥션 풀 고갈 없음 |
| **F1-02** | P1 완료 전후 | **선착순 프로모션 쿠폰 발급 & 주문 할인 적용**<br/>(`POST /coupons/{id}/claim`, `POST /orders` 확장) | - 한정 수량(`total_qty`) 쿠폰을 유저당 최대 1매씩만 선착순 발급한다.<br/>- 주문 생성(`POST /orders`) 시 보유한 미사용 쿠폰(`user_coupon_id`)을 적용하면 할인 금액만큼 결제 금액이 차감된다.<br/>- 하나의 쿠폰을 동시에 두 주문에 사용하는 따닥 공격을 방어해야 하며, 주문 결제 실패 또는 취소(F1-01) 시 쿠폰은 다시 사용 가능 상태로 복원되어야 한다. | 쿠폰 초과 발급 0건, 유저당 중복 발급 0건, 동시 주문 시 쿠폰 이중 사용 0건, 주문 취소 시 쿠폰 복원 100% |
| **F2-01** | P2-02 완료 직후 | **비동기 딜 구매 상태 폴링 & 미확정 재고 회수**<br/>(`GET /deals/{id}/requests/{req_id}`) | - P2-02에서 `202 Accepted`로 접수된 딜 구매 요청에 대해 클라이언트가 현재 상태(`QUEUED`, `CONFIRMED`, `SOLD_OUT`, `FAILED`)와 생성된 `order_id`를 조회할 수 있는 API를 제공한다.<br/>- 워커 처리 실패 또는 비정상 중단으로 일정 시간(TTL) 이상 확정되지 못한 선점 수량을 안전하게 회수(보상)하여 재고 증발(Under-sell)을 막는다. | 접수 직후~확정 전 전 구간 상태 일관성 보장, 실패 건 재고 누수(Under-sell) 0건, 조회 API p95<50ms |
| **F2-02** | P2-07 완료 직후 | **결제 웹훅(Webhook) 수신 및 미결제 주문 대사**<br/>(`POST /webhooks/pg`) | - P1-07/P2-07에서 `mockpg` 타임아웃이나 네트워크 단절로 인해 실제로는 결제가 성공했으나 앱이 응답을 받지 못해 `PENDING` 등에 머문 주문을 최종 일관성(Eventual Consistency)으로 해결한다.<br/>- PG사가 보내는 웹훅(`pg_tx_id`, `order_id`, `status`)을 수신해 주문 상태를 확정하거나, 이미 취소/실패 처리된 주문이면 자동 환불/보상 처리를 수행한다.<br/>- 동일한 웹훅이 여러 번 도착하거나 원래 API 응답보다 먼저 도착하는 경쟁 상태를 멱등하게 처리한다. | 중복/역전 웹훅 전송 시 상태 깨짐 0건, 타임아웃 발생 주문의 최종 정합성 100% 복구 |

각 설계와 수정에는 트레이드오프가 있다 (예: 202 접수 패턴은 클라이언트 폴링 복잡도↑, replica는 지연 정합성 문제 발생). 설계 문서(`docs/designs/<ID>.md`)와 실험 로그(`docs/experiments/<ID>.md`)에 반드시 기록한다.

---

## 7. 워크플로우 — 난이도 조절 및 과제 수행 사이클

### 7.1 4단계 난이도 다이얼 (Difficulty & Coaching Levels)

사용자의 현재 코딩 감각과 도메인 친숙도에 맞춰 매 과제 시작 시 난이도를 선택(또는 변경)할 수 있다. 사용자가 별도로 지정하지 않으면 초반 과제는 **`Lv.1(재활 모드)`** 또는 **`Lv.2(가이드 실전)`**를 기본 제안한다.

| 구분 | **Lv.1 재활 모드 (Warm-up)** | **Lv.2 가이드 실전 (Guided Pro)** | **Lv.3 독립 시니어 (Independent)** | **Lv.4 하드코어 (Staff)** |
|---|---|---|---|---|
| **목표** | 3개월 코딩 공백 회복 및 프레임워크/문법 감각 깨우기 | 핵심 아키텍처 개념 학습 + 스스로 코드 구조 짜기 | 힌트 없이 현업 시니어 수준으로 원인 분석·설계·구현 | 복합 장애 및 도메인 요구사항을 스태프 수준으로 완벽 해결 |
| **1. 개념 브리핑** | 문제 원리 상세 해설 + **해결 아키텍처 후보 2~3개(장단점) 비교 제시** | 핵심 개념 키워드와 **설계 시 고민해야 할 질문 체크리스트**만 제공 | 사전 브리핑 없음 (지표·로그·요구사항만 제공) | 사전 브리핑 없음 + 인접 이슈/확장 요구사항 동시 제약 |
| **2. 설계 (RFC)** | 후보 중 하나 선택 + 이유 3~5줄 작성으로 통과 | 직접 RFC 작성 → AI가 빠진 엣지 케이스 보완 질문 | 백지 RFC 작성 → AI의 압박 질문(Design Critique) 방어 필수 | 대안 비교·폴백·무중단 마이그레이션 계획까지 완벽해야 승인 |
| **3. 코딩 지원** | 수정할 파일·함수 위치 안내 + **SQLAlchemy/FastAPI 문법 치트시트(예시 스니펫)** 제공 | 문법 치트시트 없이 직접 구현 (공식 문서 수준 질의만 허용) | 전 과정 단독 구현 (레이어, 예외 처리, 타입, 마이그레이션) | 관측 메트릭, 장애 격리, 리소스 정리까지 완벽 구현 |
| **4. 리뷰 기준** | 동작 성공 및 핵심 병목 해결 시 `APPROVED` (나머지는 학습 팁 제공) | 5대 루브릭 평가 + 주요 결함 시 `CHANGES REQUESTED` | 적대적 테스트 통과 필수 + 현업 PR 수준의 엄격한 리뷰 | 5대 루브릭 전 항목 `A` 이상이어야 `APPROVED` |

* **3단계 힌트 에스컬레이션 (진행 중 막히면 언제든 요청 가능)**:
  * **`힌트 1단계 (Concept)`**: 관련 CS/DB/분산시스템 원리와 접근 방향 힌트 제공
  * **`힌트 2단계 (Structure)`**: 수정할 계층 구조, 쿼리 형태, 상태 전이도 또는 의사코드(Pseudocode) 제공
  * **`힌트 3단계 (Reference / Pair)`**: 막힌 구간의 레퍼런스 코드 스니펫 제시 또는 AI와 페어 수정 진행

---

### 7.2 과제 1개 처리 사이클 (`Brief & Measure → Design → Implement → Evaluate → Log`)

사용자가 `"P1-04 하자 (Lv.1)"` 또는 `"F1-01 하자 (Lv.2)"`라고 하면 다음 6단계를 순서대로 수행한다:

1. **Step 1: `brief & measure` (요구사항 확인·부하 측정·개념 브리핑)**
   - **[AI 필수 선행]**: AI는 먼저 `docs/reference/solution-guide.md`에서 해당 이슈(`<ID>`)의 표준 해법, 허용 대안, 필수 체크리스트(Pitfalls)를 읽고 내부 기준을 세운다 (단, 선택된 난이도에 허용된 범위 밖의 정답은 스포일러하지 않는다).
   - **병목 이슈(`P1/P2`)인 경우**: Phase 0에 심어진 문제 위치와 `INTENDED-ISSUE` 주석을 확인(필요시 verify-break 점검)한 뒤, AI가 `load/k6/<id>.js` 및 `EXPLAIN (ANALYZE, BUFFERS)` / `pg_stat_statements`로 **Before 지표**를 측정해 사용자에게 제시한다.
   - **신규 기능(`F1/F2`)인 경우**: AI가 비즈니스 요구사항(PRD), 입출력 API 계약 조건, 만족해야 할 불변식(Invariants)과 SLO를 제시한다.
   - 선택된 난이도(`Lv.1` 또는 `Lv.2`)에 따라 AI가 **개념 브리핑 / 아키텍처 후보군 / 문법 치트시트**를 함께 제공한다 (`Lv.3~4`는 생략).

2. **Step 2: `design (RFC)` (사용자 아키텍처 설계 & AI Design Review 게이트)**
   - **사용자**: `docs/designs/<ID>.md` (`docs/designs/_template.md` 기반)에 원인 진단, 선택한 아키텍처, 트랜잭션/데이터 흐름, 실패/동시성 방어 대책, 트레이드오프를 작성한다. (`Lv.1`은 채팅 또는 문서에 3~5줄 요약으로 대체 가능)
   - **AI (Design Reviewer)**: `docs/reference/solution-guide.md`의 `[표준 해법 / 허용 대안]` 및 `[코드 리뷰 필수 체크 (Pitfalls)]`를 기준으로 설계의 빈틈(예: *"커넥션 풀이 고갈되면?", "동시에 두 요청이 들어오면?", "향후 F1-01 취소 기능이 들어올 때 이 구조가 유지되나요?"*)을 질문한다.
   - **게이트 통과**: 설계가 타당하면 `DESIGN APPROVED` 선언 후 코딩 단계로 넘어간다.

3. **Step 3: `implement` (사용자 주도 프로덕션 코딩)**
   - **사용자**: 승인된 설계를 바탕으로 `app/` 및 `migrations/`에 실제 프로덕션 레벨 코드를 직접 작성한다.
   - 해당 이슈의 `# INTENDED-ISSUE: <ID>` 주석을 제거하고, 로컬에서 `make lint`(`ruff` + `mypy`)로 기본 정적 검사를 수행한다.
   - 구현이 끝나면 AI에게 *"구현 완료, 평가해줘"*라고 요청한다.

4. **Step 4: `evaluate — Adversarial Verification` (AI의 적대적 검증 및 부하 테스트)**
   - **AI**: 사용자가 작성한 코드를 읽고 다음 4가지 검증을 실행한다:
     1. **정적 분석**: `make lint` (`ruff check`, `ruff format --check`, `mypy`)
     2. **적대적 & 엣지 케이스 테스트 (`tests/adversarial/test_<id>.py`)**: `docs/reference/solution-guide.md`의 **`[적대적 테스트 포인트]`**와 사용자 코드의 취약 지점을 바탕으로 경계값, 잘못된 입력, 동시성 경쟁(Race condition), 외부 의존성 예외 상황을 찌르는 pytest를 작성·실행한다.
     3. **부하 테스트 (`k6`)**: `make load S=<id> PROFILE=target` 및 `EXPLAIN`으로 **After 지표**를 측정한다.
     4. **데이터 불변식 (`make check`) & 회귀 스모크**: `oversell`, `dup_orders` 및 `mixed` 스모크를 확인한다.

5. **Step 5: `evaluate — Production Code Review` (5대 루브릭 성적표 & PR 리뷰 게이트)**
   - **AI**: `docs/reference/solution-guide.md`의 **`[코드 리뷰 필수 체크 (Pitfalls)]`**에 적힌 프로덕션 함정에 빠지지 않았는지 대조하고, 아래 **5대 프로덕션 루브릭**으로 채점하여 `reports/<ID>-review.md` (`reports/_review_template.md` 기반)를 작성한다:
     1. **Architecture & Layering**: `router` / `service` / `repository` 책임 분리, 트랜잭션 경계, 향후 기능(`F1/F2`) 확장성
     2. **Concurrency & Integrity**: 동시성 제어, 락 범위/순서, 멱등성, 비즈니스 불변식 보장
     3. **Resilience & Error Handling**: 예외 처리, DB 세션/커넥션 정리, 타임아웃/폴백, 적절한 HTTP 상태코드
     4. **Code Craftsmanship**: 타입 힌트(`mypy` strict), 가독성, 도메인 모델 표현력, 불필요한 복잡도 배제
     5. **Performance & SLO**: 쿼리 플랜 개선, 부하 테스트 목표(SLO) 달성 여부
   - **판정 및 피드백 루프**:
     - 결함이나 개선 필요 사항이 있으면 **`CHANGES REQUESTED`**를 선언하고, 정답 코드를 대신 짜주지 않은 채 `파일:라인` 단위의 리뷰 코멘트를 남긴다 → 사용자가 직접 리팩토링(Step 3→4→5 반복).
     - 모든 기준을 충족하면 **`APPROVED`**를 선언한다.

6. **Step 6: `log & report` (문서화 및 커밋 마감)**
   - 전/후 수치와 트레이드오프, 코드 리뷰에서 개선한 핵심 사항을 `docs/experiments/<ID>.md`와 `reports/<ID>.md`에 기록하고 커밋한다.

### 커밋 컨벤션
```
<type>(<ISSUE-ID>): <요약>        # type ∈ break | verify-break | measure | design | fix | feat | refactor | test | verify | docs
```
- Phase 0 기능 구현: `feat(P0)[P1-02,P1-08]: 주문 API (N+1·루프 INSERT 포함)` — 심은 이슈 ID 병기
- 아키텍처 설계 및 구현: `design(P1-04): keyset 페이지네이션 RFC 작성`, `fix(P1-04): 커서 기반 상품 목록 페이지네이션 구현 (page 5000 p95 1.8s→12ms)`
- 신규 도메인 기능 구현: `feat(F1-01): 주문 취소 및 환불 상태머신 구현`
- 이력 조회: `git log --oneline --grep P1-04` → 측정→설계→구현→검증이 한 줄기로 보여야 한다
- Phase 경계 태그: `phase-0`, `phase-1-fixed`, `phase-2-fixed`

### 실험 로그 템플릿 (`docs/experiments/_template.md`)
```markdown
# <ID> <제목>
## 증상 / 가설
## 심은 지점 & 검증 승인 (파일·함수·라인, INTENDED-ISSUE 위치, 승인 일시)
## 재현 조건 (시나리오 파일, 데이터 상태, 리소스 제한)
## Before  — TPS, p50/p95/p99, err%, DB 지표 + 근거(EXPLAIN, 캡처 경로: assets/)
## 원인 분석
## 아키텍처 설계 & 수정 (난이도, 설계 문서 링크, 코드 리뷰 라운드, 커밋 해시)
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
