from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db
from app.main import app

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://flashmart:flashmart@localhost:35432/flashmart",
)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    engine = create_async_engine(TEST_DB_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_cursor_sequential_traversal_no_dup_no_gap(client: httpx.AsyncClient) -> None:
    seen_ids: list[int] = []
    cursor: int | None = None
    size = 25

    for _ in range(4):
        params: dict[str, int] = {"size": size}
        if cursor is not None:
            params["cursor"] = cursor
        res = await client.get("/products", params=params)
        assert res.status_code == 200
        body = res.json()
        items = body["items"]
        assert len(items) == size
        ids = [item["id"] for item in items]
        assert ids == sorted(ids)
        if cursor is not None:
            assert ids[0] > cursor
        seen_ids.extend(ids)
        cursor = body["next_cursor"]
        assert cursor == ids[-1]

    assert len(seen_ids) == len(set(seen_ids))
    assert seen_ids == list(range(1, 4 * size + 1))


@pytest.mark.asyncio
async def test_cursor_exact_boundary_last_page_next_cursor_is_none(
    client: httpx.AsyncClient,
) -> None:
    # 마지막 20개 상품(199981..200000)을 size=20으로 딱 맞게 조회했을 때
    # 다음 행이 더 없으므로 next_cursor 는 반드시 None 이어야 한다.
    res = await client.get("/products", params={"cursor": 199980, "size": 20})
    assert res.status_code == 200
    body = res.json()
    items = body["items"]
    assert len(items) == 20
    assert items[0]["id"] == 199981
    assert items[-1]["id"] == 200000
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_cursor_combined_with_category_and_query_filter(
    client: httpx.AsyncClient,
) -> None:
    res1 = await client.get("/products", params={"category": 1, "q": "이어폰", "size": 10})
    assert res1.status_code == 200
    body1 = res1.json()
    items1 = body1["items"]
    assert len(items1) == 10
    assert all(item["category_id"] == 1 for item in items1)
    next_cursor = body1["next_cursor"]
    assert next_cursor == items1[-1]["id"]

    res2 = await client.get(
        "/products",
        params={"category": 1, "q": "이어폰", "cursor": next_cursor, "size": 10},
    )
    assert res2.status_code == 200
    body2 = res2.json()
    items2 = body2["items"]
    assert len(items2) > 0
    assert all(item["category_id"] == 1 for item in items2)
    assert all(item["id"] > next_cursor for item in items2)


@pytest.mark.asyncio
async def test_cursor_beyond_max_id_returns_empty(client: httpx.AsyncClient) -> None:
    res = await client.get("/products", params={"cursor": 999_999_999, "size": 20})
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_cursor", [0, -1, -999])
async def test_invalid_cursor_rejected_with_422(
    client: httpx.AsyncClient, invalid_cursor: int
) -> None:
    res = await client.get("/products", params={"cursor": invalid_cursor, "size": 20})
    assert res.status_code == 422
