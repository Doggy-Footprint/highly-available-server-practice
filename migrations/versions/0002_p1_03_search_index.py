"""P1-03 fix: products 검색 인덱스 (btree category_id + pg_trgm GIN name/description)

측정(measure): app x3 + nginx, DB 2vCPU/4g, k6 p1-03.js target(50VU·3m) —
  http_req_duration p50=7.18s / p95=32.99s / p99=46.95s, TPS≈4.38/s.
  count_products(P1-05) 쿼리가 ILIKE 있을 때 카테고리만 필터할 때(~15ms)보다 ~10배(≈145ms,
  단일 실행 기준) 비싸짐 — 무인덱스 ILIKE 가 COUNT 경로를 통해서도 증폭됨을 확인
  (docs/experiments/P1-03.md 참고).

이 리비전은 `CREATE INDEX`(비-CONCURRENTLY)를 그대로 쓴다 — 무중단 인덱스 생성은
P2-15 의 소재이므로 여기서 미리 처리하지 않는다 (CLAUDE.md §0-1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-18

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
    op.create_index(
        "ix_products_name_trgm",
        "products",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_description_trgm",
        "products",
        ["description"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"description": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_products_description_trgm", table_name="products")
    op.drop_index("ix_products_name_trgm", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    # pg_trgm 은 다른 테이블에서도 공유될 수 있는 확장이라 downgrade 에서 DROP EXTENSION 하지 않는다.
