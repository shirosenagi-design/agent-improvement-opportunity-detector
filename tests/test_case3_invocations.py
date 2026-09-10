from contextlib import asynccontextmanager

import pytest

import core.case3 as case3
from core.agents import ModelSelection


def test_four_invocations_are_isolated_and_capture_exact_inputs(monkeypatch):
    selection = ModelSelection(provider="bedrock", model_id="offline-model")
    calls = []
    agents = []

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
                "system_prompt": system_prompt,
                "selection": selected,
                "context": context,
                "tools": tools,
                "openai_model_params": openai_model_params,
                "openai_client": openai_client,
            }
        )

        def fake_agent(prompt):
            return f"response-{len(calls)}:{prompt}"

        agents.append(fake_agent)
        return fake_agent

    monkeypatch.setattr(case3, "build_agent", fake_build_agent)

    baseline = case3.run_case3_baseline(selection)
    candidate = case3.run_case3_candidate(selection)
    observations = [
        *baseline.invocation_observations,
        *candidate.invocation_observations,
    ]

    assert len(calls) == 4
    assert len({id(agent) for agent in agents}) == 4
    assert [observation.observation_id for observation in observations] == [
        "baseline:condition-a",
        "baseline:condition-b",
        "candidate:condition-a",
        "candidate:condition-b",
    ]
    assert {observation.shared_utterance for observation in observations} == {
        case3.SHARED_UTTERANCE
    }
    assert all(
        observation.context_delivery_path == "build_agent.context"
        for observation in observations
    )
    assert all(observation.tools_absent for observation in observations)
    assert all(call["tools"] is None for call in calls)
    assert all(call["selection"] is selection for call in calls)
    assert list(baseline.responses) == ["condition-a", "condition-b"]
    assert list(candidate.responses) == ["condition-a", "condition-b"]

    for condition in case3.RELATIONSHIP_CONDITIONS:
        expected_context = case3.relationship_context(condition)
        condition_observations = [
            observation
            for observation in observations
            if observation.condition_id == condition.id
        ]
        assert len(condition_observations) == 2
        assert {
            observation.relationship_context
            for observation in condition_observations
        } == {expected_context}


def test_openai_invocations_use_separate_owned_clients_and_same_params(monkeypatch):
    selection = ModelSelection(provider="openai", model_id="offline-model")
    clients = []
    closed = []
    build_calls = []

    @asynccontextmanager
    async def fake_client_scope():
        client = object()
        clients.append(client)
        try:
            yield client
        finally:
            closed.append(client)

    def fake_build_agent(
        system_prompt,
        selected,
        *,
        context,
        tools=None,
        openai_model_params=None,
        openai_client=None,
    ):
        build_calls.append(
            {
                "selection": selected,
                "context": context,
                "tools": tools,
                "params": openai_model_params,
                "client": openai_client,
            }
        )

        class FakeAgent:
            async def invoke_async(self, prompt):
                return f"response:{prompt}"

        return FakeAgent()

    monkeypatch.setattr(case3, "openai_client_scope", fake_client_scope)
    monkeypatch.setattr(case3, "build_agent", fake_build_agent)

    case3.run_case3_baseline(selection)
    case3.run_case3_candidate(selection)

    assert len(clients) == 4
    assert len({id(client) for client in clients}) == 4
    assert closed == clients
    assert [call["client"] for call in build_calls] == clients
    assert all(call["selection"] is selection for call in build_calls)
    assert all(call["tools"] is None for call in build_calls)
    assert [call["params"] for call in build_calls] == [
        {"reasoning_effort": "none"},
        {"reasoning_effort": "none"},
        {"reasoning_effort": "none"},
        {"reasoning_effort": "none"},
    ]
    assert len({id(call["params"]) for call in build_calls}) == 4


def test_openai_owned_client_closes_when_an_invocation_fails(monkeypatch):
    selection = ModelSelection(provider="openai", model_id="offline-model")
    clients = []
    closed = []
    invocation_count = 0

    @asynccontextmanager
    async def fake_client_scope():
        client = object()
        clients.append(client)
        try:
            yield client
        finally:
            closed.append(client)

    def fake_build_agent(*args, **kwargs):
        class FakeAgent:
            async def invoke_async(self, prompt):
                nonlocal invocation_count
                invocation_count += 1
                if invocation_count == 2:
                    raise RuntimeError("offline invocation failure")
                return "completed"

        return FakeAgent()

    monkeypatch.setattr(case3, "openai_client_scope", fake_client_scope)
    monkeypatch.setattr(case3, "build_agent", fake_build_agent)

    with pytest.raises(RuntimeError, match="offline invocation failure"):
        case3.run_case3_baseline(selection)

    assert len(clients) == 2
    assert closed == clients
