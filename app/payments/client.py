"""외부 결제(mockpg) 호출.

여기에 P1-06(동기 호출)과 P2-07(무한 재시도)이 심겨 있다. 이 함수는 async 가 아니라
일부러 동기 함수다 — orders 서비스(async)가 `await` 없이 직접 부르면 이벤트 루프가 막힌다.
"""

from __future__ import annotations

import requests

from app.core.config import get_settings


def pay(order_id: int, amount: float) -> dict[str, str]:
    settings = get_settings()
    url = f"{settings.mockpg_url}/pay"
    payload = {"order_id": order_id, "amount": amount}

    # INTENDED-ISSUE: P1-06
    # 동기 requests 로 외부 결제를 호출한다. async 핸들러 안에서 이 함수가 도는 동안
    # 이벤트 루프 전체가 멈춘다 — mockpg LATENCY_MS=800 이면 무관한 GET /products 까지
    # 800ms 밀린다. fix 에서 httpx.AsyncClient 로 옮기며 requests 의존성을 제거한다.
    #
    # INTENDED-ISSUE: P2-07
    # 실패(502)면 백오프도, 시도 상한도, timeout 도 없이 즉시 다시 던진다. mockpg
    # FAIL_RATE 를 높이면 재시도가 겹쳐 유효 QPS 가 폭증, 결제 경로가 스스로 과부하된다.
    # fix 에서 timeout + 지수 백오프 + 시도 상한 + 서킷 브레이커.
    while True:
        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            return {"status": str(data["status"]), "pg_tx_id": str(data["pg_tx_id"])}
        # 502 등 실패 → 즉시 재시도 (상한 없음)
