import json

import httpx
import openai
import pytest

from core.agents import ModelSelection
from core.case2 import (
    MEMORY_ID,
    MEMORY_TEXT,
    run_case2_candidate,
)


def _sse_response(*events: dict[str, object]) -> httpx.Response:
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
    body += "data: [DONE]\n\n"
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=body.encode(),
    )


def _chunk(*, delta: dict[str, object], finish_reason: str | None) -> dict[str, object]:
    return {
        "id": "chatcmpl-offline",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "offline-model",
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def test_openai_tool_loop_keeps_transport_open_through_final_response(
    monkeypatch: pytest.MonkeyPatch,
):
    requests: list[httpx.Request] = []
    clients: list[openai.DefaultAsyncHttpxClient] = []
    close_counts: list[int] = []
    http_client_configs: list[dict[str, object]] = []
    sdk_client_configs: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _sse_response(
                _chunk(delta={"role": "assistant"}, finish_reason=None),
                _chunk(
                    delta={
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-memory",
                                "type": "function",
                                "function": {
                                    "name": "retrieve_user_memory",
                                    "arguments": json.dumps(
                                        {"query": "workflow review approval preference"}
                                    ),
                                },
                            }
                        ]
                    },
                    finish_reason=None,
                ),
                _chunk(delta={}, finish_reason="tool_calls"),
            )
        if len(requests) == 2:
            return _sse_response(
                _chunk(delta={"role": "assistant"}, finish_reason=None),
                _chunk(
                    delta={"content": "FINAL_DECISION: REVIEW_FIRST"},
                    finish_reason=None,
                ),
                _chunk(delta={}, finish_reason="stop"),
            )
        raise AssertionError("unexpected third model request")

    real_http_client_type = openai.DefaultAsyncHttpxClient
    real_async_openai_type = openai.AsyncOpenAI

    def mock_http_client(**kwargs):
        http_client_configs.append(kwargs)
        client = real_http_client_type(transport=httpx.MockTransport(handler))
        clients.append(client)
        close_counts.append(0)
        real_aclose = client.aclose

        async def counted_aclose():
            close_counts[0] += 1
            await real_aclose()

        client.aclose = counted_aclose
        return client

    def mock_async_openai(**kwargs):
        sdk_client_configs.append(kwargs)
        return real_async_openai_type(**kwargs)

    monkeypatch.setattr(openai, "DefaultAsyncHttpxClient", mock_http_client)
    monkeypatch.setattr(openai, "AsyncOpenAI", mock_async_openai)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-placeholder-only")

    result = run_case2_candidate(
        ModelSelection(provider="openai", model_id="offline-model")
    )

    assert len(requests) == 2
    assert result.memory_access.tool_executed is True
    assert result.memory_access.returned_memory_id == MEMORY_ID
    assert result.memory_access.returned_memory_text == MEMORY_TEXT
    assert "FINAL_DECISION: REVIEW_FIRST" in result.responses["decision"]
    assert len(clients) == 1
    assert close_counts == [1]
    assert clients[0].is_closed is True
    assert http_client_configs[0]["verify"] is not False
    assert sdk_client_configs[0]["http_client"] is clients[0]
    assert sdk_client_configs[0]["max_retries"] == 0


def test_openai_case2_closes_transport_once_when_model_request_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    request_count = 0
    clients: list[openai.DefaultAsyncHttpxClient] = []
    close_counts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ConnectError("offline transport failure", request=request)

    real_http_client_type = openai.DefaultAsyncHttpxClient

    def mock_http_client(**kwargs):
        client = real_http_client_type(transport=httpx.MockTransport(handler))
        clients.append(client)
        close_counts.append(0)
        real_aclose = client.aclose

        async def counted_aclose():
            close_counts[0] += 1
            await real_aclose()

        client.aclose = counted_aclose
        return client

    monkeypatch.setattr(openai, "DefaultAsyncHttpxClient", mock_http_client)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-placeholder-only")

    with pytest.raises(openai.APIConnectionError, match="Connection error"):
        run_case2_candidate(
            ModelSelection(provider="openai", model_id="offline-model")
        )

    assert request_count == 1
    assert close_counts == [1]
    assert clients[0].is_closed is True
