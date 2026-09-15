from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator, metrics

LATENCY_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.075,            # 정상 응답 구간
    0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75,  # 관문 경계(0.3) 주변을 촘촘히
    1.0, 1.5, 2.0, 3.0, 5.0, 10.0,              # 터진 구간
    float("inf"),
)
# fmt: on


def setup_metrics(app: FastAPI) -> None:
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=False,
        should_group_untemplated=True,
        excluded_handlers=["/metrics"],
    )

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
