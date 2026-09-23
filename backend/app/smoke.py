"""Disposable end-to-end model smoke. Real API calls require explicit --real."""

from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
from pathlib import Path
from time import monotonic

from app.db import init_db
from app.fake_gateway import FakeGateway
from app.model_gateway import DeepSeekGateway
from app.orchestrator import Orchestrator
from app.panel_service import PanelService
from app.store import Store


async def run_smoke(db_path: Path, gateway: object, topic: str, expert_count: int) -> dict:
    started = monotonic()
    await init_db(db_path)
    store = Store(db_path)
    discussion_id = await store.create_discussion(topic, expert_count)
    semaphore = asyncio.Semaphore(4)
    await PanelService(store, gateway, semaphore).generate(discussion_id)
    snapshot = await store.get_snapshot(discussion_id)
    if snapshot["status"] == "awaiting_confirmation":
        await store.transition(discussion_id, "awaiting_confirmation", "running", stage="opening")
        await Orchestrator(store, gateway, semaphore).run(discussion_id)
        snapshot = await store.get_snapshot(discussion_id)
    return {
        "id": discussion_id,
        "status": snapshot["status"],
        "error_code": snapshot["error_code"],
        "panel_size": len(snapshot["agents"]),
        "agent_names": [agent["name"] for agent in snapshot["agents"]],
        "expert_turns": snapshot["expert_turns"],
        "messages": len(snapshot["messages"]),
        "flags": len(snapshot["insight"]["claim_flags"]),
        "summary": snapshot["summary"],
        "model_runs": await store.count_model_runs(discussion_id),
        "elapsed_seconds": round(monotonic() - started, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a disposable AI roundtable smoke test")
    parser.add_argument("--real", action="store_true", help="Make billable DeepSeek API calls")
    parser.add_argument("--topic", default="中小学应如何稳妥试点 AI 学习助手？")
    parser.add_argument("--experts", type=int, default=2, choices=range(2, 7))
    parser.add_argument("--database", type=Path, help="Keep smoke data at this exact path")
    args = parser.parse_args()
    if args.real and not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit("缺少 DEEPSEEK_API_KEY；没有发出真实 API 请求。")
    gateway = DeepSeekGateway() if args.real else FakeGateway()
    with tempfile.TemporaryDirectory(prefix="ai-panel-smoke-") as temporary:
        db_path = args.database or Path(temporary) / "smoke.sqlite3"
        result = asyncio.run(run_smoke(db_path, gateway, args.topic, args.experts))
    print(f"模式：{'真实 DeepSeek' if args.real else '假模型'}")
    print(f"状态：{result['status']}；错误码：{result['error_code'] or '无'}")
    print(f"耗时：{result['elapsed_seconds']} 秒；模型调用：{result['model_runs']} 次")
    print(f"阵容：{result['panel_size']} 人（{', '.join(result['agent_names'])}）")
    print(f"发言：{result['messages']} 条，专家回合：{result['expert_turns']}，风险标记：{result['flags']}")
    if result["summary"]:
        print(f"自然语言总结：{result['summary']}")
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
