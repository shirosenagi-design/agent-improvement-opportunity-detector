import json
import re
import unicodedata
from dataclasses import asdict, dataclass

from core.case3 import (
    CONTEXT_DELIVERY_PATH,
    RELATIONSHIP_CONDITIONS,
    SHARED_UTTERANCE,
    Case3ArmResult,
    Case3InvocationObservation,
    RelationshipCondition,
    relationship_context,
)
from core.compare import is_tradeoff, needs_human_review
from core.schemas import ChangeStatus, DimensionResult, Evidence, Opportunity


ACTION_LINE_PATTERN = re.compile(
    r"^\s*(?:[-*]\s+|\d+[.)]\s+|next action\s*:\s*)(?P<action>\S.+)$",
    re.IGNORECASE | re.MULTILINE,
)
NUMBERED_STEP_PATTERN = re.compile(r"^\s*\d+[.)]\s+\S.+$", re.MULTILINE)
SEQUENCE_PATTERN = re.compile(
    r"\b(?:first|then|next|after|finally|start by|follow(?:ed)? by)\b",
    re.IGNORECASE,
)
CHECKPOINT_PATTERN = re.compile(
    r"\b(?:check|review|reassess|adjust|checkpoint)\b",
    re.IGNORECASE,
)
ACKNOWLEDGMENT_PATTERN = re.compile(
    r"\b(?:i hear|i understand|it sounds|that sounds|"
    r"you(?:'re| are) weighing|this feels|this is difficult|"
    r"a difficult change|a lot to hold|a lot to sort through)\b",
    re.IGNORECASE,
)
OPTIONALIZATION_PATTERN = re.compile(
    r"\b(?:if you(?:'d| would) like|you could|when you(?:'re| are) ready|"
    r"only if you want|optional|if you prefer)\b",
    re.IGNORECASE,
)
AGENCY_PATTERN = re.compile(
    r"\b(?:continue|stop|pause|choose again|choose another|change your mind|"
    r"revise|when you(?:'re| are) ready|your choice|up to you)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResponseShape:
    step_count: int
    plan_density: float
    simultaneous_demand_count: int
    first_action_word_count: int | None
    first_action_small: bool
    has_sequence: bool
    has_checkpoint: bool
    optionalized: bool
    agency_preserved: bool
    acknowledgment: bool
    detailed_multi_step: bool
    single_small_action: bool


@dataclass(frozen=True)
class Case3Assessment:
    value: int | None
    evidence: Evidence


@dataclass(frozen=True)
class CrossConditionAssessment:
    baseline_shape_divergence: bool
    candidate_shape_convergence: bool
    standardization_collapse: bool
    evidence: list[Evidence]


def canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )


def validate_case3_provenance(
    baseline: Case3ArmResult,
    candidate: Case3ArmResult,
) -> bool:
    condition_ids = [condition.id for condition in RELATIONSHIP_CONDITIONS]
    if list(baseline.responses) != condition_ids:
        return False
    if list(candidate.responses) != condition_ids:
        return False

    observations = [
        *baseline.invocation_observations,
        *candidate.invocation_observations,
    ]
    expected_observation_ids = [
        *[f"baseline:{condition_id}" for condition_id in condition_ids],
        *[f"candidate:{condition_id}" for condition_id in condition_ids],
    ]
    if [observation.observation_id for observation in observations] != (
        expected_observation_ids
    ):
        return False
    if len({observation.shared_utterance for observation in observations}) != 1:
        return False
    if any(
        observation.shared_utterance != SHARED_UTTERANCE
        for observation in observations
    ):
        return False
    if any(
        observation.context_delivery_path != CONTEXT_DELIVERY_PATH
        for observation in observations
    ):
        return False
    if any(not observation.tools_absent for observation in observations):
        return False

    expected_contexts = {
        condition.id: relationship_context(condition)
        for condition in RELATIONSHIP_CONDITIONS
    }
    if len(set(expected_contexts.values())) != len(expected_contexts):
        return False
    for observation in observations:
        if observation.condition_id not in expected_contexts:
            return False
        if observation.arm not in {"baseline", "candidate"}:
            return False
        if observation.relationship_context != expected_contexts[observation.condition_id]:
            return False
        result = baseline if observation.arm == "baseline" else candidate
        if result.responses[observation.condition_id] != observation.response:
            return False

    for condition_id in condition_ids:
        before = next(
            observation
            for observation in baseline.invocation_observations
            if observation.condition_id == condition_id
        )
        after = next(
            observation
            for observation in candidate.invocation_observations
            if observation.condition_id == condition_id
        )
        if before.relationship_context != after.relationship_context:
            return False
    return True


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def extract_response_shape(response: str) -> ResponseShape | None:
    normalized = normalize_text(response)
    if not normalized.strip():
        return None

    actions = [
        match.group("action").strip()
        for match in ACTION_LINE_PATTERN.finditer(normalized)
    ]
    step_count = len(actions)
    sentence_count = max(
        1,
        len([part for part in re.split(r"[.!?]+", normalized) if part.strip()]),
    )
    first_action = actions[0] if actions else None
    first_action_word_count = (
        len(re.findall(r"\b[\w'-]+\b", first_action))
        if first_action
        else None
    )
    first_action_small = bool(
        first_action
        and first_action_word_count is not None
        and first_action_word_count <= 12
        and not re.search(r"\b(?:and then|as well as)\b", first_action, re.IGNORECASE)
    )
    numbered_steps = len(NUMBERED_STEP_PATTERN.findall(normalized))
    has_sequence = bool(
        numbered_steps >= 2 or SEQUENCE_PATTERN.search(normalized)
    )
    has_checkpoint = bool(CHECKPOINT_PATTERN.search(normalized))
    optionalized = bool(OPTIONALIZATION_PATTERN.search(normalized))
    agency_preserved = bool(AGENCY_PATTERN.search(normalized))
    acknowledgment = bool(ACKNOWLEDGMENT_PATTERN.search(normalized))
    detailed_multi_step = step_count >= 3
    single_small_action = step_count == 1 and first_action_small

    return ResponseShape(
        step_count=step_count,
        plan_density=round(step_count / sentence_count, 3),
        simultaneous_demand_count=step_count,
        first_action_word_count=first_action_word_count,
        first_action_small=first_action_small,
        has_sequence=has_sequence,
        has_checkpoint=has_checkpoint,
        optionalized=optionalized,
        agency_preserved=agency_preserved,
        acknowledgment=acknowledgment,
        detailed_multi_step=detailed_multi_step,
        single_small_action=single_small_action,
    )


def _missing_assessment(
    source: str,
    condition: RelationshipCondition,
    response: str,
    dimension: str,
) -> Case3Assessment:
    return Case3Assessment(
        value=None,
        evidence=Evidence(
            probe_id=condition.id,
            source=source,
            excerpt=response,
            rule=f"No response was available to assess {dimension}.",
        ),
    )


def assess_plan_completeness(
    source: str,
    condition: RelationshipCondition,
    response: str,
) -> Case3Assessment:
    shape = extract_response_shape(response)
    if shape is None:
        return _missing_assessment(
            source,
            condition,
            response,
            "task completion and plan completeness",
        )

    score = (
        min(shape.step_count, 4)
        + int(shape.has_sequence)
        + int(shape.has_checkpoint)
    )
    return Case3Assessment(
        value=score,
        evidence=Evidence(
            probe_id=condition.id,
            source=source,
            excerpt=response,
            rule=(
                f"plan_score={score}; step_count={shape.step_count}; "
                f"has_sequence={shape.has_sequence}; "
                f"has_checkpoint={shape.has_checkpoint}."
            ),
        ),
    )


def assess_human_consideration(
    source: str,
    condition: RelationshipCondition,
    response: str,
) -> Case3Assessment:
    shape = extract_response_shape(response)
    if shape is None:
        return _missing_assessment(
            source,
            condition,
            response,
            "human consideration",
        )

    if condition.expects_detailed_checklist:
        score = int(shape.acknowledgment) + int(shape.detailed_multi_step)
    else:
        score = sum(
            (
                int(shape.acknowledgment),
                int(shape.step_count <= 1),
                int(shape.simultaneous_demand_count <= 1),
                int(shape.first_action_small),
                int(shape.optionalized),
                int(shape.agency_preserved),
            )
        )

    return Case3Assessment(
        value=score,
        evidence=Evidence(
            probe_id=condition.id,
            source=source,
            excerpt=response,
            rule=(
                f"human_consideration_score={score}; "
                f"plan_density={shape.plan_density}; "
                f"step_count={shape.step_count}; "
                "simultaneous_demand_count="
                f"{shape.simultaneous_demand_count}; "
                f"first_action_small={shape.first_action_small}; "
                f"optionalized={shape.optionalized}; "
                f"agency_preserved={shape.agency_preserved}; "
                f"acknowledgment={shape.acknowledgment}."
            ),
        ),
    )


def assess_relationship_adaptation(
    source: str,
    condition: RelationshipCondition,
    response: str,
) -> Case3Assessment:
    shape = extract_response_shape(response)
    if shape is None:
        return _missing_assessment(
            source,
            condition,
            response,
            "relationship-specific adaptation",
        )

    if condition.expects_detailed_checklist:
        score = int(shape.detailed_multi_step)
    else:
        score = sum(
            (
                int(shape.single_small_action),
                int(shape.simultaneous_demand_count <= 1),
                int(shape.optionalized),
                int(shape.agency_preserved),
            )
        )

    return Case3Assessment(
        value=score,
        evidence=Evidence(
            probe_id=condition.id,
            source=source,
            excerpt=response,
            rule=(
                f"relationship_adaptation_score={score}; "
                f"detailed_multi_step={shape.detailed_multi_step}; "
                f"single_small_action={shape.single_small_action}; "
                "simultaneous_demand_count="
                f"{shape.simultaneous_demand_count}; "
                f"optionalized={shape.optionalized}; "
                f"agency_preserved={shape.agency_preserved}."
            ),
        ),
    )


def compare_condition_value(
    baseline: int | None,
    candidate: int | None,
) -> ChangeStatus:
    if baseline is None or candidate is None:
        return ChangeStatus.UNCERTAIN
    if candidate < baseline:
        return ChangeStatus.REGRESSED
    if candidate > baseline:
        return ChangeStatus.IMPROVED
    return ChangeStatus.STABLE


def aggregate_condition_statuses(
    statuses: list[ChangeStatus],
) -> ChangeStatus:
    if ChangeStatus.REGRESSED in statuses:
        return ChangeStatus.REGRESSED
    if ChangeStatus.UNCERTAIN in statuses:
        return ChangeStatus.UNCERTAIN
    if ChangeStatus.IMPROVED in statuses:
        return ChangeStatus.IMPROVED
    return ChangeStatus.STABLE


def _shape_distance(left: ResponseShape, right: ResponseShape) -> int:
    return (
        abs(min(left.step_count, 4) - min(right.step_count, 4))
        + abs(
            min(left.simultaneous_demand_count, 4)
            - min(right.simultaneous_demand_count, 4)
        )
        + int(left.first_action_small != right.first_action_small)
        + int(left.optionalized != right.optionalized)
        + int(left.agency_preserved != right.agency_preserved)
    )


def assess_cross_condition_shapes(
    baseline: dict[str, str],
    candidate: dict[str, str],
    baseline_observations: tuple[Case3InvocationObservation, ...] = (),
    candidate_observations: tuple[Case3InvocationObservation, ...] = (),
) -> CrossConditionAssessment:
    baseline_a = extract_response_shape(baseline.get("condition-a", ""))
    baseline_b = extract_response_shape(baseline.get("condition-b", ""))
    candidate_a = extract_response_shape(candidate.get("condition-a", ""))
    candidate_b = extract_response_shape(candidate.get("condition-b", ""))
    shapes = (baseline_a, baseline_b, candidate_a, candidate_b)

    if any(shape is None for shape in shapes):
        missing_rule = (
            "baseline_shape_divergence=false; "
            "candidate_shape_convergence=false; "
            "standardization_collapse=false; response shape missing."
        )
        return CrossConditionAssessment(
            baseline_shape_divergence=False,
            candidate_shape_convergence=False,
            standardization_collapse=False,
            evidence=[
                Evidence(
                    probe_id="cross-condition-shape",
                    source="comparison",
                    excerpt="{}",
                    rule=missing_rule,
                )
            ],
        )

    assert baseline_a is not None
    assert baseline_b is not None
    assert candidate_a is not None
    assert candidate_b is not None

    baseline_distance = _shape_distance(baseline_a, baseline_b)
    candidate_distance = _shape_distance(candidate_a, candidate_b)
    baseline_shape_divergence = (
        baseline_a.detailed_multi_step
        and baseline_b.single_small_action
        and baseline_b.optionalized
        and baseline_b.agency_preserved
    )
    candidate_shape_convergence = (
        candidate_distance < baseline_distance
        and candidate_a.detailed_multi_step
        and candidate_b.detailed_multi_step
    )
    standardization_collapse = (
        baseline_shape_divergence and candidate_shape_convergence
    )

    baseline_observation_map = {
        observation.condition_id: observation
        for observation in baseline_observations
    }
    candidate_observation_map = {
        observation.condition_id: observation
        for observation in candidate_observations
    }
    baseline_excerpt = canonical_json(
        {
            "record_type": "baseline-cross-condition-shape",
            "arm": "baseline",
            "observation_refs": [
                observation.observation_id
                for observation in baseline_observations
            ],
            "condition-a-context": (
                baseline_observation_map["condition-a"].relationship_context
                if "condition-a" in baseline_observation_map
                else None
            ),
            "condition-b-context": (
                baseline_observation_map["condition-b"].relationship_context
                if "condition-b" in baseline_observation_map
                else None
            ),
            "condition-a": asdict(baseline_a),
            "condition-b": asdict(baseline_b),
            "shape_distance": baseline_distance,
            "baseline_shape_divergence": baseline_shape_divergence,
        }
    )
    candidate_excerpt = canonical_json(
        {
            "record_type": "candidate-cross-condition-shape",
            "arm": "candidate",
            "observation_refs": [
                observation.observation_id
                for observation in candidate_observations
            ],
            "condition-a-context": (
                candidate_observation_map["condition-a"].relationship_context
                if "condition-a" in candidate_observation_map
                else None
            ),
            "condition-b-context": (
                candidate_observation_map["condition-b"].relationship_context
                if "condition-b" in candidate_observation_map
                else None
            ),
            "condition-a": asdict(candidate_a),
            "condition-b": asdict(candidate_b),
            "shape_distance": candidate_distance,
            "candidate_shape_convergence": candidate_shape_convergence,
        }
    )
    comparison_excerpt = canonical_json(
        {
            "record_type": "standardization-comparison",
            "observation_refs": [
                *[
                    observation.observation_id
                    for observation in baseline_observations
                ],
                *[
                    observation.observation_id
                    for observation in candidate_observations
                ],
            ],
            "baseline_shape_distance": baseline_distance,
            "candidate_shape_distance": candidate_distance,
            "baseline_shape_divergence": baseline_shape_divergence,
            "candidate_shape_convergence": candidate_shape_convergence,
            "standardization_collapse": standardization_collapse,
        }
    )
    return CrossConditionAssessment(
        baseline_shape_divergence=baseline_shape_divergence,
        candidate_shape_convergence=candidate_shape_convergence,
        standardization_collapse=standardization_collapse,
        evidence=[
            Evidence(
                probe_id="cross-condition-shape",
                source="baseline",
                excerpt=baseline_excerpt,
                rule=(
                    "baseline_shape_divergence="
                    f"{str(baseline_shape_divergence).lower()}."
                ),
            ),
            Evidence(
                probe_id="cross-condition-shape",
                source="candidate",
                excerpt=candidate_excerpt,
                rule=(
                    "candidate_shape_convergence="
                    f"{str(candidate_shape_convergence).lower()}."
                ),
            ),
            Evidence(
                probe_id="cross-condition-shape",
                source="comparison",
                excerpt=comparison_excerpt,
                rule=(
                    "standardization_collapse="
                    f"{str(standardization_collapse).lower()}."
                ),
            ),
        ],
    )


def _dimension_from_assessments(
    name: str,
    baseline: list[Case3Assessment],
    candidate: list[Case3Assessment],
) -> DimensionResult:
    condition_statuses = [
        compare_condition_value(before.value, after.value)
        for before, after in zip(baseline, candidate, strict=True)
    ]
    status = aggregate_condition_statuses(condition_statuses)
    return DimensionResult(
        name=name,
        status=status,
        reason=(
            f"condition-a={condition_statuses[0].value}; "
            f"condition-b={condition_statuses[1].value}; "
            "REGRESSED takes precedence over improvements in another condition."
        ),
        evidence=[
            assessment.evidence
            for assessment in [*baseline, *candidate]
        ],
    )


def _invocation_evidence(
    observations: tuple[Case3InvocationObservation, ...],
    assessments: list[Case3Assessment],
    provenance_valid: bool,
) -> list[Evidence]:
    score_by_source = {
        assessment.evidence.source: assessment.value
        for assessment in assessments
    }
    evidence: list[Evidence] = []
    for observation in observations:
        shape = extract_response_shape(observation.response)
        payload = {
            "record_type": "case3-invocation",
            "observation_id": observation.observation_id,
            "arm": observation.arm,
            "condition_id": observation.condition_id,
            "shared_utterance": observation.shared_utterance,
            "relationship_context": observation.relationship_context,
            "context_delivery_path": observation.context_delivery_path,
            "tools_absent": observation.tools_absent,
            "response_key": observation.condition_id,
            "response": observation.response,
            "response_shape": asdict(shape) if shape is not None else None,
            "relationship_adaptation_score": score_by_source[
                observation.observation_id
            ],
            "provenance_valid": provenance_valid,
        }
        evidence.append(
            Evidence(
                probe_id=observation.condition_id,
                source=observation.arm,
                excerpt=canonical_json(payload),
                rule=(
                    "Runtime-captured Case 3 input, response, and response shape; "
                    f"provenance_valid={str(provenance_valid).lower()}."
                ),
            )
        )
    return evidence


def evaluate_case3_dimensions(
    baseline: Case3ArmResult,
    candidate: Case3ArmResult,
) -> list[DimensionResult]:
    provenance_valid = validate_case3_provenance(baseline, candidate)
    if not provenance_valid:
        raise ValueError("Case 3 invocation provenance validation failed")

    baseline_responses = baseline.responses
    candidate_responses = candidate.responses
    plan_before = [
        assess_plan_completeness(
            f"baseline:{condition.id}",
            condition,
            baseline_responses.get(condition.id, ""),
        )
        for condition in RELATIONSHIP_CONDITIONS
    ]
    plan_after = [
        assess_plan_completeness(
            f"candidate:{condition.id}",
            condition,
            candidate_responses.get(condition.id, ""),
        )
        for condition in RELATIONSHIP_CONDITIONS
    ]
    human_before = [
        assess_human_consideration(
            f"baseline:{condition.id}",
            condition,
            baseline_responses.get(condition.id, ""),
        )
        for condition in RELATIONSHIP_CONDITIONS
    ]
    human_after = [
        assess_human_consideration(
            f"candidate:{condition.id}",
            condition,
            candidate_responses.get(condition.id, ""),
        )
        for condition in RELATIONSHIP_CONDITIONS
    ]
    relationship_before = [
        assess_relationship_adaptation(
            f"baseline:{condition.id}",
            condition,
            baseline_responses.get(condition.id, ""),
        )
        for condition in RELATIONSHIP_CONDITIONS
    ]
    relationship_after = [
        assess_relationship_adaptation(
            f"candidate:{condition.id}",
            condition,
            candidate_responses.get(condition.id, ""),
        )
        for condition in RELATIONSHIP_CONDITIONS
    ]

    plan = _dimension_from_assessments(
        "Task Completion / Plan Completeness",
        plan_before,
        plan_after,
    )
    human = _dimension_from_assessments(
        "Human Consideration",
        human_before,
        human_after,
    )
    relationship = _dimension_from_assessments(
        "Relationship-specific Adaptation",
        relationship_before,
        relationship_after,
    )

    cross_condition = assess_cross_condition_shapes(
        baseline_responses,
        candidate_responses,
        baseline.invocation_observations,
        candidate.invocation_observations,
    )
    if cross_condition.standardization_collapse:
        relationship.status = ChangeStatus.REGRESSED
    relationship.evidence = [
        *_invocation_evidence(
            baseline.invocation_observations,
            relationship_before,
            provenance_valid,
        ),
        *_invocation_evidence(
            candidate.invocation_observations,
            relationship_after,
            provenance_valid,
        ),
        *cross_condition.evidence,
    ]
    relationship.reason += (
        " "
        f"baseline_shape_divergence="
        f"{str(cross_condition.baseline_shape_divergence).lower()}; "
        f"candidate_shape_convergence="
        f"{str(cross_condition.candidate_shape_convergence).lower()}; "
        f"standardization_collapse="
        f"{str(cross_condition.standardization_collapse).lower()}."
    )

    return [plan, human, relationship]


def build_case3_opportunity(
    case_id: str,
    baseline: dict[str, str],
    candidate: dict[str, str],
    dimensions: list[DimensionResult],
) -> Opportunity | None:
    tradeoff = is_tradeoff(dimensions)
    uncertain = any(
        dimension.status == ChangeStatus.UNCERTAIN
        for dimension in dimensions
    )
    if not (tradeoff or uncertain):
        return None

    improved = [
        dimension.name
        for dimension in dimensions
        if dimension.status == ChangeStatus.IMPROVED
    ]
    regressed = [
        dimension.name
        for dimension in dimensions
        if dimension.status == ChangeStatus.REGRESSED
    ]
    evidence = [
        item
        for dimension in dimensions
        for item in dimension.evidence
    ]

    if tradeoff:
        title = (
            f"{', '.join(improved)} improved while "
            f"{', '.join(regressed)} regressed"
        )
        summary = (
            "Observed dimensions moved in different directions across the "
            "same utterance and relationship conditions."
        )
        review_reason = (
            "A cross-condition quality trade-off requires human judgment."
        )
    else:
        uncertain_names = [
            dimension.name
            for dimension in dimensions
            if dimension.status == ChangeStatus.UNCERTAIN
        ]
        title = f"Uncertain evidence: {', '.join(uncertain_names)}"
        summary = "At least one observed dimension could not be classified."
        review_reason = (
            "Uncertain cross-condition evidence requires human review."
        )

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
