from typing import Literal
from pydantic import BaseModel, Field

PopulationPreset = Literal["balanced","cautious_consensus","creative_exploratory","warm_relational"]
MBTIType = Literal["INTJ","INTP","ENTJ","ENTP","INFJ","INFP","ENFJ","ENFP","ISTJ","ISFJ","ESTJ","ESFJ","ISTP","ISFP","ESTP","ESFP"]

class PopulationWeights(BaseModel):
    caution: float = Field(.66, ge=0, le=1)
    consensus: float = Field(.68, ge=0, le=1)
    directness: float = Field(.50, ge=0, le=1)
    warmth: float = Field(.55, ge=0, le=1)
    novelty: float = Field(.45, ge=0, le=1)
    context_sensitivity: float = Field(.42, ge=0, le=1)

class TrialRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=4000)
    user_mbti: MBTIType | None = None
    personal_context: str = Field(default="", max_length=4000)
    base_persona: str = Field(default="A capable general-purpose AI assistant. Be useful, truthful, clear, and appropriately cautious.", max_length=1500)
    population_preset: PopulationPreset = "balanced"
    population_weights: PopulationWeights | None = None
    population_size: int = Field(10_000, ge=100, le=100_000)
    population_seed: int = Field(20260911, ge=0, le=2_147_483_647)

class DistributionStat(BaseModel):
    mean: float
    p10: float
    p90: float

class PopulationProfile(BaseModel):
    size: int
    seed: int
    preset: str
    dimensions: dict[str, DistributionStat]
    note: str

class ProvisionalUserModel(BaseModel):
    summary: str
    explicit_signals: list[str] = []
    working_hypotheses: list[str] = []
    interaction_needs: list[str] = []
    likely_friction_points: list[str] = []
    personalization_policy: list[str] = []
    do_not_assume: list[str] = []
    confidence: Literal["LOW","MEDIUM","HIGH"] = "LOW"

class BaselineObservation(BaseModel):
    present_in_baseline: list[str] = []
    not_foregrounded_for_this_user: list[str] = []
    observed_excerpts: list[str] = []
    note: str = ""

class PersonalizedObservation(BaseModel):
    newly_surfaced: list[str] = []
    baseline_elements_still_present: list[str] = []
    possibly_weakened_or_omitted: list[str] = []
    observed_excerpts: list[str] = []
    note: str = ""

class ResearchQuestion(BaseModel):
    title: str
    observed_difference: str
    evidence_from_population: list[str] = []
    evidence_from_personalized: list[str] = []
    question_to_test: str

class AgentTraceEvent(BaseModel):
    step: int
    actor: str
    action: str
    detail: str

class OpportunityPacket(BaseModel):
    summary: str
    population_baseline: BaselineObservation
    personalized_observation: PersonalizedObservation
    research_questions: list[ResearchQuestion] = []
    no_strong_difference_reason: str = ""
    human_review_prompt: str

class TrialResult(BaseModel):
    prompt: str
    user_mbti: str | None = None
    personal_context: str
    population_profile: PopulationProfile
    provisional_user_model: ProvisionalUserModel | None = None
    population_response: str
    personalized_response: str
    deterministic_measurements: dict
    opportunity_packet: OpportunityPacket
    agent_trace: list[AgentTraceEvent]
    model: str
    population_is_synthetic: bool = True
    methodology_note: str = (
        "Population Mode is a synthetic broad-preference baseline. Personalized Mode uses a live provisional user model inferred from MBTI + a short self-introduction + the current task. PROJECT 04 shows observed differences and turns only the strongest differences into neutral questions for developers to test. It does not score brevity, choose a winner, recommend adoption, or automatically update the agent."
    )
