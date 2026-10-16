# [Production Review] <ID> <제목> — Round <N>

- **검토 일시**: YYYY-MM-DD HH:MM
- **적용 난이도**: `Lv.1` | `Lv.2` | `Lv.3` | `Lv.4`
- **설계 문서**: `docs/designs/<ID>.md`
- **종합 판정**: `APPROVED` | `CHANGES REQUESTED`

---

## 1. 자동 검증 요약 (Verification Matrix)

| 검증 단계 | 실행 명령 / 시나리오 | 결과 (`PASS`/`FAIL`) | 핵심 수치 및 요약 |
|---|---|---|---|
| **정적 분석 & 타입 체크** | `make lint` (`ruff` + `mypy`) | | |
| **기능 & 적대적 테스트** | `make test` (`tests/adversarial/test_<id>.py`) | | 경계값, 동시성 레이스, 예외 주입 결과 |
| **부하 테스트 (SLO)** | `make load S=<id> PROFILE=target` | | TPS, p50/p95/p99, err% |
| **데이터 불변식 (Invariant)** | `make check S=...` / DB 상태 점검 | | oversell, 중복 주문, 커넥션 누수 여부 |

---

## 2. 5대 프로덕션 루브릭 성적표 (Scorecard)

> 등급 기준: **S** (프로덕션 모범 사례) / **A** (프로덕션 배포 가능, 사소한 개선점만 존재) / **B** (동작하나 엣지 케이스·구조 보완 필요) / **C** (핵심 결함 또는 안티패턴 존재) / **F** (요구사항 미충족 또는 장애 유발)

| 평가 축 | 등급 | 평가 코멘트 요약 |
|---|---|---|
| **1. Architecture & Layering**<br/>(계층 분리, 트랜잭션 경계, 확장성) | | |
| **2. Concurrency & Integrity**<br/>(동시성 제어, 멱등성, 불변식 보장) | | |
| **3. Resilience & Error Handling**<br/>(예외 처리, 리소스 정리, 타임아웃/폴백) | | |
| **4. Code Craftsmanship**<br/>(타입 안정성, 가독성, 도메인 표현력) | | |
| **5. Performance & SLO**<br/>(쿼리 플랜, 부하 지표 전/후 개선도) | | |

---

## 3. 상세 코드 리뷰 코멘트 (Inline Review)

> AI는 정답 코드를 직접 짜주지 않고 문제 원인과 개선 방향을 리뷰 코멘트로 제시합니다. (단, 사용자가 `힌트 3단계` 또는 페어 수정을 요청한 경우 예시 스니펫을 함께 제공합니다.)

### [Blocker / Must Fix] (`APPROVED` 전 반드시 해결 필요)
- **`app/.../파일.py:라인`**:
  - **문제**: 
  - **영향 (프로덕션 리스크)**: 
  - **개선 방향 질문/가이드**: 

### [Major / Design] (구조·엣지 케이스 개선 권장)
- **`app/.../파일.py:라인`**:
  - **관찰**: 
  - **제안**: 

### [Nit / Learning Note] (사소한 스타일 또는 학습 팁)
- **`app/.../파일.py:라인`**:
  - 

---

## 4. 다음 액션 (Next Steps)

- [ ] (수정이 필요한 체크리스트 항목)
