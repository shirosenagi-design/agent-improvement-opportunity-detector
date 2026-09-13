from __future__ import annotations

import json
import os
import re
import ssl
from typing import Any

import truststore
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from strands import Agent, tool
from strands.models.openai import OpenAIModel

from .measure import measure_pair
from .personalization import normalize_mbti
from .population import profile_as_prompt, simulate_population
from .schemas import (
    AgentTraceEvent,
    OpportunityPacket,
    ProvisionalUserModel,
    TrialRequest,
    TrialResult,
)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    return json.loads(candidate)


def _normalized(text: str) -> str:
    return " ".join(text.split()).strip()


def _safe_excerpt(excerpt: str, sources: list[str]) -> bool:
    normalized = _normalized(excerpt)
    return (
        bool(normalized)
        and len(normalized) <= 260
        and any(normalized in _normalized(source) for source in sources)
    )


def _validated_packet(
    raw: dict[str, Any], population_response: str, personalized_response: str
) -> OpportunityPacket:
    packet = OpportunityPacket.model_validate(raw)
    sources = [population_response, personalized_response]

    packet.population_baseline.observed_excerpts = [
        x for x in packet.population_baseline.observed_excerpts if _safe_excerpt(x, sources)
    ][:4]
    packet.personalized_observation.observed_excerpts = [
        x for x in packet.personalized_observation.observed_excerpts if _safe_excerpt(x, sources)
    ][:4]
    for question in packet.research_questions:
        question.evidence_from_population = [
            x for x in question.evidence_from_population if _safe_excerpt(x, sources)
        ][:3]
        question.evidence_from_personalized = [
            x for x in question.evidence_from_personalized if _safe_excerpt(x, sources)
        ][:3]
    return packet


async def run_research_trial(request: TrialRequest, api_key: str) -> TrialResult:
    model_id = os.getenv("OPENAI_MODEL_ID", os.getenv("OPENAI_MODEL", "gpt-5.6-sol"))

    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    http_client = DefaultAsyncHttpxClient(verify=ssl_context)
    client = AsyncOpenAI(api_key=api_key, http_client=http_client, max_retries=0)

    def new_model() -> OpenAIModel:
        return OpenAIModel(
            client=client,
            model_id=model_id,
            params={"reasoning_effort": "none"},
        )

    state: dict[str, Any] = {
        "population_profile": None,
        "user_model": None,
        "population_response": None,
        "personalized_response": None,
        "measurements": None,
        "counterfactual_used": False,
    }
    trace: list[AgentTraceEvent] = []

    def record(actor: str, action: str, detail: str) -> None:
        trace.append(
            AgentTraceEvent(
                step=len(trace) + 1,
                actor=actor,
                action=action,
                detail=detail,
            )
        )

    def ensure_population_profile():
        if state["population_profile"] is None:
            state["population_profile"] = simulate_population(
                request.population_preset,
                request.population_size,
                request.population_seed,
                request.population_weights,
            )
            record(
                "tool",
                "prepare_synthetic_population",
                (
                    f"Prepared deterministic synthetic n={state['population_profile'].size} "
                    f"profile ({state['population_profile'].preset}); no real user data."
                ),
            )
        return state["population_profile"]

    @tool
    def prepare_synthetic_population() -> dict:
        """Prepare the deterministic synthetic aggregate preference profile."""
        return ensure_population_profile().model_dump()

    async def infer_user_model_internal() -> ProvisionalUserModel:
        if state["user_model"] is not None:
            return state["user_model"]

        mbti = normalize_mbti(request.user_mbti)
        intro = request.personal_context.strip()

        profiler = Agent(
            model=new_model(),
            callback_handler=None,
            system_prompt=(
                "You infer a PROVISIONAL USER MODEL for a cold-start personalization experiment. "
                "This is not personality diagnosis. MBTI is only a weak prior. The user's own "
                "self-introduction and current message are stronger evidence. Infer only what is "
                "useful for how an AI should think with this person: priorities, decision framing, "
                "level of challenge, likely friction, what to avoid assuming, and how to preserve "
                "their agency. Do not infer sensitive or protected traits that were not explicitly "
                "provided. Do not turn one trait into a stereotype. Explicitly separate observed "
                "signals from working hypotheses. Return JSON only with exactly this shape:\n"
                '{"summary":"string","explicit_signals":["..."],"working_hypotheses":["..."],'
                '"interaction_needs":["..."],"likely_friction_points":["..."],'
                '"personalization_policy":["..."],"do_not_assume":["..."],'
                '"confidence":"LOW|MEDIUM|HIGH"}'
            ),
        )

        prompt = (
            f"SELF-REPORTED MBTI: {mbti or '(not supplied)'}\n\n"
            f"SHORT SELF-INTRODUCTION:\n{intro or '(not supplied)'}\n\n"
            f"CURRENT USER MESSAGE:\n{request.prompt}\n\n"
            "Build the smallest useful model of this person for this one conversation. "
            "The goal is to shortcut some of the learning that normally takes repeated interaction, "
            "without pretending a long-term relationship already exists."
        )
        raw = str(await profiler.invoke_async(prompt)).strip()
        model = ProvisionalUserModel.model_validate(_extract_json(raw))
        state["user_model"] = model
        record(
            "inference_agent",
            "infer_provisional_user_model",
            (
                "Inferred a provisional user model from self-reported MBTI, short self-introduction, "
                "and the current task. The result is treated as a hypothesis, not identity ground truth."
            ),
        )
        return model

    @tool
    async def infer_provisional_user_model() -> dict:
        """Infer a provisional user model for the one-to-one condition."""
        return (await infer_user_model_internal()).model_dump()

    @tool
    async def generate_population_mode_response() -> str:
        """Generate the broad-population answer for the same user message."""
        profile = profile_as_prompt(ensure_population_profile())
        subject = Agent(
            model=new_model(),
            callback_handler=None,
            system_prompt=(
                f"{request.base_persona}\n\n"
                "You are the POPULATION PREFERENCE MODE subject in a controlled research trial. "
                "The values below summarize a synthetic aggregate preference profile from 0..1. "
                "They are not real RLHF training data and never override truthfulness or safety. "
                f"Profile: {profile}.\n"
                "Answer as a capable general-purpose assistant optimizing for broad acceptability, "
                "broad usefulness, and low risk across many possible users. Do not use the separate "
                "self-introduction or provisional user model. Do not mention this experiment. "
                "Give the actual user-facing answer."
            ),
        )
        output = str(await subject.invoke_async(request.prompt)).strip()
        state["population_response"] = output
        record(
            "subject_agent",
            "generate_population_mode_response",
            "Generated a fresh live broad-population answer to the submitted free-form message.",
        )
        return output

    @tool
    async def generate_personalized_mode_response() -> str:
        """Generate a response by reasoning through the provisional user model."""
        user_model = await infer_user_model_internal()
        intro = request.personal_context.strip() or "(none supplied)"

        subject = Agent(
            model=new_model(),
            callback_handler=None,
            system_prompt=(
                f"{request.base_persona}\n\n"
                "You are the PERSONALIZED MODE subject in a controlled research trial. You are the "
                "same base model/persona as Population Mode. The experimental difference is that you "
                "have a provisional model of this individual.\n\n"
                "Do not merely change tone or add MBTI-flavored wording. Use the provisional user model "
                "to change your reasoning priorities when warranted: what you foreground, what you omit, "
                "how you frame choices, how much you challenge assumptions, how you reduce predictable "
                "friction, and how you preserve the user's values and agency. Treat every inference as "
                "fallible. Concrete self-description overrides MBTI stereotypes. Never pretend you have "
                "a long relationship or memories you do not have.\n\n"
                "Keep the same truthfulness and safety floor as Population Mode. In higher-risk situations, "
                "personalization may change engagement strategy and wording, but it must not invent facts "
                "or remove genuinely warranted safety information merely to feel more personal.\n\n"
                f"SHORT SELF-INTRODUCTION:\n{intro}\n\n"
                f"PROVISIONAL USER MODEL (hypothesis, not fact):\n"
                f"{json.dumps(user_model.model_dump(), ensure_ascii=False)}\n\n"
                "Do not mention MBTI, the user model, or the experiment unless the user explicitly asks."
            ),
        )

        output = str(await subject.invoke_async(request.prompt)).strip()
        state["personalized_response"] = output
        record(
            "subject_agent",
            "generate_personalized_mode_response",
            (
                "Generated a fresh live answer by reasoning through the inferred provisional user model, "
                "not through a fixed MBTI-to-counterpart mapping."
            ),
        )
        return output

    @tool
    def measure_current_pair() -> dict:
        """Run deterministic surface measurements on the two current live responses."""
        if not state["population_response"] or not state["personalized_response"]:
            record(
                "tool",
                "measure_current_pair_not_ready",
                "Measurement requested before both live responses existed.",
            )
            return {
                "ready": False,
                "reason": "Generate both Population and Personalized responses first.",
            }

        measurements = measure_pair(
            request.prompt,
            request.personal_context,
            state["population_response"],
            state["personalized_response"],
        )
        state["measurements"] = measurements
        record(
            "tool",
            "measure_current_pair",
            (
                "Measured response shape and wording-level differences. "
                "These measurements are supporting evidence, not the personalization judgment itself."
            ),
        )
        return measurements

    @tool
    async def run_one_counterfactual_probe(reason: str) -> dict:
        """Run at most one bounded re-probe if a developer hypothesis is genuinely ambiguous."""
        if state["counterfactual_used"]:
            return {"ran": False, "reason": "Counterfactual budget already used."}
        if not state["population_response"] or not state["personalized_response"]:
            return {"ran": False, "reason": "Both primary responses must exist first."}

        state["counterfactual_used"] = True
        user_model = await infer_user_model_internal()
        probe_agent = Agent(
            model=new_model(),
            callback_handler=None,
            system_prompt=(
                f"{request.base_persona}\n"
                "You are a bounded counterfactual probe for a developer evaluation. "
                "Vary only the specific personalization choice named by the evaluator. "
                "Keep truthfulness and safety fixed. Return one concise alternative user-facing response."
            ),
        )
        probe_prompt = (
            f"AMBIGUITY TO TEST:\n{reason}\n\n"
            f"ORIGINAL USER MESSAGE:\n{request.prompt}\n\n"
            f"PROVISIONAL USER MODEL:\n"
            f"{json.dumps(user_model.model_dump(), ensure_ascii=False)}"
        )
        output = str(await probe_agent.invoke_async(probe_prompt)).strip()
        record(
            "subject_agent",
            "run_one_counterfactual_probe",
            f"Used the one permitted re-probe to test this ambiguity: {reason[:180]}",
        )
        return {"ran": True, "reason": reason, "probe_response": output}

    orchestrator = Agent(
        model=new_model(),
        callback_handler=None,
        tools=[
            prepare_synthetic_population,
            infer_provisional_user_model,
            generate_population_mode_response,
            generate_personalized_mode_response,
            measure_current_pair,
            run_one_counterfactual_probe,
        ],
        system_prompt=(
            "You are PROJECT 04: a research instrument for AI developers studying personalization at the individual scale. "
            "Your purpose is to help humans improve AI agents without losing what already works. "
            "You are NOT a consumer answer-comparison app, NOT a brevity/readability scorer, NOT an MBTI critic, and NOT an automatic optimizer.\n\n"
            "The experiment is intentionally ASYMMETRIC.\n"
            "Population Mode is the macro baseline: broadly acceptable, broadly safe behavior across many possible users.\n"
            "Personalized Mode is the microscope: the same base agent reasons through a provisional model of this one user.\n"
            "Your job is to SHOW WHAT CHANGED and return the unanswered research questions to the developer.\n\n"
            "For each trial:\n"
            "1. Prepare the synthetic population baseline.\n"
            "2. Infer the provisional user model from self-reported MBTI + short self-introduction + current task. MBTI is only bootstrap context; do not evaluate MBTI validity unless the user's question itself is about MBTI.\n"
            "3. Generate both answers to the exact same user message.\n"
            "4. Inspect the RAW answers WITHOUT rewriting, shortening, polishing, summarizing, or normalizing them.\n"
            "5. Record concrete elements present in the macro baseline.\n"
            "6. Record what the macro baseline did not foreground for THIS user.\n"
            "7. Record what personalized reasoning newly surfaced and which baseline elements remained.\n"
            "8. Record anything that may have been weakened or omitted by personalization. This is an observation, not a verdict.\n"
            "9. Turn only the strongest observed differences into 1-3 NEUTRAL, TESTABLE RESEARCH QUESTIONS. Each question must be grounded in exact excerpts from A and/or B.\n"
            "10. Stop at Human Review. Never recommend adoption, implementation, generalization, or automatic agent updates.\n\n"
            "CRITICAL RESEARCH BOUNDARY: Do NOT tell the developer what to implement. Do NOT say an observed behavior should be adopted, generalized, kept in a personalization layer, or rejected. Do NOT write implementation prescriptions such as 'the system should...'. Instead, phrase the unresolved issue as a question the developer can test across more users or conditions. PROJECT 04 supplies evidence and testable questions, not conclusions.\n\n"
            "Keep the summary neutral and short: at most two sentences. Keep observation lists compact: no more than 4 items each. Keep each research question compact.\n\n"
            "DO NOT use response length, sentence count, verbosity, concision, readability, or generic cognitive load as a general advantage/disadvantage. These may only matter if the user's own self-description explicitly makes them relevant, and even then they are user-specific observations, not generic quality metrics. Never trim the personalized response before analysis.\n\n"
            "DO NOT turn this into 'which answer wins?'. The population baseline is valuable. The personalized condition exists to expose individual-specific possibilities that macro optimization can hide. The developer decides what any observed difference means.\n\n"
            "Final output must be JSON only with exactly this shape:\n"
            '{"summary":"string","population_baseline":{"present_in_baseline":["..."],"not_foregrounded_for_this_user":["..."],"observed_excerpts":["exact excerpt"],"note":"string"},"personalized_observation":{"newly_surfaced":["..."],"baseline_elements_still_present":["..."],"possibly_weakened_or_omitted":["..."],"observed_excerpts":["exact excerpt"],"note":"string"},"research_questions":[{"title":"string","observed_difference":"string","evidence_from_population":["exact excerpt"],"evidence_from_personalized":["exact excerpt"],"question_to_test":"string ending with ?"}],"no_strong_difference_reason":"string","human_review_prompt":"neutral question for the developer"}'
        ),
    )

    record(
        "orchestrator_agent",
        "trial_started",
        (
            "PROJECT 04 received a new free-form trial and began observing differences "
            "between the macro baseline and one-to-one reasoning."
        ),
    )

    trial_prompt = (
        "Run a new Research Trial.\n\n"
        f"USER MESSAGE:\n{request.prompt}\n\n"
        f"SELF-REPORTED MBTI:\n{request.user_mbti or '(not supplied)'}\n\n"
        f"SHORT SELF-INTRODUCTION:\n{request.personal_context or '(not supplied)'}\n\n"
        f"SYNTHETIC POPULATION PRESET: {request.population_preset}\n"
        f"SYNTHETIC POPULATION SIZE: {request.population_size}\n\n"
        "Use the available tools. Do not invent tool results. The provisional user model must be "
        "inferred before judging whether personalization helped. Finish with observed differences and neutral questions to test, then stop at Human Review."
    )

    try:
        raw_result = str(await orchestrator.invoke_async(trial_prompt)).strip()

        if state["population_profile"] is None:
            raise ValueError("The orchestrator did not prepare the synthetic population.")
        if state["user_model"] is None:
            raise ValueError("The orchestrator did not infer the provisional user model.")
        if not state["population_response"] or not state["personalized_response"]:
            raise ValueError("The orchestrator did not generate both required live responses.")

        if state["measurements"] is None:
            state["measurements"] = measure_pair(
                request.prompt,
                request.personal_context,
                state["population_response"],
                state["personalized_response"],
            )
            record(
                "application_guardrail",
                "required_measurement_completed",
                (
                    "Both live responses existed; the application completed the required deterministic "
                    "surface measurement without fabricating a semantic judgment."
                ),
            )

        packet = _validated_packet(
            _extract_json(raw_result),
            state["population_response"],
            state["personalized_response"],
        )
        record(
            "orchestrator_agent",
            "opportunity_packet_created",
            (
                "PROJECT 04 converted the strongest observed differences into neutral, evidence-backed questions for developers to test."
            ),
        )
        record(
            "human_boundary",
            "human_review_reached",
            (
                "No recommendation or automatic agent update is performed. The developer decides what the evidence means and what, if anything, to test next."
            ),
        )

        return TrialResult(
            prompt=request.prompt,
            user_mbti=request.user_mbti,
            personal_context=request.personal_context,
            population_profile=state["population_profile"],
            provisional_user_model=state["user_model"],
            population_response=state["population_response"],
            personalized_response=state["personalized_response"],
            deterministic_measurements=state["measurements"],
            opportunity_packet=packet,
            agent_trace=trace,
            model=model_id,
        )
    finally:
        await client.close()
