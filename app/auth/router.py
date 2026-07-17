"""auth 라우터 — signup / login / me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import schemas, service
from app.core.config import get_settings
from app.core.deps import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
_settings = get_settings()


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=schemas.MeResponse)
async def signup(
    body: schemas.SignupRequest, session: AsyncSession = Depends(get_db)
) -> schemas.MeResponse:
    user = await service.signup(session, body.email, body.password)
    return schemas.MeResponse(
        id=user.id, email=user.email, created_at=user.created_at, instance_id=_settings.instance_id
    )


@router.post("/login", response_model=schemas.TokenResponse)
async def login(
    body: schemas.LoginRequest, session: AsyncSession = Depends(get_db)
) -> schemas.TokenResponse:
    token = await service.login(session, body.email, body.password)
    return schemas.TokenResponse(token=token, instance_id=_settings.instance_id)


@router.get("/me", response_model=schemas.MeResponse)
async def me(user: User = Depends(service.get_current_user)) -> schemas.MeResponse:
    return schemas.MeResponse(
        id=user.id, email=user.email, created_at=user.created_at, instance_id=_settings.instance_id
    )
