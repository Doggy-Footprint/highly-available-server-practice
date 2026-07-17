"""FlashMart API 진입점.

Phase 0 기능 라우터(auth/products/deals/cart/orders/payments)는 §14-4 에서 붙인다.
지금은 스캐폴딩이 실제로 기동하고 리소스 제한이 걸리는지 확인할 수 있는 최소 형태다.

헬스체크 엔드포인트와 graceful shutdown 은 일부러 없다 — P2-08 의 소재이므로
해당 이슈의 fix 에서 nginx health check 와 함께 도입한다. 아래 `GET /` 는
기동 확인용이고 로드밸런서가 참조하지 않는다.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.metrics import setup_metrics

settings = get_settings()

app = FastAPI(title="FlashMart", version="0.0.0")

setup_metrics(app)


@app.get("/")
async def root() -> dict[str, str]:
    return {"app": settings.app_name, "instance": settings.instance_id}
