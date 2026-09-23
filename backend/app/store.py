from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.db import connect_db


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_insight() -> dict:
    return {
        "consensus": [],
        "disagreements": [],
        "open_questions": [],
        "claim_flags": [],
    }


class Store:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    async def create_discussion(self, topic: str, expert_count: int) -> str:
        discussion_id = str(uuid4())
        now = utc_now()
        connection = await connect_db(self.db_path)
        try:
            await connection.execute(
                """INSERT INTO discussion
                   (id, topic, expert_count, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'generating_panel', ?, ?)""",
                (discussion_id, topic, expert_count, now, now),
            )
            await connection.commit()
        finally:
            await connection.close()
        return discussion_id

    async def list_discussions(self) -> list[dict]:
        connection = await connect_db(self.db_path)
        try:
            cursor = await connection.execute(
                """SELECT id, topic, expert_count, status, stage, created_at, updated_at
                   FROM discussion ORDER BY created_at DESC, id DESC"""
            )
            return [dict(row) for row in await cursor.fetchall()]
        finally:
            await connection.close()

    async def get_snapshot(self, discussion_id: str) -> dict | None:
        connection = await connect_db(self.db_path)
        try:
            cursor = await connection.execute(
                "SELECT * FROM discussion WHERE id = ?", (discussion_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            snapshot = dict(row)

            cursor = await connection.execute(
                "SELECT * FROM agent WHERE discussion_id = ? ORDER BY rowid", (discussion_id,)
            )
            snapshot["agents"] = [
                {
                    **dict(agent),
                    "specialties": json.loads(agent["specialties_json"]),
                }
                for agent in await cursor.fetchall()
            ]
            for agent in snapshot["agents"]:
                agent.pop("specialties_json")
                agent.pop("discussion_id")

            cursor = await connection.execute(
                "SELECT id, agent_id, sequence, stage, content, created_at "
                "FROM message WHERE discussion_id = ? ORDER BY sequence",
                (discussion_id,),
            )
            snapshot["messages"] = [dict(message) for message in await cursor.fetchall()]

            cursor = await connection.execute(
                "SELECT content_json FROM insight WHERE discussion_id = ? "
                "ORDER BY version DESC LIMIT 1",
                (discussion_id,),
            )
            latest_insight = await cursor.fetchone()
            snapshot["insight"] = (
                json.loads(latest_insight["content_json"])
                if latest_insight is not None
                else empty_insight()
            )
            return snapshot
        finally:
            await connection.close()
