"""요청 스코프 의존성.

요청마다 세션을 하나 만들어 주입한다. Phase 0 구현은 이 세션을 예외 경로에서
닫지 않는다 (P1-12) — 자세한 건 아래 주석.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory


async def get_db() -> AsyncIterator[AsyncSession]:
    # INTENDED-ISSUE: P1-12
    # 세션을 열고, 정상 경로에서만 닫는다. 핸들러가 예외를 던지면 FastAPI 는 이 제너레이터의
    # yield 지점으로 예외를 되던진다(gen.athrow). try/finally 가 없으므로 아래 close() 에
    # 닿지 못하고, 세션은 커넥션을 쥔 채 버려진다. mixed 부하에 에러 요청을 5% 섞어 오래
    # 돌리면 풀이 서서히 고갈된다. fix 에서 try/finally(또는 `async with`)로 확실히 반환한다.
    #
    # measure 유의(verify-break §5):
    #   (i) 세션은 첫 SQL 전엔 커넥션이 없다 — 그래서 "DB 쿼리 이후에 나는 에러"만 누수를
    #       만든다. get_current_user 의 401 처럼 쿼리 전에 나는 에러는 안 샌다.
    #       k6 에러 유발 요청은 반드시 쿼리를 한 번 태운 뒤 실패하는 경로여야 한다.
    #   (ii) CPython refcount 가 버려진 세션을 회수하면 SQLAlchemy 가 non-checked-in 커넥션을
    #        terminate 시켜, "서서히 고갈" 대신 "경고 로그 + 커넥션 churn"으로 나타날 수 있다.
    #        재현이 약하면 §0-7 대로 조건 조정 과정을 로그에 남긴다.
    session = SessionFactory()
    yield session
    await session.close()
