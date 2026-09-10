import sys
from types import ModuleType

import pytest

import core.agents as agents
import core.runner as runner
from core.schemas import EvaluationRun, RunState


def test_model_provider_defaults_to_bedrock(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.setenv("BEDROCK_MODEL_ID", "bedrock-model")

    selection = agents.resolve_model_selection()

    assert selection == agents.ModelSelection(provider="bedrock", model_id="bedrock-model")


def test_bedrock_without_model_id_preserves_strands_default(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.setitem(sys.modules, "strands.models.openai", None)
    captured = {}

    monkeypatch.setattr(agents, "Agent", lambda **kwargs: captured.update(kwargs) or object())
    selection = agents.resolve_model_selection()
    agents.build_agent("system", selection)

    assert "model" not in captured


def test_openai_requires_model_id(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_MODEL_ID", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "present")

    with pytest.raises(ValueError, match="OPENAI_MODEL_ID is required"):
        agents.resolve_model_selection()


def test_openai_requires_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL_ID", "openai-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        agents.resolve_model_selection()


def test_openai_provider_is_built_only_when_selected(monkeypatch):
    import ssl

    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL_ID", "openai-model")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    model_config = {}
    transport_config = {}

    class FakeSSLContext:
        def __init__(self, protocol):
            self.protocol = protocol

    class FakeDefaultAsyncHttpxClient:
        def __init__(self, **kwargs):
            transport_config.update(kwargs)

    class FakeOpenAIModel:
        def __init__(self, **kwargs):
            model_config.update(kwargs)

    fake_truststore = ModuleType("truststore")
    fake_truststore.SSLContext = FakeSSLContext
    fake_openai = ModuleType("openai")
    fake_openai.DefaultAsyncHttpxClient = FakeDefaultAsyncHttpxClient
    fake_strands_openai = ModuleType("strands.models.openai")
    fake_strands_openai.OpenAIModel = FakeOpenAIModel
    monkeypatch.setitem(sys.modules, "truststore", fake_truststore)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setitem(sys.modules, "strands.models.openai", fake_strands_openai)
    monkeypatch.setattr(agents, "Agent", lambda **kwargs: kwargs)

    selection = agents.resolve_model_selection()
    built = agents.build_agent("system", selection)

    assert selection == agents.ModelSelection(provider="openai", model_id="openai-model")
    assert model_config["model_id"] == "openai-model"
    assert set(model_config["client_args"]) == {"api_key", "http_client", "max_retries"}
    assert model_config["client_args"]["max_retries"] == 0
    assert isinstance(
        model_config["client_args"]["http_client"], FakeDefaultAsyncHttpxClient
    )
    assert isinstance(transport_config["verify"], FakeSSLContext)
    assert transport_config["verify"].protocol == ssl.PROTOCOL_TLS_CLIENT
    assert isinstance(built["model"], FakeOpenAIModel)
    assert "params" not in model_config



def test_openai_model_params_are_copied_and_forwarded(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    model_config = {}

    class FakeSSLContext:
        def __init__(self, protocol):
            self.protocol = protocol

    class FakeDefaultAsyncHttpxClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAIModel:
        def __init__(self, **kwargs):
            model_config.update(kwargs)

    fake_truststore = ModuleType("truststore")
    fake_truststore.SSLContext = FakeSSLContext
    fake_openai = ModuleType("openai")
    fake_openai.DefaultAsyncHttpxClient = FakeDefaultAsyncHttpxClient
    fake_strands_openai = ModuleType("strands.models.openai")
    fake_strands_openai.OpenAIModel = FakeOpenAIModel
    monkeypatch.setitem(sys.modules, "truststore", fake_truststore)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setitem(sys.modules, "strands.models.openai", fake_strands_openai)
    monkeypatch.setattr(agents, "Agent", lambda **kwargs: kwargs)
    original = {"reasoning_effort": "none"}

    agents.build_agent(
        "system",
        agents.ModelSelection(provider="openai", model_id="openai-model"),
        openai_model_params=original,
    )

    assert model_config["params"] == {"reasoning_effort": "none"}
    assert model_config["params"] is not original
    assert original == {"reasoning_effort": "none"}


def test_openai_caller_owned_client_is_forwarded_without_client_args(monkeypatch):
    model_config = {}
    injected_client = object()

    class FakeOpenAIModel:
        def __init__(self, **kwargs):
            model_config.update(kwargs)

    fake_strands_openai = ModuleType("strands.models.openai")
    fake_strands_openai.OpenAIModel = FakeOpenAIModel
    monkeypatch.setitem(sys.modules, "strands.models.openai", fake_strands_openai)
    monkeypatch.setattr(agents, "Agent", lambda **kwargs: kwargs)

    built = agents.build_agent(
        "system",
        agents.ModelSelection(provider="openai", model_id="openai-model"),
        openai_model_params={"reasoning_effort": "none"},
        openai_client=injected_client,
    )

    assert model_config == {
        "client": injected_client,
        "model_id": "openai-model",
        "params": {"reasoning_effort": "none"},
    }
    assert built["model"].__class__ is FakeOpenAIModel


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="Unsupported MODEL_PROVIDER: unknown"):
        agents.resolve_model_selection()


def test_runner_reuses_one_selection_and_records_safe_metadata(monkeypatch):
    selection = agents.ModelSelection(provider="openai", model_id="openai-model")
    received = []

    monkeypatch.setattr(runner, "resolve_model_selection", lambda: selection)
    monkeypatch.setattr(
        runner,
        "run_agent_suite",
        lambda case, prompt, selected: received.append(selected) or {},
    )
    monkeypatch.setattr(runner, "evaluate_dimensions", lambda baseline, candidate: [])
    monkeypatch.setattr(runner, "build_opportunity", lambda *args: None)
    monkeypatch.setattr(runner, "needs_human_review", lambda dimensions: False)
    monkeypatch.setattr(runner, "save_run_artifact", lambda completed: None)
    run = EvaluationRun(id="test-run", case_id="case-1", state=RunState.IDLE)

    runner.execute_case1(run)

    assert received == [selection, selection]
    assert received[0] is received[1]
    assert run.metadata == {"model_provider": "openai", "model_id": "openai-model"}
