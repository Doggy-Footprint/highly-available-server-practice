# <ID> <제목>

> 이 로그가 갱신되어야 이슈가 완료된 것으로 친다 (§0-6).
> 재현이 안 됐으면 안 됐다고 그대로 적는다. 수치를 만들어내지 않는다 (§0-7).

## 증상 / 가설

<무엇이 터질 것으로 보는가. 왜 그렇게 보는가.>

## 심은 지점 & 검증 승인

| | |
|---|---|
| 파일·함수·라인 | `app/.../x.py:42` `service.do_thing()` |
| INTENDED-ISSUE 위치 | `grep -rn "INTENDED-ISSUE: <ID>"` 결과 |
| 백로그 정의와 일치하는 근거 | <1~2줄> |
| 승인 일시 | YYYY-MM-DD HH:MM |

## 재현 조건

| | |
|---|---|
| 시나리오 | `load/k6/<ID>.js` (`make load S=<ID> PROFILE=target`) |
| 데이터 상태 | seed 기본 / `make reset-deal` 후 / ... |
| 구성 | app xN, 리소스 프로파일 §13 기준, 변경점 명시 |
| 주입 | `MOCKPG_LATENCY_MS=...`, `MOCKPG_FAIL_RATE=...` 등 |

## Before

| 지표 | 값 |
|---|---|
| TPS | |
| p50 / p95 / p99 | |
| error rate | |
| DB active conn | |
| lock wait | |
| 기타 | |

근거:

```
<EXPLAIN (ANALYZE, BUFFERS) / pg_stat_statements 상위 쿼리 / k6 summary 발췌>
```

캡처: `docs/experiments/assets/<ID>-before-*.png`

## 원인 분석

<왜 이 수치가 나왔는가. 추측과 확인한 사실을 구분해서 적는다.>

## 수정

- 커밋: `<hash>` `fix(<ID>): ...`
- 무엇을 바꿨는가:

## After

| 지표 | Before | After |
|---|---|---|
| TPS | | |
| p50 / p95 / p99 | | |
| error rate | | |
| DB active conn | | |

근거:

```
<동일 항목>
```

invariant: `make check S=...` 결과
회귀: mixed 스모크 결과

## 트레이드오프 & 남은 한계

<모든 fix 에는 대가가 있다. 없으면 안 찾은 것이다.>

## 배운 것

<한 줄>
