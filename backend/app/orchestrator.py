from __future__ import annotations

import asyncio
import re
from time import monotonic, perf_counter
from typing import Awaitable, Callable, TypeVar

from app.model_gateway import ModelOutputError, ModelRequestError
from app.selector import select_speaker
from app.store import Store


T = TypeVar("T")


def speech_is_short(text: str) -> bool:
    sentences = [part for part in re.split(r"[。！？!?]+", text.strip()) if part.strip()]
    return 1 <= len(sentences) <= 2 and len(text) <= 240


def stage_for_turns(expert_turns: int) -> str:
    if expert_turns < 4:
        return "exploration"
    if expert_turns < 8:
        return "challenge"
    if expert_turns < 12:
        return "synthesis"
    return "closing"


class Orchestrator:
    def __init__(self, store: Store, gateway: object, semaphore: asyncio.Semaphore) -> None:
        self.store = store
        self.gateway = gateway
        self.semaphore = semaphore
        self.tasks: dict[str, asyncio.Task] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.call_counts: dict[str, int] = {}

    def schedule(self, discussion_id: str) -> bool:
        existing = self.tasks.get(discussion_id)
        if existing is not None and not existing.done():
            return False
        task = asyncio.create_task(self.run(discussion_id))
        self.tasks[discussion_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(discussion_id, None))
        return True

    async def _model_call(
        self,
        discussion_id: str,
        purpose: str,
        fn: Callable[..., Awaitable[T]],
        *args: object,
    ) -> T:
        used = self.call_counts.get(discussion_id, 0)
        if used >= 100:
            raise ModelRequestError("model_call_limit")
        self.call_counts[discussion_id] = used + 1
        started = perf_counter()
        error_code = None
        try:
            async with self.semaphore:
                return await fn(*args)
        except ModelRequestError as error:
            error_code = error.error_code
            raise
        except ModelOutputError:
            error_code = "invalid_model_output"
            raise
        except Exception:
            error_code = "model_error"
            raise
        finally:
            await self.store.record_model_run(
                discussion_id,
                purpose=purpose,
                model=getattr(self.gateway, "model", "unknown"),
                status="failed" if error_code else "succeeded",
                latency_ms=round((perf_counter() - started) * 1000),
                token_usage=None,
                error_code=error_code,
            )

    @staticmethod
    def _context(snapshot: dict) -> dict:
        messages = snapshot["messages"][-12:]
        host_ids = {agent["id"] for agent in snapshot["agents"] if agent["kind"] == "host"}
        latest_host = next(
            (message["content"] for message in reversed(messages) if message["agent_id"] in host_ids),
            snapshot["topic"],
        )
        return {
            "discussion_id": snapshot["id"],
            "topic": snapshot["topic"],
            "stage": snapshot["stage"],
            "expert_turns": snapshot["expert_turns"],
            "current_question": latest_host,
            "messages": messages,
            "insight": snapshot["insight"],
        }

    async def _collect_intents(self, discussion_id: str, experts: list[dict], context: dict) -> list[dict]:
        results = await asyncio.gather(
            *(
                self._model_call(
                    discussion_id, "intent", self.gateway.propose_intent, agent, context
                )
                for agent in experts
            ),
            return_exceptions=True,
        )
        return [
            result
            for result in results
            if isinstance(result, dict) and result.get("wants_to_speak") is True
        ]

    async def _host_message(self, discussion_id: str, host_id: str, kind: str) -> None:
        snapshot = await self.store.get_snapshot(discussion_id)
        context = self._context(snapshot)
        content = await self._model_call(
            discussion_id, "moderate", self.gateway.moderate, context, kind
        )
        await self.store.append_message(discussion_id, host_id, snapshot["stage"] or kind, content)

    async def _run_running(self, discussion_id: str) -> None:
        snapshot = await self.store.get_snapshot(discussion_id)
        host_id = next(agent["id"] for agent in snapshot["agents"] if agent["kind"] == "host")
        experts = [agent for agent in snapshot["agents"] if agent["kind"] == "expert"]
        deadline = monotonic() + 20 * 60

        if not snapshot["messages"]:
            await self._host_message(discussion_id, host_id, "opening")
            await self.store.transition(discussion_id, "running", "running", stage="exploration")

        empty_rounds = 0
        while True:
            snapshot = await self.store.get_snapshot(discussion_id)
            if snapshot["expert_turns"] >= 12 or monotonic() >= deadline:
                break
            if self.call_counts[discussion_id] >= 98:
                break

            context = self._context(snapshot)
            intents = await self._collect_intents(discussion_id, experts, context)
            expert_ids = {agent["id"] for agent in experts}
            recent = [
                message["agent_id"]
                for message in snapshot["messages"]
                if message["agent_id"] in expert_ids
            ]
            spoken_counts = {agent_id: recent.count(agent_id) for agent_id in expert_ids}
            selected = select_speaker(intents, recent, spoken_counts)
            if selected is None:
                empty_rounds += 1
                if empty_rounds >= 2:
                    break
                await self._host_message(discussion_id, host_id, "reframe")
                continue
            empty_rounds = 0
            agent = next(agent for agent in experts if agent["id"] == selected["agent_id"])
            await self.store.update_agent(
                discussion_id, agent["id"], "speaking", str(selected.get("public_intent") or "")
            )
            speech = await self._model_call(
                discussion_id, "speech", self.gateway.generate_speech, agent, context, selected
            )
            if not speech_is_short(speech):
                raise ModelOutputError("speech_length_invalid")
            await self.store.append_message(discussion_id, agent["id"], snapshot["stage"], speech)
            await self.store.update_agent(
                discussion_id, agent["id"], "waiting", str(selected.get("public_intent") or "")
            )

            next_stage = stage_for_turns(snapshot["expert_turns"] + 1)
            if next_stage != snapshot["stage"] and next_stage != "closing":
                await self.store.transition(discussion_id, "running", "running", stage=next_stage)
                await self._host_message(discussion_id, host_id, next_stage)

        await self.store.transition(discussion_id, "running", "running", stage="closing")
        await self._host_message(discussion_id, host_id, "closing")
        await self.store.transition(discussion_id, "running", "summarizing", stage="closing")

    async def run(self, discussion_id: str) -> None:
        lock = self.locks.setdefault(discussion_id, asyncio.Lock())
        async with lock:
            snapshot = await self.store.get_snapshot(discussion_id)
            if snapshot is None or snapshot["status"] not in {"running", "summarizing"}:
                return
            self.call_counts[discussion_id] = await self.store.count_model_runs(discussion_id)
            try:
                if snapshot["status"] == "running":
                    await self._run_running(discussion_id)
                snapshot = await self.store.get_snapshot(discussion_id)
                context = self._context(snapshot)
                summary = await self._model_call(
                    discussion_id, "summary", self.gateway.summarize, context
                )
                await self.store.complete(discussion_id, summary)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                snapshot = await self.store.get_snapshot(discussion_id)
                if snapshot is not None:
                    point = "summarizing" if snapshot["status"] == "summarizing" else "running"
                    error_code = (
                        error.error_code if isinstance(error, ModelRequestError)
                        else "invalid_model_output" if isinstance(error, ModelOutputError)
                        else "orchestration_error"
                    )
                    await self.store.fail(discussion_id, error_code, point)
