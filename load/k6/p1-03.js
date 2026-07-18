// p1-03.js — 상품 검색(GET /products?q=)의 무인덱스 ILIKE 를 재현.
//
// 심은 지점: app/products/repository.py `_filtered()` (INTENDED-ISSUE: P1-03),
//   app/models.py Product (INTENDED-ISSUE: P1-03, PK 외 인덱스 없음).
//   `Product.name.ilike('%q%') | Product.description.ilike('%q%')` — 선행 와일드카드라
//   btree 도 못 타 20만 행을 scan 한다.
//
// verify-break 로 확인한 선택도(selectivity) 함정 (EXPLAIN, measure 단계에서 직접 확인):
//   - 흔한 명사(예: "이어폰", 매치 ~9,933/200,000 ≈ 5%) 로 검색하면, ORDER BY id + LIMIT
//     조합 때문에 planner 가 PK 인덱스를 id 순으로 훑다 20건 채우면 멈춘다 — search 자체는
//     역설적으로 1ms 대로 빠르다(무인덱스 문제가 안 보임).
//   - 반면 count_products()(P1-05)는 LIMIT 이 없어 매번 Parallel Seq Scan 으로 전체를
//     실제로 다 센다 — q 가 있으면(ILIKE 비교) 카테고리만 필터할 때(정수 비교, ~15ms)보다
//     ~10배(≈145ms) 비싸진다. 이게 P1-03(ILIKE)이 같은 요청 안에서 P1-05(COUNT)를 통해
//     증폭되는 지점.
//   - 오타·과세부 검색어처럼 매치가 희소/0건인 검색(실사용에서 드물지 않음)은 search 자체도
//     20만 행 전부를 걸러야 끝나 300ms+ 로 치솟는다(EXPLAIN: rows=0, Rows Removed=200000).
//   → 그래서 이 시나리오는 흔한 명사만 쓰지 않고 "매치 희소/0건" 검색어를 섞어야
//     P1-03 고유의 병리(선택도가 낮을 때 인덱스 없이는 답이 없다)가 p95 에 드러난다.
//
// 재현 조건: app x3(Phase 1 구성, 이미 기동 중) + nginx, DB 2vCPU/4g(§13). 50 VU.
// 실행: make load S=p1-03 PROFILE=target N=3

import http from 'k6/http';
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const PROFILE = __ENV.PROFILE || 'smoke';

// 느리지만 정상인 무인덱스 seq scan 응답을 클라 타임아웃으로 실패 처리하지 않기 위한 상한.
const HTTP_TIMEOUT = '90s';

// mixed.js 와 동일한 명사 풀(재현 조건 일관성) — 매치 ~5%.
const HIT_NOUNS = [
  '이어폰', '키보드', '모니터', '마우스', '충전기', '백팩', '텀블러', '스탠드', '케이블', '스피커',
  '웹캠', '허브', '의자', '램프', '패드', '커피머신', '청소기', '선풍기', '이불', '프라이팬',
];

// 매치 희소/0건 검색어 — 오타·과세부 검색(모델번호 일부 등) 흉내. 실사용에서 흔한 패턴이고,
// ILIKE 가 무인덱스일 때 가장 비싸지는 지점(20만 행 전부를 걸러야 "없음"을 안다).
const MISS_TERMS = [
  '이어펀', '키보오드', '모나터', '마우스휠', '충전깅', 'FM-999999', 'FM-100000', '무선블루투스공진기',
];

const EXECUTORS = {
  smoke: { executor: 'constant-vus', vus: 10, duration: '1m', gracefulStop: '90s' },
  // 백로그(§6 P1-03) 재현 조건 그대로: 50 VU.
  target: { executor: 'constant-vus', vus: 50, duration: '3m', gracefulStop: '90s' },
};

export const options = {
  scenarios: {
    p1_03: Object.assign({ exec: 'p1_03' }, EXECUTORS[PROFILE] || EXECUTORS.smoke),
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

function randint(a, b) {
  return Math.floor(Math.random() * (b - a + 1)) + a;
}

function pick(arr) {
  return arr[randint(0, arr.length - 1)];
}

const searchDuration = new Trend('search_duration', true);
const missDuration = new Trend('search_miss_duration', true);
const hitDuration = new Trend('search_hit_duration', true);
const errors = new Counter('search_errors');

export function p1_03() {
  // 70% 흔한 명사(매치 있음) / 30% 희소·오타(매치 희소~0) — 실사용 검색 실패율을 과장 없이 반영.
  const isMiss = Math.random() < 0.3;
  const q = isMiss ? pick(MISS_TERMS) : pick(HIT_NOUNS);
  // 카테고리 필터를 섞어(50%) 목록 화면에서 흔한 "카테고리 안에서 검색" 패턴도 포함.
  const category = Math.random() < 0.5 ? `&category=${randint(1, 50)}` : '';

  const res = http.get(`${BASE}/products?q=${encodeURIComponent(q)}${category}&page=0&size=20`, {
    tags: { action: 'search' },
    timeout: HTTP_TIMEOUT,
  });

  searchDuration.add(res.timings.duration);
  (isMiss ? missDuration : hitDuration).add(res.timings.duration);
  const ok = check(res, { 'search 200': (r) => r.status === 200 });
  if (!ok) errors.add(1);
}

export function setup() {
  console.log(
    `[p1-03] BASE_URL=${BASE} PROFILE=${PROFILE} — GET /products?q=... 70% 흔한명사/30% 희소·오타, 50% category 동반`
  );
}
