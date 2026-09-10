import threading

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.artifacts import load_latest_run_artifact, load_run_artifact
from core.cases import CASE_1
from core.runner import RUNS, execute_case1


load_dotenv()
app = FastAPI(title="AI Agent Improvement Opportunity Detector")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    with open("templates/index.html", encoding="utf-8") as page:
        return HTMLResponse(page.read())


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cases")
def cases() -> list[dict[str, object]]:
    return [
        {
            "id": CASE_1.id,
            "name": CASE_1.name,
            "probes": [
                {"id": probe.id, "label": probe.label, "prompt": probe.prompt}
                for probe in CASE_1.probes
            ],
        }
    ]


@app.get("/api/artifacts/runs/latest", response_class=JSONResponse)
def get_latest_run_artifact() -> JSONResponse:
    try:
        artifact = load_latest_run_artifact()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No saved run artifacts found") from exc
    return JSONResponse(content=artifact)


@app.get("/api/artifacts/runs/{run_id}", response_class=JSONResponse)
def get_run_artifact(run_id: str) -> JSONResponse:
    try:
        artifact = load_run_artifact(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact run ID") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Saved run artifact not found") from exc
    return JSONResponse(content=artifact)


@app.post("/api/evaluations/run", status_code=202)
def run_evaluation() -> dict[str, str]:
    run = RUNS.create()
    thread = threading.Thread(
        target=execute_case1,
        args=(run, RUNS.save),
        daemon=True,
        name=f"case-1-{run.id}",
    )
    thread.start()
    return {"run_id": run.id}


@app.get("/api/evaluations/{run_id}")
def get_evaluation(run_id: str):
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run