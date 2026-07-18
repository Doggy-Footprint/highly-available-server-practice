"""auth 도메인 로직 — 세션 발급/검증과 현재 사용자 의존성.

세션은 Redis 에 저장한다(P1-01 fix). 어떤 인스턴스가 로그인을 처리했든, 다른 인스턴스가
같은 Redis 를 보고 토큰을 검증할 수 있어 app 이 stateless 하다.
"""

from __future__ import annotations

import secrets

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import repository
from app.core.deps import get_db
from app.core.redis import get_redis
from app.models import User

_SESSION_KEY_PREFIX = "session:"
_SESSION_TTL_SECONDS = 60 * 60 * 24  # 24h


def hash_password(password: str) -> str:
    # bcrypt cost 12 (seed 와 동일). signup 도 이 블로킹 해싱을 타지만, 부하로 자극되는
    # 지점은 로그인 검증이다 (P1-10 은 login 에 표식).
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, pw_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), pw_hash.encode())


async def signup(session: AsyncSession, email: str, password: str) -> User:
    pw_hash = hash_password(password)
    return await repository.create_user(session, email, pw_hash)


async def login(session: AsyncSession, redis: Redis, email: str, password: str) -> str:
    user = await repository.get_user_by_email(session, email)
    # INTENDED-ISSUE: P1-10
    # cost 12 bcrypt 검증(~수백 ms, CPU 바운드)을 async 핸들러(이벤트 루프) 위에서 그대로
    # 돌린다. 로그인 100vu 스파이크면 루프가 그 시간만큼 막혀 무관한 GET /products 까지
    # 밀린다. (P1-06 은 I/O 블로킹, 이건 CPU 블로킹이라 대응이 다르다.)
    # fix 에서 run_in_executor/스레드풀로 오프로드한다 (또는 해싱 워커 분리).
    if user is None or not verify_password(password, user.pw_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = secrets.token_urlsafe(32)
    await redis.set(f"{_SESSION_KEY_PREFIX}{token}", user.id, ex=_SESSION_TTL_SECONDS)
    return token


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    token = authorization.removeprefix("Bearer ")
    user_id = await redis.get(f"{_SESSION_KEY_PREFIX}{token}")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown token")
    user = await repository.get_user(session, int(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown user")
    return user
