from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import router
from app.db import init_db
from app.store import Store


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "panel.sqlite3"


def create_app(store: Store, gateway: object | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await init_db(store.db_path)
        yield

    app = FastAPI(title="AI Panel Studio", lifespan=lifespan)
    app.state.store = store
    app.state.gateway = gateway
    app.state.schedule_panel = lambda _discussion_id: None
    app.include_router(router)
    return app


app = create_app(Store(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))))
