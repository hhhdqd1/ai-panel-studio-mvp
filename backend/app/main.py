from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import router
from app.db import init_db
from app.fake_gateway import FakeGateway
from app.model_gateway import DeepSeekGateway
from app.orchestrator import Orchestrator
from app.panel_service import PanelService
from app.seeds import seed_examples
from app.store import Store


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "panel.sqlite3"


def create_app(store: Store, gateway: object | None = None) -> FastAPI:
    selected_gateway = gateway if gateway is not None else (
        FakeGateway() if os.getenv("APP_FAKE_MODEL") == "1" else DeepSeekGateway()
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await init_db(store.db_path)
        await store.mark_interrupted()
        await seed_examples(store)
        yield

    app = FastAPI(title="AI Panel Studio", lifespan=lifespan)
    app.state.store = store
    app.state.gateway = selected_gateway
    app.state.tasks = {}
    app.state.model_semaphore = asyncio.Semaphore(4)
    app.state.runner = Orchestrator(store, selected_gateway, app.state.model_semaphore)

    def schedule_panel(discussion_id: str) -> None:
        if not hasattr(selected_gateway, "generate_panel"):
            return
        task = asyncio.create_task(
            PanelService(store, selected_gateway, app.state.model_semaphore).generate(discussion_id)
        )
        app.state.tasks[discussion_id] = task
        task.add_done_callback(lambda _: app.state.tasks.pop(discussion_id, None))

    app.state.schedule_panel = schedule_panel
    app.include_router(router)
    return app


app = create_app(Store(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))))
