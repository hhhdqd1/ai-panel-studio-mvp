from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import init_db
from app.main import create_app
from app.store import Store


@dataclass
class SpyGateway:
    calls: list[dict] = field(default_factory=list)


@pytest.fixture
def fake_gateway() -> SpyGateway:
    return SpyGateway()


@pytest.fixture
async def store(tmp_path) -> Store:
    db_path = tmp_path / "panel-test.sqlite3"
    await init_db(db_path)
    return Store(db_path)


@pytest.fixture
async def client(store: Store, fake_gateway: SpyGateway):
    app = create_app(store=store, gateway=fake_gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
