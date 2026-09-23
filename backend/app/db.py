from __future__ import annotations

from pathlib import Path

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS discussion (
  id TEXT PRIMARY KEY, topic TEXT NOT NULL, expert_count INTEGER NOT NULL,
  status TEXT NOT NULL, stage TEXT, expert_turns INTEGER NOT NULL DEFAULT 0,
  summary TEXT, last_event_seq INTEGER NOT NULL DEFAULT 0,
  resume_point TEXT, error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  kind TEXT NOT NULL, name TEXT NOT NULL, title TEXT NOT NULL, stance TEXT NOT NULL,
  specialties_json TEXT NOT NULL, color TEXT NOT NULL,
  public_status TEXT NOT NULL DEFAULT 'waiting', public_intent TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS message (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  agent_id TEXT NOT NULL REFERENCES agent(id), sequence INTEGER NOT NULL,
  stage TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(discussion_id, sequence)
);
CREATE TABLE IF NOT EXISTS event (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  sequence INTEGER NOT NULL, type TEXT NOT NULL, payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(discussion_id, sequence)
);
CREATE TABLE IF NOT EXISTS insight (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  version INTEGER NOT NULL, content_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(discussion_id, version)
);
CREATE TABLE IF NOT EXISTS model_run (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  purpose TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
  latency_ms INTEGER, token_usage_json TEXT, error_code TEXT, created_at TEXT NOT NULL
);
"""


async def connect_db(db_path: str | Path) -> aiosqlite.Connection:
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys = ON")
    await connection.execute("PRAGMA busy_timeout = 5000")
    return connection


async def init_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = await connect_db(path)
    try:
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.executescript(SCHEMA)
        await connection.commit()
    finally:
        await connection.close()
