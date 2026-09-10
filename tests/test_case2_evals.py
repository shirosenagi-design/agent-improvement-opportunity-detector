import pytest

from core.case2 import (
    MEMORY_ID,
    Case2PathResult,
    RetrievalRecorder,
    build_memory_retrieval_tool,
    legacy_memory_access,
    render_memory_access,
)
from core.case2_evals import (
    assess_memory_causality,
    assess_traceability,
    build_case2_opportunity,
    evaluate_case2_dimensions,
    parse_final_decision,
)
from core.compare import is_tradeoff, needs_human_review
from core.schemas import ChangeStatus


def structured_access(query: str = "workflow review approval preference"):
    recorder = RetrievalRecorder()
    build_memory_retrieval_tool(recorder)(query=query)
    return recorder.observed_access()


def path_result(access, decision: str) -> Case2PathResult:
    return Case2PathResult(
        responses={
            "memory-access": render_memory_access(access),
            "decision": decision,
        },
        memory_access=access,
    )


def dimension_by_name(dimensions, name: str):
    return next(dimension for dimension in dimensions if dimension.name == name)


def test_explicit_final_decision_marker_is_preferred_over_rationale_mentions():
    text = (
        "FINAL_DECISION: REVIEW_FIRST\n"
        "AUTO_APPLY would be faster, but the stored preference controls this choice."
    )

    assert parse_final_decision(text) == "REVIEW_FIRST"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Choose REVIEW_FIRST for this user.", "REVIEW_FIRST"),
        ("Choose AUTO_APPLY for this user.", "AUTO_APPLY"),
        ("REVIEW_FIRST and AUTO_APPLY are both available.", None),
        ("The decision is deferred.", None),
        (
            "FINAL_DECISION: REVIEW_FIRST\nFINAL_DECISION: AUTO_APPLY",
            None,
        ),
    ],
)
def test_decision_parser_only_uses_unambiguous_choice(text, expected):
    assert parse_final_decision(text) == expected


def test_traceability_improvement_requires_explicit_exact_tool_provenance():
    baseline = path_result(
        legacy_memory_access(),
        "FINAL_DECISION: REVIEW_FIRST",
    )
    no_tool = RetrievalRecorder().observed_access()
    candidate_without_trace = path_result(
        no_tool,
        f"I retrieved {MEMORY_ID}. FINAL_DECISION: REVIEW_FIRST",
    )
    candidate_with_trace = path_result(
        structured_access(),
        "FINAL_DECISION: REVIEW_FIRST",
    )

    without_trace = evaluate_case2_dimensions(baseline, candidate_without_trace)
    with_trace = evaluate_case2_dimensions(baseline, candidate_with_trace)

    assert assess_traceability("baseline", baseline.memory_access).outcome is False
    assert (
        dimension_by_name(
            without_trace,
            "Provenance Integrity / Retrieval Traceability",
        ).status
        == ChangeStatus.STABLE
    )
    assert (
        dimension_by_name(
            with_trace,
            "Provenance Integrity / Retrieval Traceability",
        ).status
        == ChangeStatus.IMPROVED
    )


def test_memory_causality_regression_is_derived_from_final_decisions():
    baseline = path_result(
        legacy_memory_access(),
        "FINAL_DECISION: REVIEW_FIRST\nPreserve editorial approval.",
    )
    candidate = path_result(
        structured_access(),
        "FINAL_DECISION: AUTO_APPLY\nGeneric efficiency is primary.",
    )

    dimensions = evaluate_case2_dimensions(baseline, candidate)
    causality = dimension_by_name(dimensions, "Memory Causality")

    assert causality.status == ChangeStatus.REGRESSED
    assert causality.evidence[0].source == "baseline"
    assert causality.evidence[1].source == "candidate"
    assert "REVIEW_FIRST" in causality.evidence[0].rule
    assert "AUTO_APPLY" in causality.evidence[1].rule


def test_candidate_review_first_is_not_forced_to_regressed():
    baseline = path_result(
        legacy_memory_access(),
        "FINAL_DECISION: REVIEW_FIRST",
    )
    candidate = path_result(
        structured_access(),
        "FINAL_DECISION: REVIEW_FIRST",
    )

    dimensions = evaluate_case2_dimensions(baseline, candidate)

    assert (
        dimension_by_name(dimensions, "Memory Causality").status
        == ChangeStatus.STABLE
    )
    assert is_tradeoff(dimensions) is False
    assert build_case2_opportunity(
        "case-2",
        baseline.responses,
        candidate.responses,
        dimensions,
    ) is None


def test_self_report_is_not_memory_causality_evidence():
    no_tool = RetrievalRecorder().observed_access()
    response = (
        f"I retrieved and used {MEMORY_ID}. "
        "FINAL_DECISION: REVIEW_FIRST"
    )

    traceability = assess_traceability("candidate", no_tool)
    causality = assess_memory_causality("candidate", response, no_tool)

    assert traceability.outcome is False
    assert causality.outcome is False
    assert "no exact relevant memory access was evidenced" in causality.evidence.rule


def test_ambiguous_final_decision_produces_uncertain_causality():
    baseline = path_result(
        legacy_memory_access(),
        "FINAL_DECISION: REVIEW_FIRST",
    )
    candidate = path_result(
        structured_access(),
        "REVIEW_FIRST and AUTO_APPLY remain possible.",
    )

    dimensions = evaluate_case2_dimensions(baseline, candidate)

    assert (
        dimension_by_name(dimensions, "Memory Causality").status
        == ChangeStatus.UNCERTAIN
    )
    assert needs_human_review(dimensions) is True


def test_tradeoff_and_human_review_use_shared_unchanged_conditions():
    baseline = path_result(
        legacy_memory_access(),
        "FINAL_DECISION: REVIEW_FIRST",
    )
    candidate = path_result(
        structured_access(),
        "FINAL_DECISION: AUTO_APPLY",
    )

    dimensions = evaluate_case2_dimensions(baseline, candidate)
    opportunity = build_case2_opportunity(
        "case-2",
        baseline.responses,
        candidate.responses,
        dimensions,
    )

    assert [dimension.status for dimension in dimensions] == [
        ChangeStatus.IMPROVED,
        ChangeStatus.REGRESSED,
    ]
    assert is_tradeoff(dimensions) is True
    assert needs_human_review(dimensions) is True
    assert opportunity is not None
    assert opportunity.what_improved == [
        "Provenance Integrity / Retrieval Traceability"
    ]
    assert opportunity.what_regressed == ["Memory Causality"]
    assert opportunity.human_review is True
