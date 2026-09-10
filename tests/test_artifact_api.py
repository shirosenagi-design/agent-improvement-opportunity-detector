import json
import os
from pathlib import Path
import time
from uuid import uuid4

from fastapi.testclient import TestClient

import app as app_module
import core.artifacts as artifacts


client = TestClient(app_module.app)


def artifact_payload(run_id: str, title: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "timestamp": "2026-09-07T22:36:55Z",
        "case_id": "case-1",
        "state": "opportunities_found",
        "provider": "saved-provider",
        "model_id": "saved-model",
        "baseline_responses": {
            "probe-a": "saved baseline",
            "probe-b": "saved allowed value",
        },
        "candidate_responses": {
            "probe-a": "saved candidate",
            "probe-b": "saved refusal",
        },
        "dimensions": [
            {
                "name": "Saved dimension",
                "status": "REGRESSED",
                "reason": "Saved reason",
                "evidence": [
                    {
                        "probe_id": "probe-a",
                        "source": "candidate",
                        "excerpt": "Saved excerpt",
                        "rule": "Saved rule",
                    }
                ],
            }
        ],
        "trade_off_detected": True,
        "opportunity": {
            "id": "saved-opportunity",
            "title": title,
            "summary": "Saved summary",
            "case_id": "case-1",
            "baseline_responses": {"probe-a": "saved baseline"},
            "candidate_responses": {"probe-a": "saved candidate"},
            "dimensions": [],
            "what_improved": ["Saved improvement"],
            "what_regressed": ["Saved regression"],
            "evidence": [],
            "human_review": True,
            "review_reason": "Saved review reason",
        },
        "human_review": True,
        "error": None,
    }


def case3_artifact_payload(run_id: str) -> dict[str, object]:
    responses = {
        "baseline": {
            "condition-a": "Baseline response A",
            "condition-b": "Baseline response B",
        },
        "candidate": {
            "condition-a": "Candidate response A",
            "condition-b": "Candidate response B",
        },
    }
    evidence = []
    for arm in ("baseline", "candidate"):
        for condition_id in ("condition-a", "condition-b"):
            record = {
                "record_type": "case3-invocation",
                "observation_id": f"{arm}:{condition_id}",
                "arm": arm,
                "condition_id": condition_id,
                "relationship_context": f"Runtime context {condition_id}",
                "context_delivery_path": "build_agent.context",
                "tools_absent": True,
                "provenance_valid": True,
                "response_shape": {
                    "step_count": 3,
                    "plan_density": 1.5,
                    "simultaneous_demand_count": 2,
                    "first_action_small": condition_id == "condition-b",
                    "first_action_word_count": 6,
                    "optionalized": condition_id == "condition-b",
                    "agency_preserved": condition_id == "condition-b",
                    "detailed_multi_step": condition_id == "condition-a",
                    "single_small_action": condition_id == "condition-b",
                },
            }
            evidence.append(
                {
                    "probe_id": condition_id,
                    "source": arm,
                    "excerpt": json.dumps(record, sort_keys=True),
                    "rule": "Runtime-captured Case 3 provenance.",
                }
            )
    comparison = {
        "record_type": "standardization-comparison",
        "observation_refs": [
            "baseline:condition-a",
            "baseline:condition-b",
            "candidate:condition-a",
            "candidate:condition-b",
        ],
        "baseline_shape_distance": 8,
        "candidate_shape_distance": 0,
        "baseline_shape_divergence": True,
        "candidate_shape_convergence": True,
        "standardization_collapse": True,
    }
    evidence.append(
        {
            "probe_id": "cross-condition-shape",
            "source": "comparison",
            "excerpt": json.dumps(comparison, sort_keys=True),
            "rule": "standardization_collapse=true.",
        }
    )
    dimensions = [
        {"name": name, "status": status, "reason": name, "evidence": items}
        for name, status, items in (
            ("Task Completion / Plan Completeness", "IMPROVED", []),
            ("Human Consideration", "REGRESSED", []),
            ("Relationship-specific Adaptation", "REGRESSED", evidence),
        )
    ]
    payload = artifact_payload(run_id, "Saved Case 3 opportunity")
    payload.update(
        case_id="case-3",
        baseline_responses=responses["baseline"],
        candidate_responses=responses["candidate"],
        dimensions=dimensions,
    )
    payload["opportunity"]["case_id"] = "case-3"
    return payload


def write_artifact(directory, payload: dict[str, object]):
    path = directory / f"{payload['run_id']}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_gets_specified_saved_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUN_ARTIFACT_DIR", tmp_path)
    run_id = str(uuid4())
    payload = artifact_payload(run_id, "Specified saved opportunity")
    write_artifact(tmp_path, payload)

    response = client.get(f"/api/artifacts/runs/{run_id}")

    assert response.status_code == 200
    assert response.json() == payload


def test_gets_latest_uuid_named_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUN_ARTIFACT_DIR", tmp_path)
    older = artifact_payload(str(uuid4()), "Older")
    newer = artifact_payload(str(uuid4()), "Newer")
    older_path = write_artifact(tmp_path, older)
    newer_path = write_artifact(tmp_path, newer)
    decoy = tmp_path / "not-a-run.json"
    decoy.write_text("{}", encoding="utf-8")
    now = time.time_ns()
    os.utime(older_path, ns=(now - 2_000_000, now - 2_000_000))
    os.utime(newer_path, ns=(now - 1_000_000, now - 1_000_000))
    os.utime(decoy, ns=(now, now))

    response = client.get("/api/artifacts/runs/latest")

    assert response.status_code == 200
    assert response.json() == newer


def test_valid_uuid_missing_artifact_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUN_ARTIFACT_DIR", tmp_path)

    response = client.get(f"/api/artifacts/runs/{uuid4()}")

    assert response.status_code == 404


def test_invalid_uuid_and_path_traversal_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUN_ARTIFACT_DIR", tmp_path)
    outside_run_id = str(uuid4())
    outside_payload = artifact_payload(outside_run_id, "Outside")
    write_artifact(tmp_path.parent, outside_payload)

    invalid_response = client.get("/api/artifacts/runs/not-a-uuid")
    traversal_response = client.get(
        f"/api/artifacts/runs/%2E%2E%2F{outside_run_id}",
        follow_redirects=False,
    )

    assert invalid_response.status_code == 400
    assert traversal_response.status_code in {400, 404}


def test_api_returns_artifact_exactly_without_recalculation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUN_ARTIFACT_DIR", tmp_path)
    run_id = str(uuid4())
    payload = artifact_payload(run_id, "<saved & untrusted>")
    payload["provider"] = "<provider-from-artifact>"
    payload["model_id"] = "model & exact"
    write_artifact(tmp_path, payload)

    response = client.get(f"/api/artifacts/runs/{run_id}")

    assert response.status_code == 200
    assert response.json() == payload


def test_latest_returns_404_when_no_uuid_artifact_exists(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUN_ARTIFACT_DIR", tmp_path)
    (tmp_path / "not-a-run.json").write_text("{}", encoding="utf-8")

    response = client.get("/api/artifacts/runs/latest")

    assert response.status_code == 404


def test_artifact_rendering_uses_safe_dom_and_query_gated_restore():
    javascript = Path("static/app.js").read_text(encoding="utf-8")

    assert "innerHTML" not in javascript
    assert "textContent" in javascript
    assert "if (initialRunId)" in javascript
    assert "/api/artifacts/runs/latest" not in javascript


def test_case2_rendering_uses_one_decision_pair_and_case_labels():
    javascript = Path("static/app.js").read_text(encoding="utf-8")
    html = Path("templates/index.html").read_text(encoding="utf-8")

    assert "if (artifact.case_id === 'case-2')" in javascript
    assert "valueAt(baseline, 'decision')" in javascript
    assert "valueAt(candidate, 'decision')" in javascript
    assert "Case 2 — Memory Provenance vs Causality" in javascript
    assert 'id="baseline-agent-label"' in html
    assert 'id="candidate-agent-label"' in html
    assert 'id="case-suite-label"' in html


def test_case3_artifact_is_returned_without_ui_or_api_transformation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUN_ARTIFACT_DIR", tmp_path)
    payload = case3_artifact_payload(str(uuid4()))
    write_artifact(tmp_path, payload)

    response = client.get(f"/api/artifacts/runs/{payload['run_id']}")

    assert response.status_code == 200
    assert response.json() == payload


def test_case3_has_distinct_condition_and_dimension_mapping():
    javascript = Path("static/app.js").read_text(encoding="utf-8")

    assert "'case-3'" in javascript
    assert "else if (artifact.case_id === 'case-3')" in javascript
    assert "Case 3 — One Response Does Not Fit Everyone" in javascript
    assert "Relationship Condition A" in javascript
    assert "Relationship Condition B" in javascript
    assert "valueAt(baseline, 'condition-a')" in javascript
    assert "valueAt(candidate, 'condition-a')" in javascript
    assert "valueAt(baseline, 'condition-b')" in javascript
    assert "valueAt(candidate, 'condition-b')" in javascript
    case3_branch = javascript.split(
        "else if (artifact.case_id === 'case-3')", 1
    )[1].split("} else {", 1)[0]
    assert "Probe A" not in case3_branch
    assert "Probe B" not in case3_branch
    for dimension_name in (
        "Task Completion / Plan Completeness",
        "Human Consideration",
        "Relationship-specific Adaptation",
    ):
        assert dimension_name in javascript


def test_case3_structured_evidence_mapping_is_safe_and_has_fallback():
    javascript = Path("static/app.js").read_text(encoding="utf-8")

    for token in (
        "JSON.parse",
        "record_type",
        "case3-invocation",
        "relationship_context",
        "context_delivery_path",
        "tools_absent",
        "provenance_valid",
        "response_shape",
        "baseline_shape_divergence",
        "candidate_shape_convergence",
        "standardization_collapse",
    ):
        assert token in javascript
    assert "return null" in javascript
    assert "structured || evidenceItem(item)" in javascript
    assert "innerHTML" not in javascript
    assert "textContent" in javascript


def test_narrow_layout_keeps_header_hedgehog_without_handwritten_note():
    stylesheet = Path("static/styles.css").read_text(encoding="utf-8")

    assert ".header-note { display: none; }" not in stylesheet
    assert ".same-goal-note { display: none; }" in stylesheet
    assert "grid-template-columns: minmax(0, 1fr) auto;" in stylesheet
