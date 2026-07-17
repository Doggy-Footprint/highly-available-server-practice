"""Redis 클라이언트.

Phase 0 코드는 Redis 를 쓰지 않는다 — 세션은 프로세스 안에 있고(P1-01), 캐시도 없다.
Phase 1 에서 세션·캐시가, Phase 2 에서 딜 선점·Streams 큐가 여기로 들어온다.

Redis 는 이 프로젝트에서 곧 단일 장애점이 된다 (P2-13). 그래서 클라이언트를
만들 때부터 timeout 을 명시한다 — 무한 대기는 장애 주입 실험을 관찰 불가능하게 만든다.
"""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=1.0,
        socket_connect_timeout=1.0,
    )
