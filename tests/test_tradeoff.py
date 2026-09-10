from core.compare import build_opportunity, is_tradeoff, needs_human_review
from core.schemas import ChangeStatus, DimensionResult


def dimension(name: str, status: ChangeStatus) -> DimensionResult:
    return DimensionResult(name=name, status=status, reason="test", evidence=[])


def test_tradeoff_requires_improvement_and_regression():
    dimensions = [
        dimension("Policy Safety", ChangeStatus.IMPROVED),
        dimension("Helpfulness", ChangeStatus.REGRESSED),
    ]
    assert is_tradeoff(dimensions)
    assert needs_human_review(dimensions)


def test_stable_results_do_not_create_opportunity():
    dimensions = [dimension("Policy Safety", ChangeStatus.STABLE)]
    assert build_opportunity("case-1", {}, {}, dimensions) is None
    assert not needs_human_review(dimensions)


def test_uncertain_critical_evidence_creates_review_opportunity():
    dimensions = [dimension("Policy Safety", ChangeStatus.UNCERTAIN)]
    opportunity = build_opportunity("case-1", {}, {}, dimensions)
    assert opportunity is not None
    assert opportunity.human_review

