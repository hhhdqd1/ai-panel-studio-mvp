from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas import CreateDiscussion


router = APIRouter(prefix="/api")


@router.post("/discussions", status_code=201)
async def create_discussion(body: CreateDiscussion, request: Request) -> dict:
    discussion_id = await request.app.state.store.create_discussion(
        body.topic, body.expert_count
    )
    request.app.state.schedule_panel(discussion_id)
    return {"id": discussion_id, "status": "generating_panel"}


@router.get("/discussions")
async def list_discussions(request: Request) -> list[dict]:
    return await request.app.state.store.list_discussions()


@router.get("/discussions/{discussion_id}")
async def get_discussion(discussion_id: str, request: Request) -> dict:
    snapshot = await request.app.state.store.get_snapshot(discussion_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="讨论不存在")
    return snapshot


@router.post("/discussions/{discussion_id}/start", status_code=202)
async def start_discussion(discussion_id: str, request: Request) -> dict:
    store = request.app.state.store
    if await store.get_snapshot(discussion_id) is None:
        raise HTTPException(status_code=404, detail="讨论不存在")
    changed = await store.transition(
        discussion_id, "awaiting_confirmation", "running", stage="opening"
    )
    if not changed:
        raise HTTPException(status_code=409, detail="讨论已开始或当前状态不可启动")
    request.app.state.runner.schedule(discussion_id)
    return {"id": discussion_id, "status": "running"}


@router.post("/discussions/{discussion_id}/resume", status_code=202)
async def resume_discussion(discussion_id: str, request: Request) -> dict:
    store = request.app.state.store
    snapshot = await store.get_snapshot(discussion_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="讨论不存在")
    if snapshot["status"] != "failed":
        raise HTTPException(status_code=409, detail="当前状态不可继续")
    point = snapshot["resume_point"]
    if point not in {"generating_panel", "running", "summarizing"}:
        raise HTTPException(status_code=409, detail="没有可恢复的检查点")
    if point in {"running", "summarizing"}:
        previous = request.app.state.runner.tasks.get(discussion_id)
        if previous is not None:
            await previous
    changed = await store.transition(discussion_id, "failed", point, stage=snapshot["stage"])
    if not changed:
        raise HTTPException(status_code=409, detail="讨论状态已改变")
    if point == "generating_panel":
        request.app.state.schedule_panel(discussion_id)
    else:
        request.app.state.runner.schedule(discussion_id)
    return {"id": discussion_id, "status": point}
