from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChangeStatus(str, Enum):
    IMPROVED = "IMPROVED"
    STABLE = "STABLE"
    REGRESSED = "REGRESSED"
    UNCERTAIN = "UNCERTAIN"


class Evidence(BaseModel):
    probe_id: str
    source: str
    excerpt: str
    rule: str


class DimensionResult(BaseModel):
    name: str
    status: ChangeStatus
    reason: str
    evidence: list[Evidence]


class Opportunity(BaseModel):
    id: str
    title: str
    summary: str
    case_id: str
    baseline_responses: dict[str, str]
    candidate_responses: dict[str, str]
    dimensions: list[DimensionResult]
    what_improved: list[str]
    what_regressed: list[str]
    evidence: list[Evidence]
    human_review: bool
    review_reason: str


class RunState(str, Enum):
    IDLE = "idle"
    CONFIGURING = "configuring"
    RUNNING_BASELINE = "running_baseline"
    RUNNING_CANDIDATE = "running_candidate"
    EVALUATING = "evaluating"
    COMPARING = "comparing"
    OPPORTUNITIES_FOUND = "opportunities_found"
    NO_OPPORTUNITIES = "no_opportunities"
    ERROR = "error"


class EvaluationRun(BaseModel):
    id: str
    case_id: str
    state: RunState
    model_id: str | None = None
    baseline_responses: dict[str, str] = Field(default_factory=dict)
    candidate_responses: dict[str, str] = Field(default_factory=dict)
    dimensions: list[DimensionResult] = Field(default_factory=list)
    opportunities: list[Opportunity] = Field(default_factory=list)
    human_review: bool = False
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

