"""FlashMart API 진입점.

Phase 0 기능 라우터(auth/products/deals/cart/orders)를 §14-4 에서 붙였다.
심은 문제 위치는 각 모듈 주석(`INTENDED-ISSUE`)에 있다 — `grep -rn INTENDED-ISSUE app` 로 조회.

헬스체크 엔드포인트와 graceful shutdown 은 일부러 없다 — P2-08 의 소재이므로
해당 이슈의 fix 에서 nginx health check 와 함께 도입한다. 아래 `GET /` 는
기동 확인용이고 로드밸런서가 참조하지 않는다.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.cart.router import router as cart_router
from app.core.config import get_settings
from app.core.metrics import setup_metrics
from app.deals.router import router as deals_router
from app.orders.router import rankings_router
from app.orders.router import router as orders_router
from app.products.router import main_router
from app.products.router import router as products_router

settings = get_settings()

app = FastAPI(title="FlashMart", version="0.0.0")

setup_metrics(app)

app.include_router(auth_router)
app.include_router(products_router)
app.include_router(main_router)
app.include_router(deals_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(rankings_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"app": settings.app_name, "instance": settings.instance_id}
