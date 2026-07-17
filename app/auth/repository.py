"""auth 데이터 접근."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    # email 에 인덱스가 없어 5만 행 seq scan 이 된다 (models.py P1-03 주석 참고).
    # 로그인 경로의 naive 비용 — 별도 이슈로 표식하진 않는다(스키마 쪽 P1-03 의 일부).
    stmt = select(User).where(User.email == email)
    return (await session.scalars(stmt)).first()


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def create_user(session: AsyncSession, email: str, pw_hash: str) -> User:
    user = User(email=email, pw_hash=pw_hash)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
