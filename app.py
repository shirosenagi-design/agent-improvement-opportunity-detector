from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.schemas import TrialRequest, TrialResult
from core.trial import run_research_trial

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = FastAPI(
    title="PROJECT 04 — Personalization Opportunity Mining",
    version="0.6.0-research-boundary",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def configured_key() -> str | None:
    return os.getenv("PROJECT04_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "live_trials_available": bool(configured_key()),
        "model": os.getenv("OPENAI_MODEL_ID", os.getenv("OPENAI_MODEL", "gpt-5.6-sol")),
        "population_is_synthetic": True,
    }


@app.post("/api/trial", response_model=TrialResult)
async def trial(request: TrialRequest):
    key = configured_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Live Research Trial needs an OpenAI API key on this machine. "
                "PROJECT04_OPENAI_API_KEY is preferred. The key is never sent to the browser."
            ),
        )
    try:
        return await run_research_trial(request, api_key=key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Research Trial could not complete: {type(exc).__name__}. "
                "Check the local server terminal for details."
            ),
        ) from exc
