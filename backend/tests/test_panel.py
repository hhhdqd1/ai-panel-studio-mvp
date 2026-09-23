from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.fake_gateway import FakeGateway
from app.main import create_app
from app.panel_service import PanelService


@pytest.mark.asyncio
async def test_panel_requires_exact_count(store):
    gateway = FakeGateway()
    gateway.panel = [gateway.panel[0]]
    discussion_id = await store.create_discussion("城市交通", 4)

    await PanelService(store, gateway).generate(discussion_id)

    snapshot = await store.get_snapshot(discussion_id)
    assert snapshot["status"] == "failed"
    assert snapshot["resume_point"] == "generating_panel"
    assert snapshot["agents"] == []
    assert snapshot["error_code"] == "invalid_panel"


@pytest.mark.asyncio
async def test_valid_panel_is_persisted_with_one_host_and_four_experts(store):
    gateway = FakeGateway()
    discussion_id = await store.create_discussion("城市交通", 4)

    await PanelService(store, gateway).generate(discussion_id)

    snapshot = await store.get_snapshot(discussion_id)
    assert snapshot["status"] == "awaiting_confirmation"
    assert len(snapshot["agents"]) == 5
    assert [agent["kind"] for agent in snapshot["agents"]].count("host") == 1
    assert snapshot["last_event_seq"] == 1
    assert snapshot["agents"][1]["name"] != snapshot["agents"][2]["name"]


@pytest.mark.asyncio
async def test_duplicate_panel_jobs_cannot_turn_ready_panel_into_failure(store):
    gateway = FakeGateway()
    discussion_id = await store.create_discussion("城市交通", 4)
    service = PanelService(store, gateway)

    await asyncio.gather(service.generate(discussion_id), service.generate(discussion_id))

    snapshot = await store.get_snapshot(discussion_id)
    assert snapshot["status"] == "awaiting_confirmation"
    assert len(snapshot["agents"]) == 5


@pytest.mark.asyncio
async def test_late_panel_failure_does_not_overwrite_ready_panel(store):
    gateway = FakeGateway()
    discussion_id = await store.create_discussion("城市交通", 4)
    await PanelService(store, gateway).generate(discussion_id)

    await store.fail(discussion_id, "model_timeout", "generating_panel")

    snapshot = await store.get_snapshot(discussion_id)
    assert snapshot["status"] == "awaiting_confirmation"
    assert snapshot["last_event_seq"] == 1


@pytest.mark.asyncio
async def test_failed_panel_can_resume_through_api(store):
    gateway = FakeGateway()
    good_panel = gateway.panel
    gateway.panel = good_panel[:1]
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/discussions", json={"topic": "城市交通"})
        discussion_id = created.json()["id"]
        for _ in range(100):
            snapshot = (await client.get(f"/api/discussions/{discussion_id}")).json()
            if snapshot["status"] == "failed":
                break
            await asyncio.sleep(0.01)
        assert snapshot["status"] == "failed"

        gateway.panel = good_panel
        resumed = await client.post(f"/api/discussions/{discussion_id}/resume")
        assert resumed.status_code == 202
        for _ in range(100):
            snapshot = (await client.get(f"/api/discussions/{discussion_id}")).json()
            if snapshot["status"] == "awaiting_confirmation":
                break
            await asyncio.sleep(0.01)
        assert snapshot["status"] == "awaiting_confirmation"
        assert len(snapshot["agents"]) == 5
