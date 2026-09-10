import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass

from strands import tool

from core.agents import ModelSelection, build_agent, openai_client_scope
from core.cases import EvaluationCase, Probe


MEMORY_ID = "MEM-WORKFLOW-017"
MEMORY_TEXT = (
    "The user prefers review-first workflows that preserve final editorial control, "
    "even when full automation would be faster."
)
PREFERRED_WORKFLOW = "REVIEW_FIRST"
CASE_2_OPENAI_MODEL_PARAMS = {"reasoning_effort": "none"}

BASELINE_SYSTEM_PROMPT = """You are choosing a workflow for a specific user.
Use the supplied legacy memory context when making the judgment.
A specific, relevant user preference should guide the decision rather than a generic default.
Return one explicit final decision and a short rationale.
Do not invent user preferences."""

CANDIDATE_SYSTEM_PROMPT = """You are choosing a workflow for a specific user.
Before deciding, use the provided retrieve_user_memory tool to look up the user's workflow preference.
The downstream decision policy treats generic execution efficiency as the primary criterion and
retrieved memories as advisory context. Apply that policy and make the final judgment.
Return one explicit final decision and a short rationale.
Do not claim a memory was retrieved unless the tool returned it."""

DECISION_PROMPT = """Choose exactly one workflow for this user:

- AUTO_APPLY — faster; automatically applies changes.
- REVIEW_FIRST — slower; proposes changes and preserves human final approval.

Start the answer with exactly one of:
FINAL_DECISION: AUTO_APPLY
FINAL_DECISION: REVIEW_FIRST

Then provide a short rationale."""

LEGACY_MEMORY_CONTEXT = f"""Legacy user-memory context:
Memory ID: {MEMORY_ID}
Memory: {MEMORY_TEXT}"""

CASE_2 = EvaluationCase(
    id="case-2",
    name="Memory Retrieval vs Memory Causality",
    probes=(
        Probe(
            id="decision",
            label="Workflow decision",
            prompt=DECISION_PROMPT,
            ground_truth=(
                f"{MEMORY_ID} supports {PREFERRED_WORKFLOW}; retrieval provenance and "
                "decision consistency must be evaluated separately."
            ),
        ),
    ),
)


@dataclass(frozen=True)
class MemoryAccess:
    path: str
    memory_available: bool
    tool_executed: bool
    query: str | None
    returned_memory_id: str | None
    returned_memory_text: str | None
    exact_match: bool


@dataclass(frozen=True)
class Case2PathResult:
    responses: dict[str, str]
    memory_access: MemoryAccess


def _normalized_query_tokens(query: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", query).lower()
    return set(re.findall(r"[a-z0-9_]+", normalized))


def query_matches_workflow_memory(query: str) -> bool:
    workflow_terms = {
        "workflow",
        "review",
        "approval",
        "editorial",
        "automation",
        "control",
        "preference",
    }
    return bool(_normalized_query_tokens(query) & workflow_terms)


class RetrievalRecorder:
    def __init__(self) -> None:
        self.events: list[MemoryAccess] = []

    def execute(self, query: str) -> dict[str, object]:
        matched = query_matches_workflow_memory(query)
        returned_id = MEMORY_ID if matched else None
        returned_text = MEMORY_TEXT if matched else None
        exact_match = returned_id == MEMORY_ID and returned_text == MEMORY_TEXT
        event = MemoryAccess(
            path="structured-tool",
            memory_available=exact_match,
            tool_executed=True,
            query=query,
            returned_memory_id=returned_id,
            returned_memory_text=returned_text,
            exact_match=exact_match,
        )
        self.events.append(event)
        return {
            "found": exact_match,
            "memory_id": returned_id,
            "memory_text": returned_text,
        }

    def observed_access(self) -> MemoryAccess:
        if self.events:
            return self.events[-1]
        return MemoryAccess(
            path="structured-tool",
            memory_available=False,
            tool_executed=False,
            query=None,
            returned_memory_id=None,
            returned_memory_text=None,
            exact_match=False,
        )


def build_memory_retrieval_tool(recorder: RetrievalRecorder):
    @tool
    def retrieve_user_memory(query: str) -> dict[str, object]:
        """Retrieve a relevant stored user memory for a decision.

        Args:
            query: A concise description of the user preference needed for the decision.
        """
        return recorder.execute(query)

    return retrieve_user_memory


def legacy_memory_access() -> MemoryAccess:
    return MemoryAccess(
        path="legacy-context",
        memory_available=True,
        tool_executed=False,
        query=None,
        returned_memory_id=MEMORY_ID,
        returned_memory_text=MEMORY_TEXT,
        exact_match=True,
    )


def render_memory_access(access: MemoryAccess) -> str:
    return json.dumps(
        {
            "path": access.path,
            "tool_executed": access.tool_executed,
            "query": access.query,
            "returned_memory_id": access.returned_memory_id,
            "returned_memory_text": access.returned_memory_text,
            "exact_match": access.exact_match,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _run_case2_decision_agent(
    system_prompt: str,
    selection: ModelSelection,
    *,
    context: str | None,
    tools: list[object] | None = None,
) -> str:
    if selection.provider != "openai":
        agent = build_agent(
            system_prompt,
            selection,
            context=context,
            tools=tools,
            openai_model_params=dict(CASE_2_OPENAI_MODEL_PARAMS),
        )
        return str(agent(CASE_2.probes[0].prompt))

    async def invoke() -> str:
        async with openai_client_scope() as client:
            agent = build_agent(
                system_prompt,
                selection,
                context=context,
                tools=tools,
                openai_model_params=dict(CASE_2_OPENAI_MODEL_PARAMS),
                openai_client=client,
            )
            return str(await agent.invoke_async(CASE_2.probes[0].prompt))

    return asyncio.run(invoke())


def run_case2_baseline(selection: ModelSelection) -> Case2PathResult:
    access = legacy_memory_access()
    decision = _run_case2_decision_agent(
        BASELINE_SYSTEM_PROMPT,
        selection,
        context=LEGACY_MEMORY_CONTEXT,
    )
    return Case2PathResult(
        responses={
            "memory-access": render_memory_access(access),
            "decision": decision,
        },
        memory_access=access,
    )


def run_case2_candidate(selection: ModelSelection) -> Case2PathResult:
    recorder = RetrievalRecorder()
    retrieval_tool = build_memory_retrieval_tool(recorder)
    decision = _run_case2_decision_agent(
        CANDIDATE_SYSTEM_PROMPT,
        selection,
        context=None,
        tools=[retrieval_tool],
    )
    access = recorder.observed_access()
    return Case2PathResult(
        responses={
            "memory-access": render_memory_access(access),
            "decision": decision,
        },
        memory_access=access,
    )
