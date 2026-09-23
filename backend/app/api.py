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
