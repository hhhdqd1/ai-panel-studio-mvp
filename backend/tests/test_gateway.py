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


@pytest.mark.asyncio
async def test_intent_drops_private_model_fields_and_keeps_public_summary():
    request_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_payloads.append(json.loads(request.content))
        content = {
            "wants_to_speak": True, "action": "challenge", "target_message_id": "m1",
            "relevance": 0.8, "novelty": 0.6, "urgency": 0.7,
            "public_intent": "准备质疑统计口径", "private_reasoning": "不得公开",
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]})

    agent = {"id": "a1", "name": "专家一", "title": "研究员", "stance": "谨慎", "specialties": ["教育"]}
    context = {"discussion_id": "d1", "topic": "教育评价", "stage": "challenge", "messages": []}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DeepSeekGateway(api_key="test-secret", client=client).propose_intent(agent, context)
    assert result["agent_id"] == "a1"
    assert result["public_intent"] == "准备质疑统计口径"
    assert "private_reasoning" not in result
    assert "教育评价" in json.dumps(request_payloads[0], ensure_ascii=False)


@pytest.mark.asyncio
async def test_speech_uses_plain_text_response_and_summary_is_text():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = "先做小范围试点。再看长期效果。" if len(requests) == 1 else "讨论认为应先试点，分歧仍需验证。"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    agent = {"id": "a1", "name": "专家一", "title": "研究员", "stance": "谨慎", "specialties": ["教育"]}
    context = {"discussion_id": "d1", "topic": "教育评价", "stage": "exploration", "messages": []}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = DeepSeekGateway(api_key="test-secret", client=client)
        speech = await gateway.generate_speech(agent, context, {"action": "answer", "public_intent": "准备回答"})
        summary = await gateway.summarize(context)
    assert speech == "先做小范围试点。再看长期效果。"
    assert summary == "讨论认为应先试点，分歧仍需验证。"
    assert "response_format" not in requests[0]
    assert "response_format" not in requests[1]


@pytest.mark.asyncio
async def test_review_uses_structured_output_without_claiming_verification():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        result = {
            "consensus": [], "disagreements": [], "open_questions": [],
            "claim_flags": [{"message_id": "m1", "quote": "增长 83%", "reason_code": "needs_external_check", "explanation": "缺少来源", "status": "open"}],
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}]})

    context = {"discussion_id": "d1", "topic": "教育评价", "stage": "exploration", "messages": []}
    message = {"id": "m1", "agent_id": "a1", "content": "增长 83%，但来源不明。"}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DeepSeekGateway(api_key="test-secret", client=client).review(context, message)
    assert result["claim_flags"][0]["reason_code"] == "needs_external_check"
    assert requests[0]["response_format"] == {"type": "json_object"}
