"""auth 도메인 로직 — 세션 발급/검증과 현재 사용자 의존성.

P1-01(프로세스 내 세션 저장)의 소재인 `_SESSIONS` dict 가 여기 있다. 세션 저장소와
그것을 읽는 `get_current_user` 를 한곳에 두어, 무엇이 심긴 문제인지 눈에 보이게 한다.
"""

from __future__ import annotations

import secrets

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import repository
from app.core.deps import get_db
from app.models import User

# INTENDED-ISSUE: P1-01
# 로그인 세션을 프로세스 메모리(dict)에 담는다. 이 프로세스가 발급한 토큰은 다른
# 인스턴스/워커의 dict 엔 존재하지 않는다. app 을 여러 대로 띄우거나 uvicorn 워커를
# 늘리면, 로그인한 인스턴스가 아닌 곳으로 라우팅된 /auth/me 가 랜덤하게 401 을 낸다.
# fix 에서 Redis 세션(또는 JWT)으로 옮겨 stateless 화한다.
_SESSIONS: dict[str, int] = {}


def hash_password(password: str) -> str:
    # bcrypt cost 12 (seed 와 동일). signup 도 이 블로킹 해싱을 타지만, 부하로 자극되는
    # 지점은 로그인 검증이다 (P1-10 은 login 에 표식).
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, pw_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), pw_hash.encode())


async def signup(session: AsyncSession, email: str, password: str) -> User:
    pw_hash = hash_password(password)
    return await repository.create_user(session, email, pw_hash)


async def login(session: AsyncSession, email: str, password: str) -> str:
    user = await repository.get_user_by_email(session, email)
    # INTENDED-ISSUE: P1-10
    # cost 12 bcrypt 검증(~수백 ms, CPU 바운드)을 async 핸들러(이벤트 루프) 위에서 그대로
    # 돌린다. 로그인 100vu 스파이크면 루프가 그 시간만큼 막혀 무관한 GET /products 까지
    # 밀린다. (P1-06 은 I/O 블로킹, 이건 CPU 블로킹이라 대응이 다르다.)
    # fix 에서 run_in_executor/스레드풀로 오프로드한다 (또는 해싱 워커 분리).
    if user is None or not verify_password(password, user.pw_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = user.id  # P1-01: 이 프로세스에만 저장된다
    return token


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    token = authorization.removeprefix("Bearer ")
    # P1-01: 다른 인스턴스가 발급한 토큰이면 이 dict 엔 없어 None → 401.
    user_id = _SESSIONS.get(token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown token")
    user = await repository.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown user")
    return user
