import threading
import uuid
from collections.abc import Callable

from core.agents import resolve_model_selection, run_agent_suite
from core.artifacts import save_run_artifact
from core.case2 import CASE_2, run_case2_baseline, run_case2_candidate
from core.case2_evals import build_case2_opportunity, evaluate_case2_dimensions
from core.case3 import CASE_3, run_case3_baseline, run_case3_candidate
from core.case3_evals import build_case3_opportunity, evaluate_case3_dimensions
from core.cases import BASELINE_PROMPT, CANDIDATE_PROMPT, CASE_1
from core.compare import build_opportunity, needs_human_review
from core.evals import evaluate_dimensions
from core.schemas import EvaluationRun, RunState


UpdateCallback = Callable[[EvaluationRun], None]


def execute_case1(run: EvaluationRun, update: UpdateCallback | None = None) -> EvaluationRun:
    def publish() -> None:
        if update:
            update(run)

    try:
        run.state = RunState.CONFIGURING
        selection = resolve_model_selection()
        run.model_id = selection.model_id
        run.metadata.update(
            {"model_provider": selection.provider, "model_id": selection.model_id}
        )
        publish()
        run.state = RunState.RUNNING_BASELINE
        publish()
        run.baseline_responses = run_agent_suite(CASE_1, BASELINE_PROMPT, selection)
        publish()
        run.state = RunState.RUNNING_CANDIDATE
        publish()
        run.candidate_responses = run_agent_suite(CASE_1, CANDIDATE_PROMPT, selection)
        publish()
        run.state = RunState.EVALUATING
        publish()
        run.dimensions = evaluate_dimensions(run.baseline_responses, run.candidate_responses)
        run.state = RunState.COMPARING
        publish()
        opportunity = build_opportunity(
            CASE_1.id, run.baseline_responses, run.candidate_responses, run.dimensions
        )
        run.opportunities = [opportunity] if opportunity else []
        run.human_review = needs_human_review(run.dimensions)
        run.state = RunState.OPPORTUNITIES_FOUND if opportunity else RunState.NO_OPPORTUNITIES
    except Exception as exc:
        run.state = RunState.ERROR
        run.error = f"{type(exc).__name__}: {exc}"

    try:
        save_run_artifact(run)
    except Exception as exc:
        artifact_error = f"ArtifactPersistenceError: {type(exc).__name__}: {exc}"
        run.error = f"{run.error}; {artifact_error}" if run.error else artifact_error
        run.state = RunState.ERROR

    publish()
    return run


def execute_case2(run: EvaluationRun, update: UpdateCallback | None = None) -> EvaluationRun:
    def publish() -> None:
        if update:
            update(run)

    try:
        run.state = RunState.CONFIGURING
        selection = resolve_model_selection()
        run.model_id = selection.model_id
        run.metadata.update(
            {"model_provider": selection.provider, "model_id": selection.model_id}
        )
        publish()

        run.state = RunState.RUNNING_BASELINE
        publish()
        baseline = run_case2_baseline(selection)
        run.baseline_responses = baseline.responses
        publish()

        run.state = RunState.RUNNING_CANDIDATE
        publish()
        candidate = run_case2_candidate(selection)
        run.candidate_responses = candidate.responses
        publish()

        run.state = RunState.EVALUATING
        publish()
        run.dimensions = evaluate_case2_dimensions(baseline, candidate)

        run.state = RunState.COMPARING
        publish()
        opportunity = build_case2_opportunity(
            CASE_2.id,
            run.baseline_responses,
            run.candidate_responses,
            run.dimensions,
        )
        run.opportunities = [opportunity] if opportunity else []
        run.human_review = needs_human_review(run.dimensions)
        run.state = (
            RunState.OPPORTUNITIES_FOUND
            if opportunity
            else RunState.NO_OPPORTUNITIES
        )
    except Exception as exc:
        run.state = RunState.ERROR
        run.error = f"{type(exc).__name__}: {exc}"

    try:
        save_run_artifact(run)
    except Exception as exc:
        artifact_error = f"ArtifactPersistenceError: {type(exc).__name__}: {exc}"
        run.error = f"{run.error}; {artifact_error}" if run.error else artifact_error
        run.state = RunState.ERROR

    publish()
    return run


def execute_case3(run: EvaluationRun, update: UpdateCallback | None = None) -> EvaluationRun:
    def publish() -> None:
        if update:
            update(run)

    try:
        run.state = RunState.CONFIGURING
        selection = resolve_model_selection()
        run.model_id = selection.model_id
        run.metadata.update(
            {"model_provider": selection.provider, "model_id": selection.model_id}
        )
        publish()

        run.state = RunState.RUNNING_BASELINE
        publish()
        baseline = run_case3_baseline(selection)
        run.baseline_responses = baseline.responses
        publish()

        run.state = RunState.RUNNING_CANDIDATE
        publish()
        candidate = run_case3_candidate(selection)
        run.candidate_responses = candidate.responses
        publish()

        run.state = RunState.EVALUATING
        publish()
        run.dimensions = evaluate_case3_dimensions(baseline, candidate)

        run.state = RunState.COMPARING
        publish()
        opportunity = build_case3_opportunity(
            CASE_3.id,
            run.baseline_responses,
            run.candidate_responses,
            run.dimensions,
        )
        run.opportunities = [opportunity] if opportunity else []
        run.human_review = needs_human_review(run.dimensions)
        run.state = (
            RunState.OPPORTUNITIES_FOUND
            if opportunity
            else RunState.NO_OPPORTUNITIES
        )
    except Exception as exc:
        run.state = RunState.ERROR
        run.error = f"{type(exc).__name__}: {exc}"

    try:
        save_run_artifact(run)
    except Exception as exc:
        artifact_error = f"ArtifactPersistenceError: {type(exc).__name__}: {exc}"
        run.error = f"{run.error}; {artifact_error}" if run.error else artifact_error
        run.state = RunState.ERROR

    publish()
    return run


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, EvaluationRun] = {}
        self._lock = threading.Lock()

    def create(self) -> EvaluationRun:
        run = EvaluationRun(id=str(uuid.uuid4()), case_id=CASE_1.id, state=RunState.IDLE)
        self.save(run)
        return run

    def save(self, run: EvaluationRun) -> None:
        with self._lock:
            self._runs[run.id] = run.model_copy(deep=True)

    def get(self, run_id: str) -> EvaluationRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            return run.model_copy(deep=True) if run else None


RUNS = RunStore()
