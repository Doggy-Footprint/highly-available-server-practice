"""Prometheus 계측 (§9)."""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator, metrics

# instrumentator 기본 버킷은 (0.1, 0.5, 1) 로 너무 성기다. 그 버킷으로는
# "p95 < 300ms" (Phase 1 관문) 를 판정할 수 없고, 160ms→1.9s 같은 전/후 비교도
# 0.5 와 1 사이 어딘가로 뭉개진다. 관문 경계(0.3)와 그 주변을 촘촘히 잡는다.
# fmt: off
LATENCY_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.075,            # 정상 응답 구간
    0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75,  # 관문 경계(0.3) 주변을 촘촘히
    1.0, 1.5, 2.0, 3.0, 5.0, 10.0,              # 터진 구간
    float("inf"),
)
# fmt: on


def setup_metrics(app: FastAPI) -> None:
    """`/metrics` 를 노출한다.

    카디널리티: `handler` 라벨은 반드시 라우트 템플릿(`/products/{id}`)이어야 한다.
    raw path 로 라벨링하면 상품 20만 개가 그대로 20만 시계열이 되어
    측정 대상보다 Prometheus 가 먼저 죽는다. instrumentator 는 기본적으로
    템플릿으로 라벨링하고, `should_group_untemplated` 로 매칭 실패 경로까지 묶는다.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=False,
        # 라우트에 매칭되지 않은 요청은 전부 하나로 묶는다 (스캐너·오타 경로 방어).
        should_group_untemplated=True,
        excluded_handlers=["/metrics"],
    )

    # add() 를 한 번이라도 호출하면 기본 메트릭 세트는 붙지 않는다.
    # 아래 둘이 표준 지표(TPS, p50/p95/p99, error rate)를 전부 커버한다.
    instrumentator.add(
        metrics.requests(
            metric_name="http_requests_total",
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    instrumentator.add(
        metrics.latency(
            metric_name="http_request_duration_seconds",
            should_include_handler=True,
            should_include_method=True,
            should_include_status=False,
            buckets=LATENCY_BUCKETS,
        )
    )

    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
