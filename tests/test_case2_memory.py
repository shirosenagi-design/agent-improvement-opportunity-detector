from contextlib import asynccontextmanager

import core.case2 as case2
from core.case2 import (
    MEMORY_ID,
    MEMORY_TEXT,
    ModelSelection,
    RetrievalRecorder,
    build_memory_retrieval_tool,
    legacy_memory_access,
)
from core.case2_evals import has_proven_retrieval_trace


def test_actual_strands_tool_execution_records_exact_memory_result():
    recorder = RetrievalRecorder()
    retrieval_tool = build_memory_retrieval_tool(recorder)

    result = retrieval_tool(query="workflow review approval preference")
    access = recorder.observed_access()

    assert result == {
        "found": True,
        "memory_id": MEMORY_ID,
        "memory_text": MEMORY_TEXT,
    }
    assert len(recorder.events) == 1
    assert access.tool_executed is True
    assert access.query == "workflow review approval preference"
    assert access.returned_memory_id == MEMORY_ID
    assert access.returned_memory_text == MEMORY_TEXT
    assert access.exact_match is True
    assert has_proven_retrieval_trace(access) is True


def test_model_self_report_does_not_create_retrieval_evidence():
    recorder = RetrievalRecorder()
    model_response = (
        f"I retrieved and used {MEMORY_ID}. "
        "FINAL_DECISION: REVIEW_FIRST"
    )

    access = recorder.observed_access()

    assert MEMORY_ID in model_response
    assert recorder.events == []
    assert access.tool_executed is False
    assert access.returned_memory_id is None
    assert has_proven_retrieval_trace(access) is False


def test_executed_tool_with_irrelevant_query_is_not_exact_retrieval():
    recorder = RetrievalRecorder()
    retrieval_tool = build_memory_retrieval_tool(recorder)

    result = retrieval_tool(query="weather forecast")
    access = recorder.observed_access()

    assert result == {
        "found": False,
        "memory_id": None,
        "memory_text": None,
    }
    assert access.tool_executed is True
    assert access.exact_match is False
    assert has_proven_retrieval_trace(access) is False


def test_legacy_memory_is_available_but_has_no_structured_trace():
    access = legacy_memory_access()

    assert access.memory_available is True
    assert access.returned_memory_id == MEMORY_ID
    assert access.returned_memory_text == MEMORY_TEXT
    assert access.tool_executed is False
    assert has_proven_retrieval_trace(access) is False


def test_candidate_path_records_retrieval_only_when_agent_invokes_tool(monkeypatch):
    selection = ModelSelection(provider="bedrock", model_id=None)

    def fake_build_agent(system_prompt, selected, *, context, tools, openai_model_params):
        assert selected is selection
        assert context is None
        assert len(tools) == 1
        assert openai_model_params == {"reasoning_effort": "none"}

        def fake_agent(prompt):
            tools[0](query="editorial approval workflow preference")
            return "FINAL_DECISION: REVIEW_FIRST\nPreserve final editorial control."

        return fake_agent

    monkeypatch.setattr(case2, "build_agent", fake_build_agent)

    result = case2.run_case2_candidate(selection)

    assert result.memory_access.tool_executed is True
    assert result.memory_access.exact_match is True
    assert has_proven_retrieval_trace(result.memory_access) is True
    assert result.responses["decision"].startswith("FINAL_DECISION: REVIEW_FIRST")


def test_both_case2_arms_share_selection_and_isolate_reasoning_params(monkeypatch):
    selection = ModelSelection(provider="openai", model_id="openai-model")
    calls = []
    clients = []

    @asynccontextmanager
    async def fake_openai_client_scope():
        client = object()
        clients.append(client)
        yield client

    def fake_build_agent(
        system_prompt,
        selected,
        *,
        context,
        tools=None,
        openai_model_params=None,
        openai_client=None,
    ):
        calls.append(
            {
                "selection": selected,
                "context": context,
                "tools": tools,
                "openai_model_params": openai_model_params,
                "openai_client": openai_client,
            }
        )

        class FakeAgent:
            async def invoke_async(self, prompt):
                if tools:
                    tools[0](query="workflow review approval preference")
                return "FINAL_DECISION: REVIEW_FIRST"

        return FakeAgent()

    monkeypatch.setattr(case2, "build_agent", fake_build_agent)
    monkeypatch.setattr(case2, "openai_client_scope", fake_openai_client_scope)

    case2.run_case2_baseline(selection)
    candidate = case2.run_case2_candidate(selection)

    assert [call["selection"] for call in calls] == [selection, selection]
    assert calls[0]["selection"] is calls[1]["selection"]
    assert [call["openai_model_params"] for call in calls] == [
        {"reasoning_effort": "none"},
        {"reasoning_effort": "none"},
    ]
    assert (
        calls[0]["openai_model_params"]
        is not calls[1]["openai_model_params"]
    )
    assert calls[0]["tools"] is None
    assert len(calls[1]["tools"]) == 1
    assert len(clients) == 2
    assert clients[0] is not clients[1]
    assert [call["openai_client"] for call in calls] == clients
    assert candidate.memory_access.tool_executed is True
    assert candidate.memory_access.exact_match is True
