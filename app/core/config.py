"""애플리케이션 설정 — 전부 env 로 주입한다 (§10)."""

from __future__ import annotations

import socket
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "flashmart"

    # 어느 인스턴스가 응답했는지 식별한다. P1-01(세션이 프로세스에 갇힘)과
    # P2-08(인스턴스 kill) 재현에서 확인하는 용도.
    # --scale app=N 은 모든 replica 에 같은 env 를 주므로, 기본값은 컨테이너 hostname 이다.
    instance_id: str = Field(default_factory=socket.gethostname)

    database_url: str = "postgresql+asyncpg://flashmart:flashmart@db:5432/flashmart"
    db_echo: bool = False

    # Phase 1 에서 세션·캐시로 도입한다. Phase 0 코드는 아직 사용하지 않는다.
    redis_url: str = "redis://redis:6379/0"

    mockpg_url: str = "http://mockpg:8000"

    log_level: str = "info"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
