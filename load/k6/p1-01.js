// p1-01.js — 로그인 세션이 프로세스 메모리(dict)에 있어 인스턴스 간 공유되지 않음을 재현.
//
// 심은 지점: app/auth/service.py `_SESSIONS` (INTENDED-ISSUE: P1-01).
// 재현 조건: app N>=2 (nginx LB 필요) — `make up N=3` 후 `make load S=p1-01`.
//   N=1(Phase 0 기본 구성)에서는 세션이 항상 같은 프로세스에 있으므로 재현되지 않는다.
//
// 시나리오: VU 마다 신규 유저를 만들어 로그인(응답의 instance_id 로 "발급 인스턴스" 기록) 한 뒤,
// 같은 토큰으로 GET /auth/me 를 반복 호출한다. nginx 가 요청을 여러 app 인스턴스로 흩뿌리면,
// 로그인 인스턴스가 아닌 곳으로 라우팅된 호출은 그 프로세스의 dict 에 토큰이 없어 401 이 난다.
//
// 관찰 지표:
//   me_401_rate            — /auth/me 가 401 로 실패하는 비율 (문제가 있으면 0 보다 크게 뜬다)
//   me_instance_mismatch   — /auth/me 가 200 인데 instance_id 가 로그인 인스턴스와 다른 경우
//                            (0 이어야 정상: 세션이 프로세스에 갇혀 있다는 가설의 반증이 되므로
//                             0 이 아니면 그 자체가 흥미로운 신호 — 원인 분석에서 다룬다)

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Counter } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const PROFILE = __ENV.PROFILE || 'smoke';

const HTTP_TIMEOUT = '30s';

const me401Rate = new Rate('me_401_rate');
const meInstanceMismatch = new Counter('me_instance_mismatch');
const meCalls = new Counter('me_calls_total');

// smoke: 세션 문제가 통계적으로 보일 만큼(반복 호출 다수) VU 를 적당히 굴린다.
// 목적이 TPS 관문이 아니라 "재현되는가" 이므로 target/limit 프로파일은 두지 않는다.
const EXECUTORS = {
  smoke: { executor: 'constant-vus', vus: 30, duration: '40s', gracefulStop: '30s' },
};

export const options = {
  // k6 는 기본적으로 VU 당 커넥션을 keep-alive 로 재사용한다. nginx 의 resolver 기반
  // 동적 proxy_pass(§11)는 "새 커넥션을 열 때"만 백엔드를 다시 고르므로, 재사용을 끄지
  // 않으면 한 VU 의 모든 요청이 로그인 때 잡힌 백엔드에 고정돼 버려 문제가 가려진다.
  // (1차 실행에서 me_401_rate 0% 로 재현 실패 → 이 옵션 추가 후 재시도.)
  noConnectionReuse: true,
  scenarios: {
    p1_01: Object.assign({ exec: 'p1_01' }, EXECUTORS[PROFILE] || EXECUTORS.smoke),
  },
  // 관문 성격이 아니라 재현 실험이므로 threshold 로 실패시키지 않는다.
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

// VU 로컬 상태 (mixed.js 와 동일한 관례: k6 는 VU 마다 스크립트를 독립 인스턴스로 돌린다).
let creds = null;
let token = null;
let loginInstance = null;

function signupAndLogin() {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
  creds = { email: `p101-${suffix}@flashmart.test`, password: 'p101-pw' };

  const signupRes = http.post(`${BASE}/auth/signup`, JSON.stringify(creds), {
    headers: { 'Content-Type': 'application/json' },
    tags: { action: 'signup' },
    timeout: HTTP_TIMEOUT,
  });
  check(signupRes, { 'signup 201': (r) => r.status === 201 });

  const loginRes = http.post(`${BASE}/auth/login`, JSON.stringify(creds), {
    headers: { 'Content-Type': 'application/json' },
    tags: { action: 'login' },
    timeout: HTTP_TIMEOUT,
  });
  check(loginRes, { 'login 200': (r) => r.status === 200 });
  if (loginRes.status === 200) {
    token = loginRes.json('token');
    loginInstance = loginRes.json('instance_id');
  }
}

export function p1_01() {
  if (token === null) {
    signupAndLogin();
    sleep(0.1);
    return;
  }

  const res = http.get(`${BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    tags: { action: 'me' },
    timeout: HTTP_TIMEOUT,
  });

  meCalls.add(1);
  const is401 = res.status === 401;
  me401Rate.add(is401);

  check(res, { 'me 200 or 401 (no other errors)': (r) => r.status === 200 || r.status === 401 });

  if (res.status === 200) {
    const instanceId = res.json('instance_id');
    if (instanceId !== loginInstance) {
      meInstanceMismatch.add(1);
    }
  }

  sleep(randint(1, 4) / 10);
}

function randint(a, b) {
  return Math.floor(Math.random() * (b - a + 1)) + a;
}

export function setup() {
  console.log(`[p1-01] BASE_URL=${BASE} PROFILE=${PROFILE} — app N>=2 아니면 401 이 안 뜬다`);
}
