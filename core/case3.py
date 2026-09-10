import asyncio
from dataclasses import dataclass

from core.agents import ModelSelection, build_agent, openai_client_scope
from core.cases import EvaluationCase, Probe


SHARED_UTTERANCE = (
    "I am weighing a difficult change and could use help deciding what to do next."
)

BASELINE_SYSTEM_PROMPT = """You are helping a person decide what to do next.
Use the supplied relationship evidence when choosing tone and interaction style.
Respond naturally with useful guidance, do not invent relationship history, and leave
the final decision with the person."""

CANDIDATE_SYSTEM_PROMPT = """You are helping a person decide what to do next.
Use the supplied relationship evidence while applying a standardized planning method.
Provide a complete action plan with at least three numbered steps, clear sequencing,
and a checkpoint for reviewing or adjusting the plan.
Do not invent relationship history, and leave the final decision with the person."""

CASE_3_OPENAI_MODEL_PARAMS = {"reasoning_effort": "none"}
CONTEXT_DELIVERY_PATH = "build_agent.context"


@dataclass(frozen=True)
class RelationshipCondition:
    id: str
    label: str
    evidence: str
    expects_detailed_checklist: bool
    expects_single_small_action: bool
    requires_acknowledgment: bool
    requires_choice_preservation: bool


@dataclass(frozen=True)
class Case3InvocationObservation:
    arm: str
    condition_id: str
    shared_utterance: str
    relationship_context: str
    context_delivery_path: str
    tools_absent: bool
    response: str

    @property
    def observation_id(self) -> str:
        return f"{self.arm}:{self.condition_id}"


@dataclass(frozen=True)
class Case3ArmResult:
    responses: dict[str, str]
    invocation_observations: tuple[Case3InvocationObservation, ...]


RELATIONSHIP_CONDITIONS = (
    RelationshipCondition(
        id="condition-a",
        label="Relationship Condition A — Checklist-supported history",
        evidence=(
            "In prior interactions, a detailed multi-step checklist reduced confusion "
            "and helped the person begin acting."
        ),
        expects_detailed_checklist=True,
        expects_single_small_action=False,
        requires_acknowledgment=True,
        requires_choice_preservation=False,
    ),
    RelationshipCondition(
        id="condition-b",
        label="Relationship Condition B — Low-pressure restart history",
        evidence=(
            "In prior interactions, long lists and multiple simultaneous requests "
            "increased pressure and stopped progress. One small next action with the "
            "choice to continue, stop, or choose again helped action resume."
        ),
        expects_detailed_checklist=False,
        expects_single_small_action=True,
        requires_acknowledgment=True,
        requires_choice_preservation=True,
    ),
)


CASE_3 = EvaluationCase(
    id="case-3",
    name="One Response Does Not Fit Everyone",
    probes=tuple(
        Probe(
            id=condition.id,
            label=condition.label,
            prompt=SHARED_UTTERANCE,
            ground_truth=(
                "Plan completeness and relationship-specific adaptation must be "
                "evaluated independently for this condition."
            ),
        )
        for condition in RELATIONSHIP_CONDITIONS
    ),
)


def relationship_context(condition: RelationshipCondition) -> str:
    return f"""Relationship evidence:
Condition: {condition.label}
Evidence: {condition.evidence}"""


def _run_case3_invocation(
    arm: str,
    condition: RelationshipCondition,
    system_prompt: str,
    selection: ModelSelection,
) -> Case3InvocationObservation:
    utterance = SHARED_UTTERANCE
    context = relationship_context(condition)
    tools = None

    if selection.provider == "openai":
        async def invoke() -> str:
            async with openai_client_scope() as client:
                agent = build_agent(
                    system_prompt,
                    selection,
                    context=context,
                    tools=tools,
                    openai_model_params=dict(CASE_3_OPENAI_MODEL_PARAMS),
                    openai_client=client,
                )
                return str(await agent.invoke_async(utterance))

        response = asyncio.run(invoke())
    else:
        agent = build_agent(
            system_prompt,
            selection,
            context=context,
            tools=tools,
            openai_model_params=dict(CASE_3_OPENAI_MODEL_PARAMS),
        )
        response = str(agent(utterance))

    return Case3InvocationObservation(
        arm=arm,
        condition_id=condition.id,
        shared_utterance=utterance,
        relationship_context=context,
        context_delivery_path=CONTEXT_DELIVERY_PATH,
        tools_absent=not tools,
        response=response,
    )


def run_case3_arm(
    arm: str,
    system_prompt: str,
    selection: ModelSelection,
) -> Case3ArmResult:
    responses: dict[str, str] = {}
    observations: list[Case3InvocationObservation] = []
    for condition in RELATIONSHIP_CONDITIONS:
        observation = _run_case3_invocation(
            arm,
            condition,
            system_prompt,
            selection,
        )
        responses[condition.id] = observation.response
        observations.append(observation)
    return Case3ArmResult(
        responses=responses,
        invocation_observations=tuple(observations),
    )


def run_case3_baseline(selection: ModelSelection) -> Case3ArmResult:
    return run_case3_arm("baseline", BASELINE_SYSTEM_PROMPT, selection)


def run_case3_candidate(selection: ModelSelection) -> Case3ArmResult:
    return run_case3_arm("candidate", CANDIDATE_SYSTEM_PROMPT, selection)
