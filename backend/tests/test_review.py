from __future__ import annotations

import asyncio
import sqlite3
from time import monotonic

import pytest
from httpx import ASGITransport, AsyncClient

from app.fake_gateway import FakeGateway
from app.main import create_app
from app.panel_service import PanelService
from app.review import merge_insight, sanitize_review


def empty_review(flags: list[dict] | None = None) -> dict:
    return {"consensus": [], "disagreements": [], "open_questions": [], "claim_flags": flags or []}


def test_review_keeps_only_sourced_items():
    raw = {
        "consensus": [
            {"text": "同意先试点", "message_ids": ["m1", "m2"]},
            {"text": "不存在的共识", "message_ids": ["missing"]},
        ],
        "disagreements": [],
        "open_questions": [],
        "claim_flags": [
            {"message_id": "m2", "quote": "增长 83%", "reason_code": "needs_external_check", "explanation": "未给出来源", "status": "open"}
        ],
    }
    result = sanitize_review(raw, {"m1", "m2"})
    assert len(result["consensus"]) == 1
    assert result["claim_flags"][0]["status"] == "open"


def test_opinion_is_not_a_claim_flag():
    result = sanitize_review(
        empty_review(
            [{"message_id": "m1", "quote": "我认为这样更公平", "reason_code": "needs_external_check", "explanation": "意见", "status": "open"}]
        ),
        {"m1"},
    )
    assert result["claim_flags"] == []


def test_numeric_claim_fake_citation_and_record_conflict_are_retained():
    flags = [
        {"message_id": "m1", "quote": "增长 83%", "reason_code": "needs_external_check", "explanation": "数字无来源", "status": "open"},
        {"message_id": "m2", "quote": "《虚构研究》指出", "reason_code": "unsupported_source", "explanation": "研究无法追溯", "status": "open"},
        {"message_id": "m3", "quote": "试点已经覆盖全市", "reason_code": "record_conflict", "conflicts_with_message_id": "m1", "explanation": "与先前仅两个区的描述冲突", "status": "open"},
    ]
    result = sanitize_review(empty_review(flags), {"m1", "m2", "m3"})
    assert [flag["reason_code"] for flag in result["claim_flags"]] == [
        "needs_external_check", "unsupported_source", "record_conflict"
    ]


def test_duplicate_untraceable_and_verified_flags_are_dropped():
    valid = {"message_id": "m1", "quote": "增长 83%", "reason_code": "needs_external_check", "explanation": "数字无来源", "status": "open"}
    result = sanitize_review(
        empty_review(
            [
                valid, valid.copy(),
                {**valid, "message_id": "missing"},
                {**valid, "status": "verified"},
                {**valid, "quote": "并未出现在原文的 99%"},
                {**valid, "reason_code": "record_conflict", "conflicts_with_message_id": "missing"},
            ]
        ),
        {"m1"},
        {"m1": "报告声称增长 83%，但没有附上数据来源。"},
    )
    assert len(result["claim_flags"]) == 1
    assert result["claim_flags"][0]["quote"] == "增长 83%"


def test_new_review_keeps_unresolved_old_flag():
    old = empty_review(
        [{"message_id": "m1", "quote": "增长 83%", "reason_code": "needs_external_check", "explanation": "缺少来源", "status": "open"}]
    )
    merged = merge_insight(old, empty_review())
    assert merged["claim_flags"] == old["claim_flags"]


def test_new_review_does_not_erase_sourced_consensus_when_latest_round_is_silent():
    old = empty_review()
    old["consensus"] = [{"text": "先小范围试点", "message_ids": ["m1", "m2"]}]
    merged = merge_insight(old, empty_review())
    assert merged["consensus"] == old["consensus"]


class ReviewFailsOnceGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def review(self, context: dict, message: dict) -> dict:
        if not self.failed:
            self.failed = True
            raise RuntimeError("review unavailable")
        return await super().review(context, message)


async def run_complete(store, gateway: FakeGateway) -> dict:
    discussion_id = await store.create_discussion("教育评价", 4)
    await PanelService(store, gateway).generate(discussion_id)
    app = create_app(store=store, gateway=gateway)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/discussions/{discussion_id}/start")).status_code == 202
        deadline = monotonic() + 10
        while monotonic() < deadline:
            snapshot = await store.get_snapshot(discussion_id)
            if snapshot["status"] in {"completed", "failed"}:
                return snapshot
            await asyncio.sleep(0.02)
    raise AssertionError("discussion did not finish")


@pytest.mark.asyncio
async def test_each_expert_speech_is_reviewed_and_flags_link_to_messages(store):
    gateway = FakeGateway()
    snapshot = await run_complete(store, gateway)
    expert_ids = {agent["id"] for agent in snapshot["agents"] if agent["kind"] == "expert"}
    expert_messages = [message for message in snapshot["messages"] if message["agent_id"] in expert_ids]
    reviews = [call for call in gateway.calls if call["purpose"] == "review"]
    flags = snapshot["insight"]["claim_flags"]
    assert snapshot["status"] == "completed"
    assert len(reviews) == len(expert_messages)
    assert flags
    assert all(flag["message_id"] in {message["id"] for message in snapshot["messages"]} for flag in flags)
    assert all(flag["status"] in {"open", "clarified"} for flag in flags)
    assert "待核实" in snapshot["summary"]


@pytest.mark.asyncio
async def test_review_failure_emits_unavailable_but_discussion_completes(store):
    snapshot = await run_complete(store, ReviewFailsOnceGateway())
    assert snapshot["status"] == "completed"
    with sqlite3.connect(store.db_path) as connection:
        event_types = [row[0] for row in connection.execute(
            "SELECT type FROM event WHERE discussion_id = ? ORDER BY sequence", (snapshot["id"],)
        )]
    assert "insight.review_unavailable" in event_types
    assert "insight.updated" in event_types
