// p1-02.js — 주문 내역(GET /orders)의 N+1 을 재현.
//
// 심은 지점: app/orders/service.py `_build_order_view` (INTENDED-ISSUE: P1-02).
//   list_orders() 가 유저의 주문 전체를 가져온 뒤, 주문마다 get_order_items 를,
//   아이템마다 product_repo.get_product 를 개별 쿼리로 호출한다.
//   요청당 쿼리 수 ≈ 1(주문 목록) + N(주문별 아이템) + N*M(아이템별 상품).
//
// 재현 조건: seed 기본 유저(주문 48~49건, 아이템 평균 2.6개/주문 — 백로그의 "30건"과
//   자릿수가 같은 대표 유저를 사용. seed 의 헤비 유저(3,000건, user_id 1·99·161·176·188
//   등)는 P1-11(LIMIT 없는 전체 조회) 전용 소재라 여기서는 피한다.
// VU 마다 다른 유저(user300..user300+VU-1)로 로그인해 실제 유저 분산 트래픽을 흉내낸다.
//
// DB 측 쿼리 수·pg_stat_statements 는 이 스크립트가 아니라 실행 전후 수동으로
// `pg_stat_statements_reset()` → 실행 → 집계 쿼리로 별도 확인한다 (실험 로그 참고).

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const PROFILE = __ENV.PROFILE || 'smoke';
const BASE_USER_ID = 300; // user300.. — 49건 주문 유저 블록 (heavy 유저 제외)

// 요청 1건이 uncontended 상태에서도 수 초대(49주문×N+1)라, constant-vus 로 반복 루프를
// 돌리면 도착률이 처리율을 곧장 앞질러 서버가 처리를 마치기도 전에 요청이 쌓인다
// (1차 시도: 20 VU·constant-vus·30s → 100% 30s 타임아웃, 게다가 k6 가 요청을 포기한
//  뒤에도 서버는 이미 시작한 N+1 루프를 취소하지 않고 계속 돌려 DB 에 잔여 부하가
//  수십 초 더 남았다 — 클라이언트 타임아웃이 서버 작업을 취소하지 않는다는 것 자체는
//  P2-14 소재라 여기서는 다루지 않고, 재현 조건만 "동시 요청 스냅샷"으로 바꿨다).
// per-vu-iterations(1회) 로 VU 마다 정확히 한 번만 요청해 "동시 사용자 수" 를 깨끗하게
// 통제한다 — 무한 재시도로 배치 오리진 폭주(backlog)를 만들지 않는다.
const HTTP_TIMEOUT = '90s';

const ordersDuration = new Trend('orders_list_duration', true);

// 목적이 TPS 관문이 아니라 "요청당 쿼리 수·지연 재현" 이므로 VU 를 크게 키우지 않는다
// (P1-09 의 풀 고갈과 신호가 섞이는 것을 피함). DB 는 §13 프로파일상 2 vCPU 고정.
const EXECUTORS = {
  smoke: { executor: 'per-vu-iterations', vus: 10, iterations: 1, maxDuration: '3m' },
};

export const options = {
  scenarios: {
    p1_02: Object.assign({ exec: 'p1_02' }, EXECUTORS[PROFILE] || EXECUTORS.smoke),
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

function login() {
  const userId = BASE_USER_ID + (__VU - 1);
  const creds = { email: `user${userId}@flashmart.test`, password: 'flashmart-pw' };
  const loginRes = http.post(`${BASE}/auth/login`, JSON.stringify(creds), {
    headers: { 'Content-Type': 'application/json' },
    tags: { action: 'login' },
    timeout: HTTP_TIMEOUT,
  });
  check(loginRes, { 'login 200': (r) => r.status === 200 });
  return loginRes.status === 200 ? loginRes.json('token') : null;
}

export function p1_02() {
  const token = login();
  if (token === null) {
    return;
  }

  const res = http.get(`${BASE}/orders`, {
    headers: { Authorization: `Bearer ${token}` },
    tags: { action: 'list_orders' },
    timeout: HTTP_TIMEOUT,
  });

  ordersDuration.add(res.timings.duration);
  check(res, { 'orders 200': (r) => r.status === 200 });
}

export function setup() {
  console.log(
    `[p1-02] BASE_URL=${BASE} PROFILE=${PROFILE} — user${BASE_USER_ID}.. (주문 49건/유저) 로 VU 수만큼 동시 GET /orders 1회씩`
  );
}
