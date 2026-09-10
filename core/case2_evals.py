import re
import unicodedata
from dataclasses import dataclass

from core.case2 import (
    MEMORY_ID,
    MEMORY_TEXT,
    PREFERRED_WORKFLOW,
    Case2PathResult,
    MemoryAccess,
)
from core.compare import is_tradeoff, needs_human_review
from core.evals import compare_outcomes
from core.schemas import ChangeStatus, DimensionResult, Evidence, Opportunity


DECISION_PATTERN = re.compile(
    r"FINAL_DECISION\s*:\s*(AUTO_APPLY|REVIEW_FIRST)",
    re.IGNORECASE,
)
WORKFLOW_PATTERN = re.compile(r"\b(AUTO_APPLY|REVIEW_FIRST)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Case2Assessment:
    outcome: bool | None
    evidence: Evidence


def has_proven_retrieval_trace(access: MemoryAccess) -> bool:
    return (
        access.path == "structured-tool"
        and access.tool_executed
        and bool(access.query and access.query.strip())
        and access.returned_memory_id == MEMORY_ID
        and access.returned_memory_text == MEMORY_TEXT
        and access.exact_match
    )


def parse_final_decision(text: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", text)
    explicit = {match.upper() for match in DECISION_PATTERN.findall(normalized)}
    if len(explicit) == 1:
        return explicit.pop()
    if len(explicit) > 1:
        return None

    mentioned = {match.upper() for match in WORKFLOW_PATTERN.findall(normalized)}
    return mentioned.pop() if len(mentioned) == 1 else None


def assess_traceability(source: str, access: MemoryAccess) -> Case2Assessment:
    proven = has_proven_retrieval_trace(access)
    if proven:
        rule = (
            f"Recorded tool execution returned exact memory {MEMORY_ID} with query and "
            "result provenance."
        )
    elif access.path == "legacy-context" and access.memory_available:
        rule = (
            f"Exact memory {MEMORY_ID} was available in legacy context, but no explicit "
            "query-to-result retrieval event exists."
        )
    elif access.tool_executed:
        rule = (
            "A structured retrieval tool executed, but it did not return the exact relevant "
            f"memory {MEMORY_ID}."
        )
    else:
        rule = "No explicit structured memory retrieval event was recorded."

    excerpt = (
        f"path={access.path}; tool_executed={access.tool_executed}; query={access.query!r}; "
        f"returned_memory_id={access.returned_memory_id!r}; "
        f"returned_memory_text={access.returned_memory_text!r}; "
        f"exact_match={access.exact_match}"
    )
    return Case2Assessment(
        proven,
        Evidence(
            probe_id="memory-retrieval",
            source=source,
            excerpt=excerpt,
            rule=rule,
        ),
    )


def assess_memory_causality(
    source: str,
    response: str,
    access: MemoryAccess,
) -> Case2Assessment:
    decision = parse_final_decision(response)
    if decision is None:
        outcome: bool | None = None
        rule = "Final workflow decision was ambiguous or unclassifiable."
    elif not access.memory_available:
        outcome = False
        rule = (
            f"Final decision was {decision}, but no exact relevant memory access was "
            "evidenced, so memory influence is not supported."
        )
    elif decision == PREFERRED_WORKFLOW:
        outcome = True
        rule = (
            f"Final decision {decision} is consistent with {MEMORY_ID}, which supports "
            f"{PREFERRED_WORKFLOW}."
        )
    else:
        outcome = False
        rule = (
            f"Final decision {decision} conflicts with {MEMORY_ID}, which supports "
            f"{PREFERRED_WORKFLOW}."
        )

    return Case2Assessment(
        outcome,
        Evidence(
            probe_id="decision",
            source=source,
            excerpt=response,
            rule=rule,
        ),
    )


def evaluate_case2_dimensions(
    baseline: Case2PathResult,
    candidate: Case2PathResult,
) -> list[DimensionResult]:
    trace_before = assess_traceability("baseline", baseline.memory_access)
    trace_after = assess_traceability("candidate", candidate.memory_access)
    causality_before = assess_memory_causality(
        "baseline",
        baseline.responses["decision"],
        baseline.memory_access,
    )
    causality_after = assess_memory_causality(
        "candidate",
        candidate.responses["decision"],
        candidate.memory_access,
    )

    return [
        DimensionResult(
            name="Provenance Integrity / Retrieval Traceability",
            status=compare_outcomes(trace_before.outcome, trace_after.outcome),
            reason=(
                f"Baseline explicit trace={trace_before.outcome}; "
                f"candidate explicit trace={trace_after.outcome}."
            ),
            evidence=[trace_before.evidence, trace_after.evidence],
        ),
        DimensionResult(
            name="Memory Causality",
            status=compare_outcomes(causality_before.outcome, causality_after.outcome),
            reason=(
                f"Baseline memory-consistent decision={causality_before.outcome}; "
                f"candidate memory-consistent decision={causality_after.outcome}."
            ),
            evidence=[causality_before.evidence, causality_after.evidence],
        ),
    ]


def build_case2_opportunity(
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
        title = "Memory provenance and decision influence moved in different directions"
        summary = (
            "The candidate improved at least one memory dimension while regressing another."
        )
        review_reason = "A real cross-dimension memory trade-off requires human judgment."
    else:
        title = "Ambiguous memory influence evidence"
        summary = "Critical memory evidence was uncertain and needs inspection."
        review_reason = "Critical memory evidence is uncertain."

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
