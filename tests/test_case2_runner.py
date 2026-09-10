import json
from uuid import uuid4

import core.agents as agents
import core.runner as runner
from core.artifacts import build_run_artifact
from core.case2 import (
    CASE_2,
    MEMORY_ID,
    Case2PathResult,
    RetrievalRecorder,
    build_memory_retrieval_tool,
    legacy_memory_access,
    render_memory_access,
)
from core.cases import CUSTOMER_CONTEXT
from core.schemas import ChangeStatus, EvaluationRun, RunState


def path_result(access, decision: str) -> Case2PathResult:
    return Case2PathResult(
        responses={
            "memory-access": render_memory_access(access),
            "decision": decision,
        },
        memory_access=access,
    )


def test_case2_runner_reuses_selection_and_persists_existing_schema(
    monkeypatch,
):
    selection = agents.ModelSelection(provider="openai", model_id="mock-model")
    baseline = path_result(
        legacy_memory_access(),
        "FINAL_DECISION: REVIEW_FIRST\nPreserve final approval.",
    )
    recorder = RetrievalRecorder()
    build_memory_retrieval_tool(recorder)(
        query="workflow review approval preference"
    )
    candidate = path_result(
        recorder.observed_access(),
        "FINAL_DECISION: AUTO_APPLY\nGeneric efficiency is primary.",
    )
    received = []
    saved = {}

    def fake_baseline(selected):
        received.append(selected)
        return baseline

    def fake_candidate(selected):
        received.append(selected)
        return candidate

    def capture_artifact(completed):
        saved.update(build_run_artifact(completed))

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-secret")
    monkeypatch.setenv("PROJECT04_OPENAI_API_KEY", "source-unit-test-secret")
    monkeypatch.setattr(runner, "resolve_model_selection", lambda: selection)
    monkeypatch.setattr(runner, "run_case2_baseline", fake_baseline)
    monkeypatch.setattr(runner, "run_case2_candidate", fake_candidate)
    monkeypatch.setattr(runner, "save_run_artifact", capture_artifact)
    run = EvaluationRun(
        id=str(uuid4()),
        case_id=CASE_2.id,
        state=RunState.IDLE,
    )

    runner.execute_case2(run)

    assert received == [selection, selection]
    assert received[0] is received[1]
    assert run.state == RunState.OPPORTUNITIES_FOUND
    assert run.model_id == "mock-model"
    assert run.metadata == {
        "model_provider": "openai",
        "model_id": "mock-model",
    }
    assert [dimension.status for dimension in run.dimensions] == [
        ChangeStatus.IMPROVED,
        ChangeStatus.REGRESSED,
    ]
    assert run.human_review is True

    assert set(saved) == {
        "run_id",
        "timestamp",
        "case_id",
        "state",
        "provider",
        "model_id",
        "baseline_responses",
        "candidate_responses",
        "dimensions",
        "trade_off_detected",
        "opportunity",
        "human_review",
        "error",
    }
    assert saved["case_id"] == CASE_2.id
    assert saved["provider"] == "openai"
    assert saved["model_id"] == "mock-model"
    assert saved["baseline_responses"] == baseline.responses
    assert saved["candidate_responses"] == candidate.responses
    assert saved["trade_off_detected"] is True
    assert saved["human_review"] is True

    evidence = [
        item
        for dimension in saved["dimensions"]
        for item in dimension["evidence"]
    ]
    assert {item["probe_id"] for item in evidence} == {
        "memory-retrieval",
        "decision",
    }
    assert any(MEMORY_ID in item["excerpt"] for item in evidence)
    assert any(
        "FINAL_DECISION: AUTO_APPLY" in item["excerpt"]
        for item in evidence
    )

    serialized = json.dumps(saved, ensure_ascii=False)
    assert "OPENAI_API_KEY" not in serialized
    assert "PROJECT04_OPENAI_API_KEY" not in serialized
    assert "unit-test-secret" not in serialized
    assert "source-unit-test-secret" not in serialized


def test_build_agent_keeps_case1_default_context_and_no_tools(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        agents,
        "Agent",
        lambda **kwargs: captured.update(kwargs) or object(),
    )

    agents.build_agent(
        "case-one-system",
        agents.ModelSelection(provider="bedrock", model_id=None),
    )

    assert captured["system_prompt"] == (
        f"case-one-system\n\n{CUSTOMER_CONTEXT}"
    )
    assert "tools" not in captured
    assert "model" not in captured
