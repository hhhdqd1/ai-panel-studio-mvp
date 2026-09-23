from __future__ import annotations

import asyncio
from time import monotonic

import pytest
from httpx import ASGITransport, AsyncClient

from app.fake_gateway import FakeGateway
from app.main import create_app
from app.orchestrator import speech_is_short
from app.panel_service import PanelService


async def ready_discussion(store, topic: str, gateway: FakeGateway) -> str:
    discussion_id = await store.create_discussion(topic, 4)
    await PanelService(store, gateway).generate(discussion_id)
    return discussion_id


async def wait_for_terminal(store, discussion_id: str) -> dict:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        snapshot = await store.get_snapshot(discussion_id)
        if snapshot["status"] in {"completed", "failed"}:
            return snapshot
        await asyncio.sleep(0.02)
    raise AssertionError("discussion did not reach a terminal state within 10 seconds")


@pytest.mark.asyncio
async def test_start_is_idempotent_conflict(store):
    gateway = FakeGateway()
    discussion_id = await ready_discussion(store, "教育评价", gateway)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(f"/api/discussions/{discussion_id}/start")
        second = await client.post(f"/api/discussions/{discussion_id}/start")
    assert first.status_code == 202
    assert second.status_code == 409
    assert (await wait_for_terminal(store, discussion_id))["status"] == "completed"


@pytest.mark.asyncio
async def test_discussion_has_host_nonfixed_experts_and_natural_summary(store):
    gateway = FakeGateway()
    discussion_id = await ready_discussion(store, "教育评价", gateway)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        started = await client.post(f"/api/discussions/{discussion_id}/start")
        assert started.status_code == 202
        snapshot = await wait_for_terminal(store, discussion_id)

    messages = snapshot["messages"]
    host_id = next(agent["id"] for agent in snapshot["agents"] if agent["kind"] == "host")
    expert_messages = [message for message in messages if message["agent_id"] != host_id]
    assert snapshot["status"] == "completed"
    assert messages[0]["agent_id"] == host_id
    assert 12 <= len(expert_messages) <= 16
    assert len({message["agent_id"] for message in expert_messages}) >= 2
    assert [message["sequence"] for message in messages] == list(range(1, len(messages) + 1))
    assert all(speech_is_short(message["content"]) for message in expert_messages)
    assert isinstance(snapshot["summary"], str) and "教育评价" in snapshot["summary"]
    assert snapshot["expert_turns"] == len(expert_messages)
    assert snapshot["last_event_seq"] > len(messages)


def test_speech_length_contract_is_one_or_two_short_sentences():
    assert speech_is_short("先做小范围试点。")
    assert speech_is_short("先做小范围试点。再跟踪长期效果。")
    assert not speech_is_short("先试点。再评估。最后推广。")
    assert not speech_is_short("")
