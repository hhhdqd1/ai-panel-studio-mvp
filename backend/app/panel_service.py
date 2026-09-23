from __future__ import annotations

import asyncio
from time import perf_counter

from app.model_gateway import ModelOutputError, ModelRequestError, validate_panel
from app.store import DiscussionStateConflict, Store


class PanelService:
    def __init__(
        self, store: Store, gateway: object, semaphore: asyncio.Semaphore | None = None
    ) -> None:
        self.store = store
        self.gateway = gateway
        self.semaphore = semaphore

    async def generate(self, discussion_id: str) -> None:
        snapshot = await self.store.get_snapshot(discussion_id)
        if snapshot is None or snapshot["status"] != "generating_panel":
            return
        started = perf_counter()
        error_code = None
        skipped = False
        try:
            if self.semaphore is None:
                raw_agents = await self.gateway.generate_panel(
                    snapshot["topic"], snapshot["expert_count"]
                )
            else:
                async with self.semaphore:
                    raw_agents = await self.gateway.generate_panel(
                        snapshot["topic"], snapshot["expert_count"]
                    )
            agents = validate_panel({"agents": raw_agents}, snapshot["expert_count"])
            await self.store.replace_panel(discussion_id, agents)
        except DiscussionStateConflict:
            skipped = True
        except ModelRequestError as error:
            error_code = error.error_code
            await self.store.fail(discussion_id, error_code, "generating_panel")
        except (ModelOutputError, ValueError):
            error_code = "invalid_panel"
            await self.store.fail(discussion_id, error_code, "generating_panel")
        finally:
            await self.store.record_model_run(
                discussion_id,
                purpose="panel",
                model=getattr(self.gateway, "model", "unknown"),
                status="skipped" if skipped else ("failed" if error_code else "succeeded"),
                latency_ms=round((perf_counter() - started) * 1000),
                token_usage=getattr(self.gateway, "last_usage", None),
                error_code=error_code,
            )
