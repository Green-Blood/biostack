import json

import httpx
import pytest

from config import Settings
from services.ai_provider import AiNotConfigured, ai_status, build_chat_client, build_lab_parser, check_ai_connection
from services.gemini_client import AiRequestError, ChatTurn
from services.openai_compat_client import OpenAICompatClient


def test_openai_compat_provider_requires_base_url_and_model():
    with pytest.raises(AiNotConfigured, match="OPENAI_BASE_URL"):
        build_lab_parser(Settings(_env_file=None, ai_provider="openai_compat", openai_base_url="", openai_model="m"))
    with pytest.raises(AiNotConfigured, match="OPENAI_MODEL"):
        build_lab_parser(Settings(_env_file=None, ai_provider="openai_compat", openai_base_url="http://localhost:11434/v1", openai_model=""))


def test_openai_compat_provider_builds_client_and_status():
    cfg = Settings(
        _env_file=None,
        ai_provider="openai_compat",
        openai_base_url="http://localhost:11434/v1",
        openai_api_key="sk-secret",
        openai_model="qwen2.5:14b",
    )
    client = build_chat_client(cfg)
    assert isinstance(client, OpenAICompatClient)
    status = ai_status(cfg)
    assert status == {
        "provider": "openai_compat",
        "model": "qwen2.5:14b",
        "configured": True,
        "base_url": "http://localhost:11434/v1",
    }
    assert "sk-secret" not in json.dumps(status)


def test_openai_compat_generate_json_strips_fences():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content)
        assert body["model"] == "llama3.2"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "```json\n{\"summary\": \"All clear\", \"findings\": []}\n```"}}]
        })

    client = OpenAICompatClient("http://localhost:11434/v1", "llama3.2", transport=httpx.MockTransport(handler))
    out = client.generate_json("Read this", b"Normal scan", {"type": "object", "properties": {"summary": {"type": "string"}}}, mime_type="text/plain")
    assert out == {"summary": "All clear", "findings": []}


def test_openai_compat_generate_text_with_tools_and_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"
        assert body["messages"][2]["role"] == "assistant"
        assert body["tools"][0]["function"]["name"] == "log_weight"
        return httpx.Response(200, json={
            "choices": [{
                "message": {
                    "content": "Proposing weight log.",
                    "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "log_weight", "arguments": '{"kg": 72.5}'}}],
                }
            }],
            "usage": {"prompt_tokens": 120, "completion_tokens": 15, "prompt_tokens_details": {"cached_tokens": 40}},
        })

    client = OpenAICompatClient("http://localhost:11434/v1", "qwen2.5", api_key="k", transport=httpx.MockTransport(handler))
    reply = client.generate_text(
        "sys", "ctx", "Log 72.5",
        history=[ChatTurn("user", "Hi"), ChatTurn("model", "Hello")],
        tools=[{"name": "log_weight", "description": "Log weight", "parameters": {"type": "object"}}],
    )
    assert reply.text == "Proposing weight log."
    assert reply.input_tokens == 120 and reply.cached_tokens == 40 and reply.output_tokens == 15
    assert len(reply.calls) == 1 and reply.calls[0].name == "log_weight" and reply.calls[0].args == {"kg": 72.5}


def test_openai_compat_stream_text_and_ping():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hello "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
        'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\n'
        'data: [DONE]\n\n'
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen2.5"}]})
        if request.method == "POST" and request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, content=sse, headers={"Content-Type": "text/event-stream"})
        return httpx.Response(404)

    client = OpenAICompatClient("http://localhost:11434/v1", "qwen2.5", transport=httpx.MockTransport(handler))
    assert client.ping() == {"ok": True, "provider": "openai_compat", "model": "qwen2.5"}
    events = list(client.stream_text("sys", "ctx", "hi"))
    assert events[:-1] == ["Hello ", "world"]
    assert events[-1].text == "Hello world"
    assert events[-1].input_tokens == 10 and events[-1].output_tokens == 2


def test_openai_compat_ping_failure_raises_ai_request_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = OpenAICompatClient("http://localhost:11434/v1", "qwen2.5", transport=httpx.MockTransport(handler))
    with pytest.raises(AiRequestError, match="503"):
        client.ping()


def test_settings_ai_status_and_test_endpoints(client, monkeypatch):
    monkeypatch.setattr(
        "routers.user_settings.app_config",
        Settings(_env_file=None, biostack_fake_ai=True, app_env="test"),
    )
    res_status = client.get("/api/v1/settings/ai-status")
    assert res_status.status_code == 200
    assert res_status.json() == {"provider": "fake", "model": "fake", "configured": True, "base_url": None}

    res_test = client.post("/api/v1/settings/ai-test")
    assert res_test.status_code == 200
    assert res_test.json() == {"ok": True, "provider": "fake", "model": "fake"}

    assert check_ai_connection(Settings(_env_file=None, biostack_fake_ai=True, app_env="test"))["ok"] is True
