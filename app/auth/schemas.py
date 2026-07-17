"""auth 요청/응답 스키마."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str
    # 어느 인스턴스가 이 토큰을 발급했는지. P1-01(세션이 프로세스에 갇힘) 관찰용 —
    # /auth/me 를 때린 인스턴스가 여기와 다르면 401 이 난다.
    instance_id: str


class MeResponse(BaseModel):
    id: int
    email: str
    created_at: datetime
    instance_id: str
