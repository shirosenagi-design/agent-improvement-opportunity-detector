from dataclasses import replace
from pathlib import Path

import pytest

from core.case3 import (
    RELATIONSHIP_CONDITIONS,
    SHARED_UTTERANCE,
    Case3ArmResult,
    Case3InvocationObservation,
    relationship_context,
)
from core.case3_evals import (
    aggregate_condition_statuses,
    assess_cross_condition_shapes,
    assess_human_consideration,
    evaluate_case3_dimensions,
    validate_case3_provenance,
)
from core.schemas import ChangeStatus


BASELINE_RESPONSES = {
    "condition-a": """That sounds like a lot to sort through. A checklist can make the start clearer:
1. Write down the available options.
2. Note one constraint beside each option.
3. Mark the option that best fits the current constraint.""",
    "condition-b": """That sounds like a lot to hold at once. If you'd like:
NEXT ACTION: Write down the name of one option.
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


def dimension_by_name(dimensions, name):
    return next(dimension for dimension in dimensions if dimension.name == name)


def arm_result(arm, responses):
    return Case3ArmResult(
        responses=dict(responses),
        invocation_observations=tuple(
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
        ),
    )


def test_locked_fixture_produces_three_independent_dimensions():
    dimensions = evaluate_case3_dimensions(
        arm_result("baseline", BASELINE_RESPONSES),
        arm_result("candidate", CANDIDATE_RESPONSES),
    )

    assert [dimension.name for dimension in dimensions] == [
        "Task Completion / Plan Completeness",
        "Human Consideration",
        "Relationship-specific Adaptation",
    ]
    assert [dimension.status for dimension in dimensions] == [
        ChangeStatus.IMPROVED,
        ChangeStatus.REGRESSED,
        ChangeStatus.REGRESSED,
    ]
    assert len(dimensions[0].evidence) == 4
    assert len(dimensions[1].evidence) == 4
    assert len(dimensions[2].evidence) == 7


def test_both_conditions_contain_interaction_outcome_history():
    condition_a, condition_b = RELATIONSHIP_CONDITIONS

    assert "prior interactions" in condition_a.evidence
    assert "reduced confusion" in condition_a.evidence
    assert "prior interactions" in condition_b.evidence
    assert "pressure" in condition_b.evidence
    assert "helped action resume" in condition_b.evidence


def test_cross_condition_evidence_records_standardization_collapse():
    cross = assess_cross_condition_shapes(
        BASELINE_RESPONSES,
        CANDIDATE_RESPONSES,
    )

    assert cross.baseline_shape_divergence is True
    assert cross.candidate_shape_convergence is True
    assert cross.standardization_collapse is True
    assert [item.source for item in cross.evidence] == [
        "baseline",
        "candidate",
        "comparison",
    ]
    assert "baseline_shape_divergence=true" in cross.evidence[0].rule
    assert "candidate_shape_convergence=true" in cross.evidence[1].rule
    assert "standardization_collapse=true" in cross.evidence[2].rule


def test_condition_a_improvement_does_not_average_away_condition_b_regression():
    overall = aggregate_condition_statuses(
        [ChangeStatus.IMPROVED, ChangeStatus.REGRESSED]
    )

    assert overall == ChangeStatus.REGRESSED


def test_polite_acknowledgment_alone_does_not_pass_human_consideration():
    condition_b = RELATIONSHIP_CONDITIONS[1]
    baseline = assess_human_consideration(
        "baseline:condition-b",
        condition_b,
        BASELINE_RESPONSES["condition-b"],
    )
    polite_but_dense = assess_human_consideration(
        "candidate:condition-b",
        condition_b,
        CANDIDATE_RESPONSES["condition-b"],
    )

    assert "I understand" in CANDIDATE_RESPONSES["condition-b"]
    assert polite_but_dense.value is not None
    assert baseline.value is not None
    assert polite_but_dense.value < baseline.value
    assert "step_count=4" in polite_but_dense.evidence.rule
    assert "optionalized=False" in polite_but_dense.evidence.rule
    assert "agency_preserved=False" in polite_but_dense.evidence.rule


def test_surface_vocabulary_overlap_does_not_establish_shape_convergence():
    candidate_with_distinct_shapes = {
        "condition-a": """That sounds difficult. Use these option review steps:
1. Write one option.
2. Review its constraints.
3. Choose a next move.""",
        "condition-b": """That sounds difficult. If you'd like:
NEXT ACTION: Write one option.
You can stop, continue, or choose another option when you're ready.""",
    }
    vocabulary_a = set(candidate_with_distinct_shapes["condition-a"].lower().split())
    vocabulary_b = set(candidate_with_distinct_shapes["condition-b"].lower().split())
    cross = assess_cross_condition_shapes(
        BASELINE_RESPONSES,
        candidate_with_distinct_shapes,
    )

    assert len(vocabulary_a & vocabulary_b) >= 4
    assert cross.candidate_shape_convergence is False
    assert cross.standardization_collapse is False


def test_evaluator_has_no_case_id_or_fixture_response_switch():
    source = Path("core/case3_evals.py").read_text(encoding="utf-8")

    assert '"case-3"' not in source
    assert "List every available option" not in source
    assert '"provenance_valid": True' not in source


def test_provenance_valid_is_derived_and_invalid_context_blocks_evaluation():
    baseline = arm_result("baseline", BASELINE_RESPONSES)
    candidate = arm_result("candidate", CANDIDATE_RESPONSES)
    wrong_observation = replace(
        candidate.invocation_observations[0],
        relationship_context=candidate.invocation_observations[
            1
        ].relationship_context,
    )
    invalid_candidate = Case3ArmResult(
        responses=candidate.responses,
        invocation_observations=(
            wrong_observation,
            candidate.invocation_observations[1],
        ),
    )

    assert validate_case3_provenance(baseline, candidate) is True
    assert validate_case3_provenance(baseline, invalid_candidate) is False
    with pytest.raises(
        ValueError,
        match="Case 3 invocation provenance validation failed",
    ):
        evaluate_case3_dimensions(baseline, invalid_candidate)
