from core.schemas import ChangeStatus, DimensionResult, Opportunity


def is_tradeoff(dimensions: list[DimensionResult]) -> bool:
    has_improved = any(d.status == ChangeStatus.IMPROVED for d in dimensions)
    has_regressed = any(d.status == ChangeStatus.REGRESSED for d in dimensions)
    return has_improved and has_regressed


def needs_human_review(dimensions: list[DimensionResult]) -> bool:
    return is_tradeoff(dimensions) or any(d.status == ChangeStatus.UNCERTAIN for d in dimensions)


def build_opportunity(
    case_id: str,
    baseline: dict[str, str],
    candidate: dict[str, str],
    dimensions: list[DimensionResult],
) -> Opportunity | None:
    tradeoff = is_tradeoff(dimensions)
    uncertain = any(d.status == ChangeStatus.UNCERTAIN for d in dimensions)
    if not (tradeoff or uncertain):
        return None
    improved = [d.name for d in dimensions if d.status == ChangeStatus.IMPROVED]
    regressed = [d.name for d in dimensions if d.status == ChangeStatus.REGRESSED]
    evidence = [item for dimension in dimensions for item in dimension.evidence]
    if tradeoff:
        title = "Over-refusal after account-safety update"
        summary = "The candidate improved at least one dimension while regressing another."
        review_reason = "A real cross-dimension trade-off requires human value judgment."
    else:
        title = "Ambiguous evidence after account-safety update"
        summary = "Critical evidence was uncertain and needs inspection."
        review_reason = "Critical evidence is uncertain."
    return Opportunity(
        id=f"{case_id}-opportunity",
        title=title,
        summary=summary,
        case_id=case_id,
        baseline_responses=baseline,
        candidate_responses=candidate,
        dimensions=dimensions,
        what_improved=improved,
        what_regressed=regressed,
        evidence=evidence,
        human_review=needs_human_review(dimensions),
        review_reason=review_reason,
    )

