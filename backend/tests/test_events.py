from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.events import event_frames, parse_after, sse_frame
from app.fake_gateway import FakeGateway
from app.main import create_app
from app.panel_service import PanelService
import app.store as store_module


async def connected() -> bool:
    return False


@pytest.mark.asyncio
async def test_replay_is_scoped_and_ordered(store):
    first = await store.create_discussion("教育", 4)
    second = await store.create_discussion("交通", 4)
    await store.append_event(first, "discussion.status", {"status": "running"})
    await store.append_event(first, "message.created", {"id": "m1"})
    await store.append_event(second, "discussion.status", {"status": "running"})

    replay = await store.events_after(first, 1)

    assert [(event["sequence"], event["type"]) for event in replay] == [(2, "message.created")]
    assert (await store.get_snapshot(first))["last_event_seq"] == 2
    assert (await store.get_snapshot(second))["last_event_seq"] == 1


def test_sse_frame_has_id_event_and_json_data():
    frame = sse_frame({"sequence": 7, "type": "message.created", "payload": {"text": "中文"}})
    assert frame.startswith("id: 7\nevent: message.created\n")
    assert json.loads(frame.split("data: ", 1)[1].strip()) == {"text": "中文"}


def test_last_event_id_takes_precedence_and_bad_values_reject():
    assert parse_after("4", "2") == 4
    assert parse_after(None, "2") == 2
    assert parse_after(None, None) == 0
    with pytest.raises(ValueError):
        parse_after("abc", "2")
    with pytest.raises(ValueError):
        parse_after(None, "-1")


@pytest.mark.asyncio
async def test_replay_does_not_call_model_again(store):
    gateway = FakeGateway()
    discussion_id = await store.create_discussion("教育", 4)
    await store.append_event(discussion_id, "discussion.status", {"status": "running"})
    before = len(gateway.calls)

    frames = event_frames(store, discussion_id, 0, connected)
    frame = await anext(frames)
    await frames.aclose()

    assert "id: 1" in frame
    assert len(gateway.calls) == before


@pytest.mark.asyncio
async def test_newly_committed_event_wakes_stream(store):
    discussion_id = await store.create_discussion("教育", 4)
    frames = event_frames(store, discussion_id, 0, connected)
    waiting = asyncio.create_task(anext(frames))
    await asyncio.sleep(0.01)
    await store.append_event(discussion_id, "discussion.status", {"status": "running"})
    frame = await asyncio.wait_for(waiting, timeout=2)
    await frames.aclose()
    assert "id: 1" in frame


@pytest.mark.asyncio
async def test_invalid_resume_id_returns_422_before_opening_stream(store):
    discussion_id = await store.create_discussion("教育", 4)
    app = create_app(store=store, gateway=FakeGateway())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/discussions/{discussion_id}/events?after=1",
            headers={"Last-Event-ID": "not-an-integer"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_snapshot_and_event_cursor_share_one_database_version(store, monkeypatch):
    discussion_id = await store.create_discussion("教育", 2)
    await PanelService(store, FakeGateway()).generate(discussion_id)
    host_id = (await store.get_snapshot(discussion_id))["agents"][0]["id"]
    original_connect = store_module.connect_db
    interrupted = False

    class InterruptedRead:
        def __init__(self, connection):
            self.connection = connection

        async def execute(self, sql, parameters=()):
            nonlocal interrupted
            if sql.startswith("SELECT * FROM agent") and not interrupted:
                interrupted = True
                await store.append_message(discussion_id, host_id, "opening", "并发写入的开场白。")
            return await self.connection.execute(sql, parameters)

        def __getattr__(self, name):
            return getattr(self.connection, name)

    async def intercept_once(path):
        connection = await original_connect(path)
        if not interrupted:
            return InterruptedRead(connection)
        return connection

    monkeypatch.setattr(store_module, "connect_db", intercept_once)
    snapshot = await store.get_snapshot(discussion_id)
    replay = await store.events_after(discussion_id, snapshot["last_event_seq"])

    assert interrupted
    assert snapshot["last_event_seq"] == 1
    assert snapshot["messages"] == []
    assert [(event["sequence"], event["type"]) for event in replay] == [(2, "message.created")]
    assert len((await store.get_snapshot(discussion_id))["messages"]) == 1
