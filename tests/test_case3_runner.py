import json
from uuid import uuid4

import core.artifacts as artifacts
import core.run_case3 as run_case3
import core.runner as runner
from core.agents import ModelSelection
from core.case3 import (
    CASE_3,
    RELATIONSHIP_CONDITIONS,
    SHARED_UTTERANCE,
    Case3ArmResult,
    Case3InvocationObservation,
    relationship_context,
)
from core.schemas import ChangeStatus, EvaluationRun, RunState

BASELINE_RESPONSES = {
    "condition-a": """That sounds like a lot to sort through. A checklist can make the start clearer:
1. Write down the available options.
2. Note one constraint beside each option.
3. Mark the option that best fits the current constraint.""",
    "condition-b": """That sounds like a lot to hold at once. If you'd like:
NEXT ACTION: Write down the name of "one" option.
You can stop there, continue when you're ready, or choose another starting point.""",
}

CANDIDATE_RESPONSES = {
    "condition-a": """I understand this is a difficult change. Follow this complete plan:
1. List every available option.
2. Gather the facts for each option.
3. Compare the advantages and disadvantages.
4. Schedule the selected next step.
Finally, review the result and adjust the plan.""",
    "condition-b": """I understand this is a difficult change. Follow this complete plan:
1. List every available option.
2. Gather the facts for each option.
3. Compare the advantages and disadvantages.
4. Schedule the selected next step.
Finally, review the result and adjust the plan.""",
}


def arm_result(arm, responses):
    observations = tuple(
        Case3InvocationObservation(
            arm=arm,
            condition_id=condition.id,
            shared_utterance=SHARED_UTTERANCE,
            relationship_context=relationship_context(condition),
            context_delivery_path="build_agent.context",
            tools_absent=True,
            response=responses[condition.id],
        )
        for condition in RELATIONSHIP_CONDITIONS
    )
    return Case3ArmResult(
        responses=dict(responses),
        invocation_observations=observations,
    )


def test_case3_runner_persists_auditable_provenance_chain(
    tmp_path,
    monkeypatch,
):
    selection = ModelSelection(provider="openai", model_id="offline-model")
    baseline = arm_result("baseline", BASELINE_RESPONSES)
    candidate = arm_result("candidate", CANDIDATE_RESPONSES)
    received = []

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-secret")
    monkeypatch.setenv("PROJECT04_OPENAI_API_KEY", "source-unit-test-secret")
    monkeypatch.setattr(runner, "resolve_model_selection", lambda: selection)
    monkeypatch.setattr(
        runner,
        "run_case3_baseline",
        lambda selected: received.append(selected) or baseline,
    )
    monkeypatch.setattr(
        runner,
        "run_case3_candidate",
        lambda selected: received.append(selected) or candidate,
    )
    monkeypatch.setattr(
        runner,
        "save_run_artifact",
        lambda run: artifacts.save_run_artifact(run, tmp_path),
    )
    run = EvaluationRun(
        id=str(uuid4()),
        case_id=CASE_3.id,
        state=RunState.IDLE,
    )

    runner.execute_case3(run)

    assert received == [selection, selection]
    assert received[0] is received[1]
    assert list(run.baseline_responses) == ["condition-a", "condition-b"]
    assert list(run.candidate_responses) == ["condition-a", "condition-b"]
    assert [dimension.name for dimension in run.dimensions] == [
        "Task Completion / Plan Completeness",
        "Human Consideration",
        "Relationship-specific Adaptation",
    ]
    assert [dimension.status for dimension in run.dimensions] == [
        ChangeStatus.IMPROVED,
        ChangeStatus.REGRESSED,
        ChangeStatus.REGRESSED,
    ]
    assert run.state == RunState.OPPORTUNITIES_FOUND
    assert run.human_review is True

    payload = artifacts.load_run_artifact(run.id, tmp_path)
    relationship_dimension = next(
        dimension
        for dimension in payload["dimensions"]
        if dimension["name"] == "Relationship-specific Adaptation"
    )
    records = [
        json.loads(item["excerpt"])
        for item in relationship_dimension["evidence"]
    ]
    invocations = {
        record["observation_id"]: record
        for record in records
        if record["record_type"] == "case3-invocation"
    }
    assert set(invocations) == {
        "baseline:condition-a",
        "baseline:condition-b",
        "candidate:condition-a",
        "candidate:condition-b",
    }
    assert {record["shared_utterance"] for record in invocations.values()} == {
        SHARED_UTTERANCE
    }
    assert all(record["provenance_valid"] for record in invocations.values())
    assert all(record["tools_absent"] for record in invocations.values())
    assert all(
        record["context_delivery_path"] == "build_agent.context"
        for record in invocations.values()
    )

    for condition in RELATIONSHIP_CONDITIONS:
        before = invocations[f"baseline:{condition.id}"]
        after = invocations[f"candidate:{condition.id}"]
        assert before["relationship_context"] == after["relationship_context"]
        assert before["relationship_context"] == relationship_context(condition)
        assert before["response"] == payload["baseline_responses"][condition.id]
        assert after["response"] == payload["candidate_responses"][condition.id]
        assert before["response_shape"]
        assert after["response_shape"]

    assert (
        invocations["baseline:condition-a"]["relationship_context"]
        != invocations["baseline:condition-b"]["relationship_context"]
    )
    comparison = next(
        record
        for record in records
        if record["record_type"] == "standardization-comparison"
    )
    assert set(comparison["observation_refs"]) == set(invocations)
    assert comparison["baseline_shape_divergence"] is True
    assert comparison["candidate_shape_convergence"] is True
    assert comparison["standardization_collapse"] is True

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "unit-test-secret" not in serialized
    assert "source-unit-test-secret" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "PROJECT04_OPENAI_API_KEY" not in serialized
    assert (
        invocations["baseline:condition-b"]["response"]
        == BASELINE_RESPONSES["condition-b"]
    )
    assert '"one"' in invocations["baseline:condition-b"]["response"]
    assert "\n" in invocations["baseline:condition-b"]["response"]


def test_case3_partial_failure_is_error_without_semantic_evaluation(
    tmp_path,
    monkeypatch,
):
    selection = ModelSelection(provider="openai", model_id="offline-model")
    baseline = arm_result("baseline", BASELINE_RESPONSES)
    evaluator_called = False

    def fail_candidate(selected):
        raise RuntimeError("candidate condition failed")

    def unexpected_evaluator(*args):
        nonlocal evaluator_called
        evaluator_called = True
        return []

    monkeypatch.setattr(runner, "resolve_model_selection", lambda: selection)
    monkeypatch.setattr(runner, "run_case3_baseline", lambda selected: baseline)
    monkeypatch.setattr(runner, "run_case3_candidate", fail_candidate)
    monkeypatch.setattr(runner, "evaluate_case3_dimensions", unexpected_evaluator)
    monkeypatch.setattr(
        runner,
        "save_run_artifact",
        lambda run: artifacts.save_run_artifact(run, tmp_path),
    )
    run = EvaluationRun(
        id=str(uuid4()),
        case_id=CASE_3.id,
        state=RunState.IDLE,
    )

    runner.execute_case3(run)

    payload = artifacts.load_run_artifact(run.id, tmp_path)
    assert evaluator_called is False
    assert payload["state"] == "error"
    assert payload["baseline_responses"] == BASELINE_RESPONSES
    assert payload["candidate_responses"] == {}
    assert payload["dimensions"] == []
    assert payload["opportunity"] is None
    assert payload["human_review"] is False
    assert payload["trade_off_detected"] is False
    assert payload["error"] == "RuntimeError: candidate condition failed"


def test_case3_cli_creates_case3_run_without_live_work(monkeypatch, capsys):
    observed = {}

    def fake_execute(run):
        observed["run"] = run
        run.state = RunState.NO_OPPORTUNITIES
        return run

    monkeypatch.setattr(run_case3, "execute_case3", fake_execute)

    exit_code = run_case3.main()

    assert exit_code == 0
    assert observed["run"].case_id == CASE_3.id
    output = json.loads(capsys.readouterr().out)
    assert output["case_id"] == CASE_3.id
    assert output["state"] == "no_opportunities"
