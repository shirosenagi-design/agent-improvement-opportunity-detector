import json
import uuid

from dotenv import load_dotenv

from core.case2 import CASE_2
from core.runner import execute_case2
from core.schemas import EvaluationRun, RunState


def main() -> int:
    load_dotenv()
    run = EvaluationRun(id=str(uuid.uuid4()), case_id=CASE_2.id, state=RunState.IDLE)
    execute_case2(run)
    print(json.dumps(run.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 1 if run.state == RunState.ERROR else 0


if __name__ == "__main__":
    raise SystemExit(main())