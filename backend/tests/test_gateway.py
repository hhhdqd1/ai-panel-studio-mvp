from __future__ import annotations

import json

import httpx
import pytest

from app.model_gateway import DeepSeekGateway, ModelOutputError, ModelRequestError


def panel_response() -> dict:
    agents = [
        {"kind": "host", "name": "主持人", "title": "主持", "stance": "中立", "specialties": ["引导"], "color": "#4361ee"}
    ]
    agents.extend(
        {
            "kind": "expert", "name": f"专家{index}", "title": "研究员",
            "stance": f"视角{index}", "specialties": ["政策"], "color": "#f97316",
        }
        for index in range(1, 5)
    )
    return {"choices": [{"message": {"content": json.dumps({"agents": agents}, ensure_ascii=False)}}]}


@pytest.mark.asyncio
async def test_malformed_json_has_bounded_retries_and_hides_key():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{broken"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = DeepSeekGateway(api_key="test-secret", client=client)
        with pytest.raises(ModelOutputError) as error:
            await gateway.generate_panel("城市交通", 4)
    assert len(requests) == 3
    assert "test-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_rate_limit_is_retried_then_panel_succeeds():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["Authorization"] == "Bearer test-secret"
        if calls == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(200, json=panel_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DeepSeekGateway(api_key="test-secret", client=client).generate_panel("城市交通", 4)
    assert calls == 2
    assert len(result) == 5


@pytest.mark.asyncio
async def test_invalid_panel_shape_is_retried_before_failing_discussion():
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"agents": []}'}}]})
        return httpx.Response(200, json=panel_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DeepSeekGateway(api_key="test-secret", client=client).generate_panel("城市交通", 4)
    assert calls == 2
    assert len(result) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "",
        '{"agents":[{"kind":"expert","name":"缺失字段"}]}',
    ],
)
async def test_empty_or_missing_fields_fail_after_three_attempts(content):
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelOutputError):
            await DeepSeekGateway(api_key="test-secret", client=client).generate_panel("城市交通", 4)
    assert calls == 3


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_has_safe_error_code():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("request timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelRequestError) as error:
            await DeepSeekGateway(api_key="test-secret", client=client).generate_panel("城市交通", 4)
    assert calls == 3
    assert error.value.error_code == "model_timeout"


@pytest.mark.asyncio
async def test_unauthorized_is_not_retried_or_echoed():
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "test-secret rejected"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelRequestError) as error:
            await DeepSeekGateway(api_key="test-secret", client=client).generate_panel("城市交通", 4)
    assert calls == 1
    assert "test-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_missing_key_fails_before_http_call():
    gateway = DeepSeekGateway(api_key="")
    with pytest.raises(ModelRequestError) as error:
        await gateway.generate_panel("城市交通", 4)
    assert error.value.error_code == "missing_api_key"
