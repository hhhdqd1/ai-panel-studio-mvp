from __future__ import annotations

import pytest

from app.seeds import seed_examples


@pytest.mark.asyncio
async def test_seed_import_is_idempotent(store):
    assert await seed_examples(store) == 5
    assert await seed_examples(store) == 0
    rows = await store.list_discussions()
    assert len(rows) == 5
    assert all(row["status"] == "awaiting_confirmation" for row in rows)


@pytest.mark.asyncio
async def test_each_seed_has_distinct_host_and_four_experts(store):
    await seed_examples(store)
    rows = await store.list_discussions()
    assert len({row["topic"] for row in rows}) == 5
    for row in rows:
        snapshot = await store.get_snapshot(row["id"])
        assert snapshot is not None
        agents = snapshot["agents"]
        assert len(agents) == 5
        assert [agent["kind"] for agent in agents].count("host") == 1
        assert len({agent["name"] for agent in agents}) == 5
        assert snapshot["last_event_seq"] == 1


@pytest.mark.asyncio
async def test_seed_import_preserves_existing_discussions(store):
    existing_id = await store.create_discussion("用户自己的议题", 3)
    assert await seed_examples(store) == 5
    assert await seed_examples(store) == 0
    snapshot = await store.get_snapshot(existing_id)
    assert snapshot is not None
    assert snapshot["status"] == "generating_panel"
