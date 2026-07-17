# 빌드 컨텍스트는 저장소 루트다 (compose 의 `context: ..`).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /srv

# uv.lock 에 고정된 버전으로만 설치한다 (--frozen).
# pyproject 의 `>=` 범위로 매번 최신을 집으면, 몇 달 뒤 재빌드한 이미지의 수치를
# 오늘 수치와 나란히 놓을 수 없다. 이 저장소의 실험은 전/후 비교가 전부이므로
# 라이브러리 버전은 측정 조건의 일부다. 의존성을 올릴 때는 uv.lock 을 갱신해 커밋한다.
COPY pyproject.toml uv.lock /srv/
RUN uv sync --frozen --no-install-project

ENV PATH="/srv/.venv/bin:$PATH"

COPY alembic.ini /srv/
COPY app /srv/app
COPY migrations /srv/migrations
COPY seed /srv/seed

EXPOSE 8000

# INTENDED-ISSUE: P1-09
# uvicorn 워커 1개. 인스턴스도 1대(Phase 0)라 전체 처리량이 단일 프로세스에 묶인다.
# 워커 수를 늘리기 전에 P1-09 에서 한계를 먼저 측정한다 —
# 총 커넥션 = 인스턴스 수 x 워커 수 x (pool_size + max_overflow) 계산도 그때 함께 한다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
