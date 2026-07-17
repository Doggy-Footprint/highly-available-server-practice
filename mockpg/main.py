"""외부 결제 PG mock — 지연·실패를 env 로 주입한다.

    LATENCY_MS  응답 전 인위적 지연 (기본 0)
    FAIL_RATE   0.0~1.0, 502 로 실패시킬 비율 (기본 0)

FlashMart 본체와 완전히 분리된 초경량 앱이다. 실험 대상이 아니므로
여기에는 의도된 문제를 심지 않는다 — 이 앱은 "장애를 내는 쪽"이지 "터지는 쪽"이 아니다.

    P1-06  LATENCY_MS=800 → 앱의 동기 호출이 이벤트 루프를 막는지 관찰
    P1-07  지연 상태에서 트랜잭션이 결제 응답을 기다리며 커넥션을 붙잡는지 관찰
    P2-07  FAIL_RATE=0.5 → 재시도 폭풍 관찰
"""

from __future__ import annotations

import asyncio
import os
import random
import uuid
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="mockpg", version="0.0.0")


def _latency_ms() -> int:
    return int(os.getenv("LATENCY_MS", "0"))


def _fail_rate() -> float:
    return float(os.getenv("FAIL_RATE", "0"))


class PayRequest(BaseModel):
    order_id: int
    amount: float


class PayResponse(BaseModel):
    status: Literal["PAID"]
    pg_tx_id: str


# 성공(PayResponse)과 주입된 실패(JSONResponse 502)를 함께 반환하므로
# 반환 타입에서 응답 모델을 유추하지 못한다. 명시적으로 끈다.
@app.post("/pay", response_model=None)
async def pay(req: PayRequest) -> PayResponse | JSONResponse:
    latency = _latency_ms()
    if latency > 0:
        await asyncio.sleep(latency / 1000)

    if random.random() < _fail_rate():
        return JSONResponse(
            status_code=502,
            content={"status": "FAILED", "reason": "injected failure"},
        )

    return PayResponse(status="PAID", pg_tx_id=uuid.uuid4().hex)


@app.get("/config")
async def config() -> dict[str, float | int]:
    """현재 주입 설정 확인용. 실험 로그에 재현 조건으로 남긴다."""
    return {"latency_ms": _latency_ms(), "fail_rate": _fail_rate()}
