from __future__ import annotations

import asyncio
from time import monotonic

import pytest
from httpx import ASGITransport, AsyncClient

from app.fake_gateway import FakeGateway
from app.main import create_app
from app.model_gateway import ModelRequestError
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


@pytest.mark.asyncio
async def test_fake_gateway_speech_remains_short_with_question_topic():
    gateway = FakeGateway()
    agent = {"name": "周雅宁"}
    context = {
        "discussion_id": "demo", "topic": "中小学是否应该引入 AI 个性化学习助手？",
        "stage": "exploration", "expert_turns": 0,
    }
    speech = await gateway.generate_speech(agent, context, {})
    assert speech_is_short(speech)


@pytest.mark.asyncio
async def test_fake_gateway_uses_seeded_expert_stances():
    gateway = FakeGateway()
    context = {
        "discussion_id": "demo", "topic": "AI 与教育？",
        "stage": "exploration", "expert_turns": 0,
    }
    supportive = await gateway.generate_speech(
        {"name": "支持者", "stance": "主张小范围试点"}, context, {}
    )
    cautious = await gateway.generate_speech(
        {"name": "审慎者", "stance": "担忧依赖风险"}, context, {}
    )
    assert "支持先做小范围试点" in supportive
    assert "成本与风险" in cautious
    assert speech_is_short(supportive) and speech_is_short(cautious)


@pytest.mark.asyncio
async def test_experts_publicly_raise_hands_before_speaking(store):
    gateway = FakeGateway()
    discussion_id = await ready_discussion(store, "教育评价", gateway)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        assert (await wait_for_terminal(store, discussion_id))["status"] == "completed"
    events = await store.events_after(discussion_id, 0)
    statuses = [
        event["payload"]["agent"]["public_status"]
        for event in events if event["type"] == "agent.updated"
    ]
    assert "raised" in statuses
    assert "speaking" in statuses
    assert statuses.index("raised") < statuses.index("speaking")


@pytest.mark.asyncio
async def test_six_experts_complete_before_model_call_limit(store):
    gateway = FakeGateway()
    discussion_id = await store.create_discussion("教育评价", 6)
    await PanelService(store, gateway).generate(discussion_id)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        snapshot = await wait_for_terminal(store, discussion_id)

    assert snapshot["status"] == "completed"
    assert 10 <= snapshot["expert_turns"] <= 12
    assert await store.count_model_runs(discussion_id) <= 100


class AllIntentsFailGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.fail_intents = True

    async def propose_intent(self, agent: dict, context: dict) -> dict:
        if self.fail_intents:
            raise ModelRequestError("model_timeout")
        return await super().propose_intent(agent, context)


class AllIntentsDeclineGateway(FakeGateway):
    async def propose_intent(self, agent: dict, context: dict) -> dict:
        return {"agent_id": agent["id"], "wants_to_speak": False}


@pytest.mark.asyncio
async def test_two_rounds_of_all_intent_errors_pause_instead_of_completing(store):
    gateway = AllIntentsFailGateway()
    discussion_id = await ready_discussion(store, "教育评价", gateway)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        snapshot = await wait_for_terminal(store, discussion_id)
    assert snapshot["status"] == "failed"
    assert snapshot["error_code"] == "all_intents_failed"
    assert snapshot["resume_point"] == "running"
    assert snapshot["expert_turns"] == 0
    gateway.fail_intents = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/resume")).status_code == 202
        assert (await wait_for_terminal(store, discussion_id))["status"] == "completed"


class SummaryFailsOnceGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def summarize(self, context: dict) -> str:
        if not self.failed:
            self.failed = True
            raise ModelRequestError("model_timeout")
        return await super().summarize(context)


class SummaryAlwaysFailsGateway(FakeGateway):
    async def summarize(self, context: dict) -> str:
        raise ModelRequestError("model_timeout")


@pytest.mark.asyncio
async def test_six_expert_summary_can_resume_within_budget(store):
    gateway = SummaryFailsOnceGateway()
    discussion_id = await store.create_discussion("教育评价", 6)
    await PanelService(store, gateway).generate(discussion_id)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        failed = await wait_for_terminal(store, discussion_id)
        assert failed["status"] == "failed"
        assert failed["resume_point"] == "summarizing"
        assert (await client.post(f"/api/discussions/{discussion_id}/resume")).status_code == 202
        completed = await wait_for_terminal(store, discussion_id)
    assert completed["status"] == "completed"
    assert await store.count_model_runs(discussion_id) <= 100


@pytest.mark.asyncio
async def test_exhausted_summary_budget_is_explicitly_not_resumable(store):
    gateway = SummaryAlwaysFailsGateway()
    discussion_id = await store.create_discussion("教育评价", 6)
    await PanelService(store, gateway).generate(discussion_id)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        snapshot = await wait_for_terminal(store, discussion_id)
        for _ in range(10):
            if snapshot["error_code"] == "model_call_limit":
                break
            assert (await client.post(f"/api/discussions/{discussion_id}/resume")).status_code == 202
            snapshot = await wait_for_terminal(store, discussion_id)
        assert snapshot["status"] == "failed"
        assert snapshot["error_code"] == "model_call_limit"
        used = await store.count_model_runs(discussion_id)
        assert used == 100
        assert (await client.post(f"/api/discussions/{discussion_id}/resume")).status_code == 409
        assert await store.count_model_runs(discussion_id) == used


@pytest.mark.asyncio
async def test_persistent_all_intent_failures_never_look_completed(store):
    gateway = AllIntentsFailGateway()
    discussion_id = await store.create_discussion("教育评价", 6)
    await PanelService(store, gateway).generate(discussion_id)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        snapshot = await wait_for_terminal(store, discussion_id)
        for _ in range(10):
            assert snapshot["status"] == "failed"
            assert snapshot["expert_turns"] == 0
            if snapshot["error_code"] == "model_call_limit":
                break
            response = await client.post(f"/api/discussions/{discussion_id}/resume")
            if response.status_code == 409:
                snapshot = await store.get_snapshot(discussion_id)
                break
            assert response.status_code == 202
            snapshot = await wait_for_terminal(store, discussion_id)
        assert snapshot["error_code"] == "model_call_limit"
        assert (await client.post(f"/api/discussions/{discussion_id}/resume")).status_code == 409
        assert await store.count_model_runs(discussion_id) <= 100


@pytest.mark.asyncio
async def test_two_rounds_of_valid_declines_can_finish_normally(store):
    gateway = AllIntentsDeclineGateway()
    discussion_id = await ready_discussion(store, "教育评价", gateway)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        snapshot = await wait_for_terminal(store, discussion_id)
    assert snapshot["status"] == "completed"
    assert snapshot["expert_turns"] == 0
