// p1-04.js — 상품 목록(GET /products) 깊은 페이지 탐색(OFFSET vs Keyset/Cursor) 비교 시나리오.
//
// 심은 지점: app/products/repository.py `search_products()` (INTENDED-ISSUE: P1-04).
//   `stmt = _filtered(q, category_id).order_by(Product.id).limit(size).offset(page * size)`
//   깊은 페이지(page=5000~9500, offset=100,000~190,000)를 요청하면 앞의 행을 전부 스캔해 버리므로
//   탐색 깊이에 비례해 버퍼 읽기와 응답 지연이 선형으로 증가한다.
//
// 자동 모드 감지(setup):
//   GET /products?cursor=100000&size=20 호출 시 첫 아이템 id > 100000 이면 서버가 cursor 기반
//   Keyset 페이지네이션을 지원하는 상태(After)로 판단해 `?cursor=` 로 깊은 위치를 조회하고,
//   그렇지 않으면(Before) `?page=` 로 동일한 깊이(offset = page * 20)를 조회한다.
//
// 실행: make load S=p1-04 [PROFILE=smoke|target] N=3

import http from 'k6/http';
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:38080';
const PROFILE = __ENV.PROFILE || 'smoke';
const HTTP_TIMEOUT = '60s';
const SIZE = 20;

const EXECUTORS = {
  smoke: { executor: 'constant-vus', vus: 10, duration: '30s', gracefulStop: '30s' },
  target: { executor: 'constant-vus', vus: 30, duration: '1m', gracefulStop: '30s' },
};

export const options = {
  scenarios: {
    p1_04: Object.assign({ exec: 'p1_04' }, EXECUTORS[PROFILE] || EXECUTORS.smoke),
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

function randint(a, b) {
  return Math.floor(Math.random() * (b - a + 1)) + a;
}

const shallowDuration = new Trend('list_shallow_duration', true);
const deepDuration = new Trend('list_deep_duration', true);
const errors = new Counter('list_errors');

export function setup() {
  const probe = http.get(`${BASE}/products?cursor=100000&size=${SIZE}`, {
    timeout: HTTP_TIMEOUT,
  });
  let useCursor = false;
  if (probe.status === 200) {
    const items = probe.json('items');
    if (Array.isArray(items) && items.length > 0 && items[0].id > 100000) {
      useCursor = true;
    }
  }
  console.log(
    `[p1-04] BASE_URL=${BASE} PROFILE=${PROFILE} mode=${useCursor ? 'cursor(keyset)' : 'page(offset)'} — 20% 첫 페이지 / 80% 깊은 페이지(page 5000~9500 상당)`
  );
  return { useCursor };
}

export function p1_04(data) {
  // 20% 얕은 탐색(첫 페이지) vs 80% 깊은 탐색(page 5000~9500 / cursor 100000~190000)
  const isDeep = Math.random() < 0.8;
  const deepPage = randint(5000, 9500);
  const deepCursor = deepPage * SIZE;

  let query;
  if (!isDeep) {
    query = data.useCursor ? `size=${SIZE}` : `page=0&size=${SIZE}`;
  } else {
    query = data.useCursor
      ? `cursor=${deepCursor}&size=${SIZE}`
      : `page=${deepPage}&size=${SIZE}`;
  }

  const res = http.get(`${BASE}/products?${query}`, {
    tags: { action: isDeep ? 'list_deep' : 'list_shallow' },
    timeout: HTTP_TIMEOUT,
  });

  if (isDeep) {
    deepDuration.add(res.timings.duration);
  } else {
    shallowDuration.add(res.timings.duration);
  }

  const ok = check(res, {
    'list 200': (r) => r.status === 200,
    'items 20': (r) => {
      const items = r.json('items');
      return Array.isArray(items) && items.length === SIZE;
    },
  });
  if (!ok) errors.add(1);
}
