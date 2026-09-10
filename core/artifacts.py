import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from core.compare import is_tradeoff
from core.schemas import EvaluationRun


RUN_ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "runs"
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def _canonical_artifact_run_id(run_id: str) -> str:
    try:
        parsed = UUID(run_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Artifact run ID must be a UUID") from exc

    canonical = str(parsed)
    if run_id.lower() != canonical:
        raise ValueError("Artifact run ID must use canonical UUID format")
    return canonical


def load_run_artifact(
    run_id: str, directory: Path | None = None
) -> dict[str, Any]:
    canonical_run_id = _canonical_artifact_run_id(run_id)
    artifact_directory = (directory or RUN_ARTIFACT_DIR).resolve()
    artifact_path = (artifact_directory / f"{canonical_run_id}.json").resolve()

    if artifact_path.parent != artifact_directory:
        raise ValueError("Artifact path must remain inside the run artifact directory")
    if not artifact_path.is_file():
        raise FileNotFoundError(canonical_run_id)

    with artifact_path.open(encoding="utf-8") as artifact_file:
        return json.load(artifact_file)


def load_latest_run_artifact(
    directory: Path | None = None,
) -> dict[str, Any]:
    artifact_directory = (directory or RUN_ARTIFACT_DIR).resolve()
    candidates: list[Path] = []

    if artifact_directory.is_dir():
        for artifact_path in artifact_directory.glob("*.json"):
            try:
                canonical_run_id = _canonical_artifact_run_id(artifact_path.stem)
            except ValueError:
                continue
            if artifact_path.name == f"{canonical_run_id}.json":
                candidates.append(artifact_path)

    if not candidates:
        raise FileNotFoundError("No saved run artifacts found")

    latest_path = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    return load_run_artifact(latest_path.stem, artifact_directory)


def build_run_artifact(run: EvaluationRun) -> dict[str, Any]:
    opportunity = run.opportunities[0] if run.opportunities else None
    return {
        "run_id": run.id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "case_id": run.case_id,
        "state": run.state.value,
        "provider": run.metadata.get("model_provider"),
        "model_id": run.model_id,
        "baseline_responses": run.baseline_responses,
        "candidate_responses": run.candidate_responses,
        "dimensions": [dimension.model_dump(mode="json") for dimension in run.dimensions],
        "trade_off_detected": is_tradeoff(run.dimensions),
        "opportunity": opportunity.model_dump(mode="json") if opportunity else None,
        "human_review": run.human_review,
        "error": run.error,
    }


def save_run_artifact(
    run: EvaluationRun, directory: Path | None = None
) -> Path:
    if not SAFE_RUN_ID.fullmatch(run.id):
        raise ValueError("Run ID contains unsupported characters")
    output_directory = directory or RUN_ARTIFACT_DIR
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"{run.id}.json"
    temporary_path = output_directory / f".{run.id}.tmp"
    payload = build_run_artifact(run)
    with temporary_path.open("w", encoding="utf-8", newline="\n") as artifact_file:
        json.dump(payload, artifact_file, ensure_ascii=False, indent=2)
        artifact_file.write("\n")
    temporary_path.replace(output_path)
    return output_path