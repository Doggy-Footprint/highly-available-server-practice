"""async 엔진 / 세션 팩토리."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()

# INTENDED-ISSUE: P1-09
# 커넥션 풀을 튜닝하지 않고 SQLAlchemy 기본값(pool_size=5, max_overflow=10)에 맡긴다.
# 인스턴스·워커 수를 늘릴 때 총 커넥션이 PG max_connections 를 넘기거나,
# 반대로 풀이 좁아 대기가 쌓이는지를 P1-09 에서 직접 계산·측정한 뒤 조정한다.
engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    echo=_settings.db_echo,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
