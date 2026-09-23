from __future__ import annotations

import asyncio
import json
import os
from typing import Callable, Literal, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.prompts import (
    intent_messages,
    moderator_messages,
    panel_messages,
    speech_messages,
    summary_messages,
)


T = TypeVar("T")


class ModelOutputError(Exception):
    """The model returned content that did not meet the public JSON contract."""


class ModelRequestError(Exception):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


class AgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["host", "expert"]
    name: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    stance: str = Field(min_length=1, max_length=160)
    specialties: list[str] = Field(min_length=1, max_length=5)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("name", "title", "stance")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty agent field")
        return value

    @field_validator("specialties")
    @classmethod
    def nonempty_specialties(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("empty specialty")
        return cleaned


class PanelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agents: list[AgentDraft]

    @model_validator(mode="after")
    def unique_names(self) -> "PanelResponse":
        names = [agent.name for agent in self.agents]
        if len(names) != len(set(names)):
            raise ValueError("agent names must be unique")
        return self


def validate_panel(payload: dict, count: int) -> list[dict]:
    try:
        agents = PanelResponse.model_validate(payload).agents
    except ValidationError as error:
        raise ModelOutputError("invalid_panel") from error
    if len(agents) != count + 1 or sum(agent.kind == "host" for agent in agents) != 1:
        raise ModelOutputError("panel_size_mismatch")
    return [agent.model_dump() for agent in agents]


class IntentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wants_to_speak: bool
    action: Literal["answer", "supplement", "challenge", "follow_up"]
    target_message_id: str | None = None
    relevance: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    urgency: float = Field(ge=0, le=1)
    public_intent: str = Field(max_length=160)


def validate_intent(payload: dict) -> dict:
    try:
        return IntentResponse.model_validate(payload).model_dump()
    except ValidationError as error:
        raise ModelOutputError("invalid_intent") from error


class DeepSeekGateway:
    base_url = "https://api.deepseek.com/chat/completions"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.client = client
        self.last_usage: dict | None = None

    async def generate_panel(self, topic: str, count: int) -> list[dict]:
        return await self._chat_json(
            panel_messages(topic, count),
            lambda payload: validate_panel(payload, count),
        )

    async def propose_intent(self, agent: dict, context: dict) -> dict:
        result = await self._chat_json(intent_messages(agent, context), validate_intent)
        return {"agent_id": agent["id"], **result}

    async def generate_speech(self, agent: dict, context: dict, intent: dict) -> str:
        return await self._chat_text(speech_messages(agent, context, intent))

    async def moderate(self, context: dict, kind: str) -> str:
        return await self._chat_text(moderator_messages(context, kind))

    async def summarize(self, context: dict) -> str:
        return await self._chat_text(summary_messages(context))

    async def _chat_json(
        self, messages: list[dict[str, str]], validator: Callable[[dict], T]
    ) -> T:
        if not self.api_key:
            raise ModelRequestError("missing_api_key")

        for attempt in range(3):
            try:
                client = self.client or httpx.AsyncClient(timeout=30.0)
                try:
                    response = await client.post(
                        self.base_url,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": messages,
                            "response_format": {"type": "json_object"},
                            "stream": False,
                        },
                    )
                finally:
                    if self.client is None:
                        await client.aclose()

                if response.status_code in {401, 403}:
                    raise ModelRequestError("model_unauthorized")
                if response.status_code == 429 or response.status_code >= 500:
                    raise ModelRequestError("model_temporarily_unavailable")
                if response.status_code >= 400:
                    raise ModelRequestError("model_request_rejected")

                envelope = response.json()
                self.last_usage = envelope.get("usage")
                content = envelope["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ModelOutputError("empty_model_output")
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ModelOutputError("model_output_not_object")
                return validator(parsed)
            except ModelRequestError as error:
                if error.error_code != "model_temporarily_unavailable" or attempt == 2:
                    raise
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt == 2:
                    raise ModelRequestError("model_timeout") from error
            except (ValueError, KeyError, IndexError, TypeError, ModelOutputError) as error:
                if attempt == 2:
                    raise ModelOutputError("invalid_model_json") from error

            await asyncio.sleep(0.05 * (2**attempt))

        raise ModelOutputError("invalid_model_json")

    async def _chat_text(self, messages: list[dict[str, str]]) -> str:
        if not self.api_key:
            raise ModelRequestError("missing_api_key")

        for attempt in range(3):
            try:
                client = self.client or httpx.AsyncClient(timeout=30.0)
                try:
                    response = await client.post(
                        self.base_url,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={"model": self.model, "messages": messages, "stream": False},
                    )
                finally:
                    if self.client is None:
                        await client.aclose()
                if response.status_code in {401, 403}:
                    raise ModelRequestError("model_unauthorized")
                if response.status_code == 429 or response.status_code >= 500:
                    raise ModelRequestError("model_temporarily_unavailable")
                if response.status_code >= 400:
                    raise ModelRequestError("model_request_rejected")
                envelope = response.json()
                self.last_usage = envelope.get("usage")
                content = envelope["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ModelOutputError("empty_model_output")
                return content.strip()
            except ModelRequestError as error:
                if error.error_code != "model_temporarily_unavailable" or attempt == 2:
                    raise
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt == 2:
                    raise ModelRequestError("model_timeout") from error
            except (ValueError, KeyError, IndexError, TypeError, ModelOutputError) as error:
                if attempt == 2:
                    raise ModelOutputError("invalid_model_response") from error
            await asyncio.sleep(0.05 * (2**attempt))

        raise ModelOutputError("invalid_model_response")
