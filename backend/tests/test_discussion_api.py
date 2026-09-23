from __future__ import annotations

import sqlite3

import pytest

from app.fake_gateway import FakeGateway
from app.main import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"topic": "   ", "expert_count": 4},
        {"topic": "x" * 501, "expert_count": 4},
        {"topic": "教育公平", "expert_count": 1},
        {"topic": "教育公平", "expert_count": 7},
    ],
)
async def test_create_rejects_invalid_input(client, fake_gateway, body):
    response = await client.post("/api/discussions", json=body)
    assert response.status_code == 422
    assert fake_gateway.calls == []


@pytest.mark.asyncio
async def test_create_normalizes_topic_and_defaults_to_four_experts(client):
    created = await client.post("/api/discussions", json={"topic": "  AI 与教育  "})
    assert created.status_code == 201
    assert created.json()["status"] == "generating_panel"
    discussion_id = created.json()["id"]

    listed = await client.get("/api/discussions")
    assert listed.status_code == 200
    assert listed.json()[0]["topic"] == "AI 与教育"
    assert listed.json()[0]["expert_count"] == 4

    detail = await client.get(f"/api/discussions/{discussion_id}")
    assert detail.status_code == 200
    assert detail.json()["topic"] == "AI 与教育"
    assert detail.json()["agents"] == []
    assert detail.json()["messages"] == []
    assert detail.json()["last_event_seq"] == 0


@pytest.mark.asyncio
async def test_unknown_discussion_returns_404(client):
    response = await client.get("/api/discussions/no-such-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_database_has_required_tables_and_wal(store):
    with sqlite3.connect(store.db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert {"discussion", "agent", "message", "event", "insight", "model_run"} <= tables
    assert journal_mode == "wal"


def test_explicit_fake_mode_never_uses_environment_deepseek_key(store, monkeypatch):
    monkeypatch.setenv("APP_FAKE_MODEL", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "do-not-use-this-test-key")
    app = create_app(store=store)
    assert isinstance(app.state.gateway, FakeGateway)
