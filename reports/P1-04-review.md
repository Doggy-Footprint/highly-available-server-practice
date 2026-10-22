# [Production Review] P1-04 상품 목록 깊은 페이지 탐색 지연 (OFFSET → Keyset/Cursor) — Round 1

- **검토 일시**: 2026-10-21 10:55
- **적용 난이도**: `Lv.1 (재활 모드)`
- **설계 문서**: [`docs/designs/P1-04.md`](../docs/designs/P1-04.md)
- **종합 판정**: `APPROVED` (Lv.1 기준 통과 — 1건의 쿼리 중복 호출 개선 팁 및 포맷팅 안내 포함)

---

## 1. 자동 검증 요약 (Verification Matrix)

| 검증 단계 | 실행 명령 / 시나리오 | 결과 (`PASS`/`FAIL`) | 핵심 수치 및 요약 |
|---|---|---|---|
| **정적 분석 & 타입 체크** | `make lint` (`ruff` + `mypy`) | `WARN` (포맷팅 2건) | `ruff check` **PASS**, `mypy` (41개 파일) **PASS**, `ruff format --check`에서 `schemas.py`, `service.py` 공백 포맷팅 2건 감지 |
| **기능 & 적대적 테스트** | `make test T=tests/adversarial/test_p1_04.py` | **`PASS` (7/7)** | 연속 페이지 순회(중복·누락 0), 마지막 페이지 경계값(`cursor=199980, size=20` → `next_cursor=None`), `category`+`q` 복합 필터, 초과 커서(`999999999`), 비정상 커서(`0, -1, -999` → `422`) 전부 통과 |
| **부하 테스트 (SLO)** | `make load S=p1-04 PROFILE=target N=3` | **`PASS`** | 처리량 `60.4/s → 104.7/s` (+73%), DB 목록 쿼리 평균 `185.15ms → 0.43ms` (**430배 단축**), 블록 스캔 `4,414 → 4 블록` (**1,103배 감소**), `shallow`(`282.8ms`) vs `deep`(`286.2ms`) 응답 지연 완전 평탄화 달성 |
| **데이터 불변식 (Invariant)** | `pg_stat_statements` / 쿼리 플랜 점검 | **`PASS`** | `Index Scan using products_pkey` (`Index Cond: id > :cursor`), 불필요한 앞선 행 스캔 0건 |

---

## 2. 5대 프로덕션 루브릭 성적표 (Scorecard)

> 등급 기준: **S** (프로덕션 모범 사례) / **A** (프로덕션 배포 가능, 사소한 개선점만 존재) / **B** (동작하나 엣지 케이스·구조 보완 필요) / **C** (핵심 결함 또는 안티패턴 존재) / **F** (요구사항 미충족 또는 장애 유발)

| 평가 축 | 등급 | 평가 코멘트 요약 |
|---|---|---|
| **1. Architecture & Layering**<br/>(계층 분리, 트랜잭션 경계, 확장성) | **A** | `router`(파라미터 검증) → `service`(다음 커서 판별) → `repository`(Keyset 쿼리 구성) 책임 분리가 깔끔하게 유지되었습니다. |
| **2. Concurrency & Integrity**<br/>(동시성 제어, 멱등성, 불변식 보장) | **A** | 마지막 페이지가 `size`에 딱 맞아떨어질 때도 `size + 1` 조회를 통해 `next_cursor=None`을 정확히 판별합니다. (단, 2회 쿼리 분리 호출로 인한 미세 레이스 여지는 아래 코멘트 참고) |
| **3. Resilience & Error Handling**<br/>(예외 처리, 리소스 정리, 타임아웃/폴백) | **S** | `cursor: int | None = Query(default=None, ge=1)`로 0 이하 비정상 커서를 라우터 입구에서 `422 Unprocessable Entity`로 완벽히 차단했습니다. |
| **4. Code Craftsmanship**<br/>(타입 안정성, 가독성, 도메인 표현력) | **A** | `mypy --strict`를 단번에 통과했으며 코드 의도가 명확합니다. (`ruff format`만 실행하면 완벽합니다.) |
| **5. Performance & SLO**<br/>(쿼리 플랜, 부하 지표 전/후 개선도) | **A** | 깊은 탐색 쿼리 자체가 `185.15ms → 0.43ms`(블록 `4,414 → 4`)로 줄어 `shallow`와 `deep`의 속도 차이가 완전히 사라졌습니다. `service.py`의 중복 조회만 1회로 합치면 **S** 등급입니다. |

---

## 3. 상세 코드 리뷰 코멘트 (Inline Review)

### [Major / Design] (구조·효율성 개선 권장 — Lv.1 학습 팁)
- **[`app/products/service.py:11-17`](../app/products/service.py#L11-L17)**:
  - **관찰**:
    ```python
    items = await repository.search_products(session, q, category_id, cursor, size)
    further_items = await repository.search_products(session, q, category_id, cursor, size + 1)
    ```
    현재 `size`개 조회 쿼리와 `size + 1`개 조회 쿼리를 각각 호출해 요청당 목록 `SELECT` 쿼리가 **2번씩** 나가고 있습니다 (`pg_stat_statements`에서도 요청 6,310건당 목록 SELECT가 12,620회 기록됨).
  - **제안**:
    `further_items`(즉 `size + 1`개) 안에 이미 앞의 `size`개 아이템이 그대로 들어 있습니다! 따라서 `search_products(..., size + 1)` **딱 한 번만 호출**한 뒤, 파이썬 슬라이싱(`items = further_items[:size]`)으로 잘라 쓰면 DB 왕복을 절반(2회 → 1회)으로 줄이고 두 쿼리 사이의 동시성 불일치 가능성도 원천 제거할 수 있습니다.

### [Nit / Learning Note] (코드에 남겨주신 질문 답변 & 포맷팅)
- **[`app/products/schemas.py:19`](../app/products/schemas.py#L19)** (`# What about previous?`):
  - **질문 답변 ("이전 페이지(`prev_cursor`)는 어떻게 하나요?")**:
    - 무한 스크롤이나 "더보기" UI에서는 `next_cursor`만 쓰지만, 페이지 단위 "이전(<) / 다음(>)" 버튼이 있는 UI에서는 **양방향 Keyset 페이지네이션**을 씁니다.
    - 원리는 대칭적입니다: 현재 페이지의 **첫 번째 아이템 `id`**를 `before_cursor`(또는 `prev_cursor`)로 넘기고, DB에서는 `WHERE id < :before_cursor ORDER BY id DESC LIMIT size + 1`로 바로 앞 묶음을 가져온 뒤 애플리케이션에서 다시 오름차순(`reversed`)으로 뒤집어 반환합니다.
- **코드 포맷팅 (`make lint`)**:
  - `app/products/schemas.py:19`(주석 앞 공백 2칸 규칙)와 `app/products/service.py:14`(`if (...)` 괄호 제거) 때문에 `uv run ruff format --check`에서 경고가 뜹니다. `uv run ruff format app/products/` 한 번만 실행해 주시면 `make lint` 전체가 깔끔하게 통과합니다.

---

## 4. 다음 액션 (Next Steps)

- `Lv.1 (재활 모드)` 기준 핵심 병목 해결 및 적대적 테스트 7건을 모두 통과하여 **`APPROVED`** 되었습니다!
- 선택지:
  1. 위 `service.py`의 1회 쿼리 슬라이싱(`further_items[:size]`) 리팩토링 + `uv run ruff format`까지 가볍게 반영해 볼지,
  2. 아니면 바로 `P1-04` 실험 로그(`docs/experiments/P1-04.md`) 및 최종 리포트(`reports/P1-04.md`)를 정리하고 다음 과제(`P1-05`: 목록 `COUNT(*)` 병목 제거)로 넘어갈지 알려주세요!
