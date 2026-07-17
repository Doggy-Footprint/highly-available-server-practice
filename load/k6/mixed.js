// mixed.js — 공용 트래픽 믹스 (CLAUDE.md §8)
//
// 믹스 비율: 목록 35 / 상세 25 / 검색 10 / 주문 15 / 내역 10 / 로그인 5 (%)
// 프로파일(PROFILE env): smoke(10vu·1m) / target(관문 300TPS·5m) / limit(한계까지 ramp)
//
// 실행: make load S=mixed [PROFILE=smoke|target|limit] [N=3]
//   Makefile 이 BASE_URL(Phase0=http://app:8000, Phase1+=http://nginx)·PROFILE 을 env 로 넣는다.
//
// 이 스크립트의 역할은 "가상의 서비스가 전형적 트래픽에서 기능적으로 도는가"다(§5 Phase 0
// 관문의 smoke). 특정 문제를 폭발시키는 건 이슈별 전용 시나리오(p1-02.js 등, 각 이슈의
// measure)의 몫이다.
//
// 인증 브랜치(주문/내역)는 VU 마다 signup→login 으로 만든 "신규 유저"를 쓴다. 이유:
//   seed 는 일반 유저에게도 ~48주문을 주는데, GET /orders 는 N+1(P1-02)에 무인덱스
//   (orders.user_id / order_items.order_id) seq scan 이 겹쳐 주문 1건마다 800만 행을
//   훑는다 → seed 유저 내역은 단발 20s+, 10VU 에선 DB 포화 피드백 루프로 분 단위가 된다.
//   그건 "느리지만 정상 동작"이 아니라 스모크를 못 돌게 만드는 수준이라, 그 병리는 여기가
//   아니라 전용 시나리오(p1-02.js/p1-11.js, §6)에서 헤비·대량주문 유저로 자극한다.
//   신규 유저는 주문 0~몇 건이라 내역이 가벼워 스모크가 제 일(기능 확인)을 할 수 있다.
// 무인덱스 지연 자체는 목록/상세/검색(전부 seq scan) p95 에 그대로 드러나므로 가려지지 않는다.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const PROFILE = __ENV.PROFILE || 'smoke';

// 느리지만 정상인 응답(무인덱스 seq scan)을 클라 타임아웃으로 실패 처리하지 않기 위한 상한.
const HTTP_TIMEOUT = '120s';

// seed 규모와 맞춘 상수 (seed/seed.py). 딜 전용 상품(뒤쪽 20개)은 일반 주문/카트에서 제외.
const N_PRODUCTS = 200000;
const NORMAL_PRODUCT_MAX = 199980; // N_PRODUCTS - N_DEALS

// 검색어: seed 상품명이 "형용사 명사 접미사 {id}" 라서, 명사 하나를 q 로 던지면
// 20만 건 중 약 1/20 이 매칭된다 (매칭 비율이 예측 가능해야 전/후 비교가 된다).
const NOUNS = [
  '이어폰', '키보드', '모니터', '마우스', '충전기', '백팩', '텀블러', '스탠드', '케이블', '스피커',
  '웹캠', '허브', '의자', '램프', '패드', '커피머신', '청소기', '선풍기', '이불', '프라이팬',
];

// 프로파일별 executor (§8). gracefulStop 은 느린 응답(최대 HTTP_TIMEOUT)이 종료 시점에
// 잘려 오염되지 않게 smoke 에서 넉넉히 준다.
const EXECUTORS = {
  smoke: { executor: 'constant-vus', vus: 10, duration: '1m', gracefulStop: '150s' },
  target: {
    // Phase 1 관문: mixed 300 TPS 5분. iteration=1 트랜잭션으로 본다.
    executor: 'constant-arrival-rate',
    rate: 300,
    timeUnit: '1s',
    duration: '5m',
    preAllocatedVUs: 200,
    maxVUs: 800,
    gracefulStop: '30s',
  },
  limit: {
    // 한계까지 VU 를 올려 어디서 무너지는지 본다.
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '1m', target: 100 },
      { duration: '2m', target: 400 },
      { duration: '2m', target: 800 },
      { duration: '2m', target: 1500 },
      { duration: '30s', target: 0 },
    ],
    gracefulStop: '30s',
  },
};

// 프로파일별 임계. smoke 는 기능(에러)만, target 은 Phase 1 관문(p95<300ms, err<1%).
const THRESHOLDS = {
  smoke: { http_req_failed: ['rate<0.01'] },
  target: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<300'] },
  limit: {}, // 한계 탐색이라 임계로 실패시키지 않는다
};

export const options = {
  scenarios: {
    mixed: Object.assign({ exec: 'mixed' }, EXECUTORS[PROFILE]),
  },
  thresholds: THRESHOLDS[PROFILE],
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

function randint(a, b) {
  return Math.floor(Math.random() * (b - a + 1)) + a;
}

function pick(arr) {
  return arr[randint(0, arr.length - 1)];
}

function login(creds) {
  const res = http.post(`${BASE}/auth/login`, JSON.stringify(creds), {
    headers: { 'Content-Type': 'application/json' },
    tags: { action: 'login' },
    timeout: HTTP_TIMEOUT,
  });
  check(res, { 'login 200': (r) => r.status === 200 });
  return res.status === 200 ? res.json('token') : null;
}

// 아래 둘은 VU 로컬이다 (k6 는 VU 마다 스크립트를 독립 인스턴스로 돌린다).
let creds = null; // 이 VU 전용 신규 유저 { email, password }
let token = null;

// 첫 이터레이션에 이 VU 전용 신규 유저를 만들고 로그인해 토큰을 얻는다.
function ensureUser() {
  if (creds === null) {
    // users.email 에 UNIQUE 제약이 없어(P1-03, models.py) 매 실행·VU 마다 새 유저가 생긴다.
    // 신규 유저는 주문 0건에서 시작해 주문 브랜치로 몇 건만 쌓이므로 내역이 가볍다.
    const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
    creds = { email: `smoke-${suffix}@flashmart.test`, password: 'smoke-pw' };
    const res = http.post(`${BASE}/auth/signup`, JSON.stringify(creds), {
      headers: { 'Content-Type': 'application/json' },
      tags: { action: 'signup' },
      timeout: HTTP_TIMEOUT,
    });
    check(res, { 'signup 201': (r) => r.status === 201 });
  }
  if (token === null) token = login(creds);
}

export function mixed() {
  ensureUser();

  const r = Math.random() * 100;

  if (r < 35) {
    // 목록 (35%)
    const res = http.get(
      `${BASE}/products?category=${randint(1, 50)}&page=${randint(0, 50)}&size=20`,
      { tags: { action: 'list' }, timeout: HTTP_TIMEOUT },
    );
    check(res, { 'list 200': (x) => x.status === 200 });
  } else if (r < 60) {
    // 상세 (25%)
    const res = http.get(`${BASE}/products/${randint(1, N_PRODUCTS)}`, {
      tags: { action: 'detail' },
      timeout: HTTP_TIMEOUT,
    });
    check(res, { 'detail 200': (x) => x.status === 200 });
  } else if (r < 70) {
    // 검색 (10%) — P1-03 자극
    const res = http.get(
      `${BASE}/products?q=${encodeURIComponent(pick(NOUNS))}&page=0&size=20`,
      { tags: { action: 'search' }, timeout: HTTP_TIMEOUT },
    );
    check(res, { 'search 200': (x) => x.status === 200 });
  } else if (r < 85) {
    // 주문 (15%) — 카트에 담고 주문 생성 (인증). P1-02/07/08·P2-03/04 경로.
    // 앱이 카트를 안 비우므로(P2-04) 같은 유저 카트는 누적된다(설계된 결과).
    if (token) {
      const authJson = {
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        timeout: HTTP_TIMEOUT,
      };
      http.post(
        `${BASE}/cart/items`,
        JSON.stringify({ product_id: randint(1, NORMAL_PRODUCT_MAX), qty: randint(1, 3) }),
        Object.assign({ tags: { action: 'cart_add' } }, authJson),
      );
      const res = http.post(`${BASE}/orders`, null, {
        headers: { Authorization: `Bearer ${token}` },
        tags: { action: 'order' },
        timeout: HTTP_TIMEOUT,
      });
      check(res, { 'order 201': (x) => x.status === 201 });
    }
  } else if (r < 95) {
    // 내역 (10%) — P1-02(N+1)·P1-11(무LIMIT) 경로. 신규 유저라 주문 몇 건뿐이라 가볍다.
    if (token) {
      const res = http.get(`${BASE}/orders`, {
        headers: { Authorization: `Bearer ${token}` },
        tags: { action: 'history' },
        timeout: HTTP_TIMEOUT,
      });
      check(res, { 'history 200': (x) => x.status === 200 });
    }
  } else {
    // 로그인 (5%) — P1-10(bcrypt CPU 블로킹) 자극. 이 VU 유저로 재로그인한다.
    login(creds);
  }

  sleep(randint(1, 3) / 10); // 0.1~0.3s think time
}

export function setup() {
  console.log(`[mixed] BASE_URL=${BASE} PROFILE=${PROFILE} HTTP_TIMEOUT=${HTTP_TIMEOUT}`);
}
