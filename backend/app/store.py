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


class DiscussionStateConflict(Exception):
    """A concurrent task changed the discussion before this write began."""


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

    async def _append_event_tx(
        self, connection, discussion_id: str, event_type: str, payload: dict
    ) -> int:
        await connection.execute(
            "UPDATE discussion SET last_event_seq = last_event_seq + 1, updated_at = ? WHERE id = ?",
            (utc_now(), discussion_id),
        )
        cursor = await connection.execute(
            "SELECT last_event_seq FROM discussion WHERE id = ?", (discussion_id,)
        )
        row = await cursor.fetchone()
        sequence = row["last_event_seq"]
        await connection.execute(
            "INSERT INTO event (id, discussion_id, sequence, type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), discussion_id, sequence, event_type, json.dumps(payload, ensure_ascii=False), utc_now()),
        )
        return sequence

    async def replace_panel(self, discussion_id: str, agents: list[dict]) -> None:
        connection = await connect_db(self.db_path)
        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT status FROM discussion WHERE id = ?", (discussion_id,)
            )
            row = await cursor.fetchone()
            if row is None or row["status"] != "generating_panel":
                raise DiscussionStateConflict("discussion is not generating a panel")
            await connection.execute("DELETE FROM agent WHERE discussion_id = ?", (discussion_id,))
            saved_agents = []
            for agent in agents:
                agent_id = str(uuid4())
                saved = {
                    "id": agent_id,
                    "kind": agent["kind"],
                    "name": agent["name"],
                    "title": agent["title"],
                    "stance": agent["stance"],
                    "specialties": agent["specialties"],
                    "color": agent["color"],
                    "public_status": "waiting",
                    "public_intent": "",
                }
                await connection.execute(
                    """INSERT INTO agent
                       (id, discussion_id, kind, name, title, stance, specialties_json, color)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        agent_id, discussion_id, saved["kind"], saved["name"], saved["title"],
                        saved["stance"], json.dumps(saved["specialties"], ensure_ascii=False), saved["color"],
                    ),
                )
                saved_agents.append(saved)
            await connection.execute(
                "UPDATE discussion SET status = 'awaiting_confirmation', error_code = NULL, "
                "resume_point = NULL, updated_at = ? WHERE id = ?",
                (utc_now(), discussion_id),
            )
            await self._append_event_tx(
                connection, discussion_id, "panel.ready", {"agents": saved_agents}
            )
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def transition(
        self,
        discussion_id: str,
        expected: str,
        status: str,
        *,
        stage: str | None = None,
    ) -> bool:
        connection = await connect_db(self.db_path)
        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT status FROM discussion WHERE id = ?", (discussion_id,)
            )
            row = await cursor.fetchone()
            if row is None or row["status"] != expected:
                await connection.rollback()
                return False
            await connection.execute(
                "UPDATE discussion SET status = ?, stage = ?, error_code = NULL, "
                "resume_point = NULL, updated_at = ? WHERE id = ?",
                (status, stage, utc_now(), discussion_id),
            )
            await self._append_event_tx(
                connection, discussion_id, "discussion.status", {"status": status, "stage": stage}
            )
            await connection.commit()
            return True
        except BaseException:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def fail(self, discussion_id: str, error_code: str, resume_point: str) -> None:
        connection = await connect_db(self.db_path)
        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "UPDATE discussion SET status = 'failed', error_code = ?, resume_point = ?, "
                "updated_at = ? WHERE id = ? AND status = ?",
                (error_code, resume_point, utc_now(), discussion_id, resume_point),
            )
            if cursor.rowcount == 0:
                await connection.rollback()
                return
            await self._append_event_tx(
                connection, discussion_id, "discussion.failed", {"error_code": error_code}
            )
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def record_model_run(
        self,
        discussion_id: str,
        *,
        purpose: str,
        model: str,
        status: str,
        latency_ms: int,
        token_usage: dict | None,
        error_code: str | None,
    ) -> None:
        connection = await connect_db(self.db_path)
        try:
            await connection.execute(
                """INSERT INTO model_run
                   (id, discussion_id, purpose, model, status, latency_ms, token_usage_json,
                    error_code, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()), discussion_id, purpose, model, status, latency_ms,
                    json.dumps(token_usage) if token_usage is not None else None,
                    error_code, utc_now(),
                ),
            )
            await connection.commit()
        finally:
            await connection.close()
