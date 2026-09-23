from __future__ import annotations

import asyncio
from time import monotonic

import pytest
from httpx import ASGITransport, AsyncClient

from app.fake_gateway import FakeGateway
from app.main import create_app
from app.model_gateway import ModelRequestError
from app.panel_service import PanelService


async def make_ready(store, gateway: FakeGateway, topic: str) -> str:
    discussion_id = await store.create_discussion(topic, 4)
    await PanelService(store, gateway).generate(discussion_id)
    return discussion_id


async def wait_for(store, discussion_id: str, status: str) -> dict:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        snapshot = await store.get_snapshot(discussion_id)
        if snapshot["status"] == status:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"discussion did not reach {status} within 10 seconds")


class FailAfterFirstExpertGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.fail_once = True

    async def generate_speech(self, agent: dict, context: dict, intent: dict) -> str:
        if context["expert_turns"] >= 1 and self.fail_once:
            self.fail_once = False
            raise ModelRequestError("model_timeout")
        return await super().generate_speech(agent, context, intent)


class FailSummaryOnceGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.fail_once = True

    async def summarize(self, context: dict) -> str:
        if self.fail_once:
            self.fail_once = False
            raise ModelRequestError("model_timeout")
        return await super().summarize(context)


class CountingPanelGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.max_active = 0

    async def generate_panel(self, topic: str, count: int) -> list[dict]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.04)
            return await super().generate_panel(topic, count)
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_two_discussions_do_not_share_messages_or_model_context(store):
    gateway = FakeGateway()
    first = await make_ready(store, gateway, "教育评价")
    second = await make_ready(store, gateway, "城市交通")
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            client.post(f"/api/discussions/{first}/start"),
            client.post(f"/api/discussions/{second}/start"),
        )
        assert [response.status_code for response in responses] == [202, 202]
        first_snapshot, second_snapshot = await asyncio.gather(
            wait_for(store, first, "completed"), wait_for(store, second, "completed")
        )

    for discussion_id, topic, other, snapshot in [
        (first, "教育评价", "城市交通", first_snapshot),
        (second, "城市交通", "教育评价", second_snapshot),
    ]:
        calls = [call for call in gateway.calls if call.get("discussion_id") == discussion_id]
        assert calls
        assert all(call["topic"] == topic for call in calls)
        assert all(other not in message["content"] for message in snapshot["messages"])
        assert all(message["agent_id"] in {agent["id"] for agent in snapshot["agents"]} for message in snapshot["messages"])


@pytest.mark.asyncio
async def test_panel_model_calls_obey_global_limit_of_four(store):
    gateway = CountingPanelGateway()
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            *(client.post("/api/discussions", json={"topic": f"议题{index}"}) for index in range(6))
        )
        ids = [response.json()["id"] for response in responses]
        await asyncio.gather(*(wait_for(store, discussion_id, "awaiting_confirmation") for discussion_id in ids))
    assert gateway.max_active <= 4


@pytest.mark.asyncio
async def test_resume_keeps_committed_messages_and_finishes(store):
    gateway = FailAfterFirstExpertGateway()
    discussion_id = await make_ready(store, gateway, "教育评价")
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        failed = await wait_for(store, discussion_id, "failed")
        before = failed["messages"]
        assert failed["resume_point"] == "running"
        assert len(before) >= 2

        resumed = await client.post(f"/api/discussions/{discussion_id}/resume")
        assert resumed.status_code == 202
        after = (await wait_for(store, discussion_id, "completed"))["messages"]

    assert [message["id"] for message in after[: len(before)]] == [message["id"] for message in before]
    assert len({message["sequence"] for message in after}) == len(after)
    assert len([message for message in after if message["content"].startswith("欢迎来到圆桌")]) == 1
    assert all(agent["public_status"] == "waiting" for agent in (await store.get_snapshot(discussion_id))["agents"])


@pytest.mark.asyncio
async def test_summary_resume_does_not_repeat_discussion(store):
    gateway = FailSummaryOnceGateway()
    discussion_id = await make_ready(store, gateway, "教育评价")
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(f"/api/discussions/{discussion_id}/start")
        failed = await wait_for(store, discussion_id, "failed")
        assert failed["resume_point"] == "summarizing"
        before_ids = [message["id"] for message in failed["messages"]]
        assert (await client.post(f"/api/discussions/{discussion_id}/resume")).status_code == 202
        completed = await wait_for(store, discussion_id, "completed")
    assert [message["id"] for message in completed["messages"]] == before_ids
    assert completed["summary"]


@pytest.mark.asyncio
async def test_restart_marks_incomplete_states_recoverable_without_touching_completed(store):
    gateway = FakeGateway()
    generating = await store.create_discussion("生成中", 4)
    running = await make_ready(store, gateway, "运行中")
    summarizing = await make_ready(store, gateway, "总结中")
    completed = await make_ready(store, gateway, "已完成")
    await store.transition(running, "awaiting_confirmation", "running", stage="exploration")
    await store.transition(summarizing, "awaiting_confirmation", "running", stage="closing")
    await store.transition(summarizing, "running", "summarizing", stage="closing")
    await store.transition(completed, "awaiting_confirmation", "running", stage="closing")
    await store.transition(completed, "running", "summarizing", stage="closing")
    await store.complete(completed, "已完成总结")

    changed = await store.mark_interrupted()

    assert changed == 3
    assert (await store.get_snapshot(generating))["resume_point"] == "generating_panel"
    assert (await store.get_snapshot(running))["resume_point"] == "running"
    assert (await store.get_snapshot(summarizing))["resume_point"] == "summarizing"
    assert (await store.get_snapshot(completed))["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_after_committed_closing_does_not_duplicate_host_message(store):
    gateway = FakeGateway()
    discussion_id = await make_ready(store, gateway, "教育评价")
    snapshot = await store.get_snapshot(discussion_id)
    host_id = next(agent["id"] for agent in snapshot["agents"] if agent["kind"] == "host")
    expert_id = next(agent["id"] for agent in snapshot["agents"] if agent["kind"] == "expert")
    await store.transition(discussion_id, "awaiting_confirmation", "running", stage="exploration")
    await store.append_message(discussion_id, host_id, "opening", "欢迎来到圆桌。")
    for index in range(12):
        await store.append_message(discussion_id, expert_id, "exploration", f"专家观点{index}。")
    await store.transition(discussion_id, "running", "running", stage="closing")
    await store.append_message(discussion_id, host_id, "closing", "本场讨论到此结束。")
    await store.fail(discussion_id, "interrupted", "running")

    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/resume")).status_code == 202
        completed = await wait_for(store, discussion_id, "completed")

    closings = [message for message in completed["messages"] if message["stage"] == "closing"]
    assert len(closings) == 1
