# P0 smoke baseline — mixed 스모크 통과 및 Phase 0 관문 확인

- **일시**: 2026-07-18
- **시나리오**: `load/k6/mixed.js` `PROFILE=smoke` (10 VU · 1m) — `make load S=mixed PROFILE=smoke`
- **판정**: **PASS** (http_req_failed 0.00%) → §14-5 완료, `phase-0` 태그 대상
- **구성**: app×1 (Phase 0, compose.direct), db(§13: 2vCPU/4g, shared_buffers 1g),
  mockpg `LATENCY_MS=0 / FAIL_RATE=0`. DB = seed 기본
  (users 5만 / products 20만 / orders 300만 / order_items 800만 / deals 20 / cart_items 2만).
  주: cart_items 는 구 seed(교차 카트 재seed 는 P2-03 measure 전에 `make seed`).

---

## 1. 이 스모크의 역할

mixed 스모크는 **"가상의 서비스가 전형적 트래픽(§8 믹스)에서 기능적으로 도는가"**를 보는
Phase 0 관문이다. 특정 심은 문제를 폭발시키는 건 이슈별 전용 시나리오(각 이슈 measure)의
몫이므로, 여기서는 **에러율만** 임계로 본다(`http_req_failed < 0.01`). 지연 관문(p95<300ms)은
target 프로파일(Phase 1)에서만 강제한다 — Phase 0 는 무인덱스라 느린 게 정상이고, 그 느린
수치가 '전/후' 비교의 before 다.

## 2. 결과 (통과본)

```
checks ............ 100.00%  (444/444)   signup·login·list·detail·search·order·history 전부 ✓
http_req_failed ... 0.00%    (0/506)     → PASS
throughput ........ 6.56 iter/s, 7.83 req/s
http_req_duration . avg 1.04s | med 401ms | p90 2.31s | p95 4.0s | p99 11.78s | max 17.56s
```

- 전 요청 완주(타임아웃/5xx 0). 기능적으로 전 기능 동작 확인.
- **느림은 설계된 baseline**: 목록/상세/검색이 전부 무인덱스 seq scan(products 20만, reviews
  100만, `ILIKE '%q%'`), 주문 경로는 P1-06/07/08·P2-03/04 를 그대로 탄다. p95 4s 는
  Phase 1 관문(<300ms) 대비 개선 여지를 그대로 보여준다.

## 3. 재현 조건 조정 과정 (§0-7 — 실패도 그대로 기록)

스모크가 처음부터 통과한 게 아니다. GET /orders(내역)가 **P1-02(N+1) × 무인덱스**
(`orders.user_id` / `order_items.order_id` 인덱스 없음)로, seed 유저는 주문 1건마다 800만 행
order_items 를 seq scan 한다.

| 시도 | 조건 | 결과 |
|---|---|---|
| 1 | seed 랜덤 유저(주문 ~48건), k6 기본 timeout 60s | **FAIL** http_req_failed 4.65%(6/129). 내역 6건 전부 60s 타임아웃 |
| 2 | 동일 + HTTP_TIMEOUT 120s | **FAIL** 6.87%(9/131). 내역이 120s 로도 미완주 |
| 3 | **인증 브랜치를 VU별 신규 유저 세션으로** + 120s | **PASS** 에러 0 |

- **원인**: 내역은 이터레이션의 10%지만 *시간*으로는 ~92%(단발 20s vs 0.2s)라, 10VU 중
  ~9개가 항상 동시에 내역을 실행 → 800만 행 동시 seq scan 으로 DB(2vCPU) 포화 →
  내역이 더 느려짐 → 더 쌓임(양의 되먹임). timeout 상향만으로는 루프가 더 부풀 뿐이었다.
- **해결(설계 정합)**: mixed 는 "전형적 트래픽"이므로, VU 마다 `signup→login` 으로 만든
  **신규 유저**(주문 0~몇 건)로 주문/내역을 수행한다. `users.email` 에 UNIQUE 제약이 없어
  (P1-03) 매 실행·VU 마다 새 유저가 깔끔히 생긴다. 내역이 가벼워 완주하고 되먹임이 사라진다.
- **무엇을 안 가렸나**: 무인덱스 지연은 목록/상세/검색 p95(위 4s)에 그대로 남는다.
  "주문 많은 유저 → N+1 폭발"(P1-02)·"헤비 유저 무제한 응답"(P1-11)의 병리는 mixed 가 아니라
  전용 시나리오(p1-02.js / p1-11.js, §6)에서 헤비/대량주문 유저로 자극한다.

## 4. Phase 0 관문(§5) 점검

- ✅ 전 기능 동작 — 수동 워크스루(전 엔드포인트 200) + 스모크 전 액션 ✓
- ✅ smoke(10vu·1m) 통과 — http_req_failed 0.00%
- ✅ 심은 문제 전부 포함 + `INTENDED-ISSUE` — verify-break 승인(`reports/p0-verify-break.md`, 18건 + 재심기 2건)

→ `git tag phase-0`.

## 5. 후속

- Phase 1 진입 시: nginx + app×3 + Redis 도입, mixed `PROFILE=target`(300 TPS·5m, p95<300ms) 관문.
- 이슈 사이클은 사용자가 지시할 때 하나씩(§0-5). P2-03 measure 전 `make seed`(교차 카트) 재실행.
