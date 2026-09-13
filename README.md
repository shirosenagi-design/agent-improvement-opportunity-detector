# PROJECT 04 — Personalization Opportunity Mining

> **What becomes visible when an AI reasons for one person?**

PROJECT 04 V6.2 is a live, developer-facing Research Trial built with the Strands Agents SDK. It compares a population-oriented baseline with personalized reasoning for the same user message, preserves the observed difference, and returns neutral questions for a human developer to test.

The V6.2 build is the branded form of the V6 research-boundary implementation. It does not redesign the trial or introduce a new evaluation product.

## What the trial compares

### A — Macro population baseline

The baseline uses a deterministic synthetic population profile. Its preset and dimensions represent aggregate preference pressure for broad acceptability, usefulness, and low risk.

The population is simulated. It is not real-user data, votes, feedback, training examples, or a production RLHF pipeline.

### B — Personalized reasoning

The personalized path uses the same base model, base persona, user message, truthfulness requirements, and safety floor. Its experimental difference is a provisional user model inferred from:

- self-reported MBTI as a weak cold-start bootstrap,
- a short self-introduction as stronger person-specific evidence, and
- the current user message as immediate task context.

The provisional user model is a fallible hypothesis, not an identity claim or personality diagnosis. Concrete self-description overrides MBTI stereotypes.

## Live Research Trial flow

1. The browser collects a User message, self-reported MBTI, Short self-introduction, Synthetic population preset, optional population weights, and base AI persona.
2. `POST /api/trial` validates a `TrialRequest` and starts `run_research_trial`.
3. A Strands Evaluation Orchestrator calls the implemented bounded tools:
   - `prepare_synthetic_population`
   - `infer_provisional_user_model`
   - `generate_population_mode_response`
   - `generate_personalized_mode_response`
   - `measure_current_pair`
   - `run_one_counterfactual_probe` — at most once, only when evidence is genuinely ambiguous
4. Population and Personalized subject agents answer the exact same User message.
5. Deterministic measurements provide supporting surface evidence; they are never treated as a quality score.
6. The orchestrator preserves the raw response pair and builds an Evidence-backed `OpportunityPacket`.
7. Only the strongest observed differences become neutral Questions to test.
8. A `TrialResult` returns the population profile, provisional user model, raw responses, measurements, Opportunity Packet, Agent Trace, model ID, and synthetic-population flag.
9. The UI displays Observed difference, Questions to test, and the terminal Developer judgment boundary.

The Agent Trace is built from actual execution events.

## Research boundary

PROJECT 04 deliberately stops before an optimization or adoption decision.

- Personalized is not automatically better.
- The synthetic population baseline remains valuable and is not presented as real-user evidence.
- MBTI is only a cold-start bootstrap.
- Response length, brevity, readability, and generic cognitive load are not general quality metrics.
- The output is evidence plus neutral, falsifiable questions.
- No behavior is automatically adopted, generalized, implemented, or used to update a model.
- Final judgment remains human.

## Architecture

![PROJECT 04 V6.2 Research Trial architecture](architecture.png)

The code-aligned runtime and boundary description is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## API

| Route | Behavior |
|---|---|
| `GET /` | Serve the V6.2 Live Research Trial UI |
| `GET /api/health` | Report local readiness, selected model, and the synthetic-population flag |
| `POST /api/trial` | Accept `TrialRequest` and return `TrialResult` |

## Provider and transport

The live trial uses the Strands OpenAI provider.

- `PROJECT04_OPENAI_API_KEY` is preferred; `OPENAI_API_KEY` is the fallback.
- `OPENAI_MODEL_ID` selects the model; `OPENAI_MODEL` remains a fallback.
- The default model is `gpt-5.6-sol`.
- Windows system trust is supplied through `truststore.SSLContext` to a verified async httpx client.
- TLS verification stays enabled.
- OpenAI SDK retries are disabled with `max_retries=0`.
- One caller-owned `AsyncOpenAI` client is reused for the trial tool loop and closed in `finally`.
- The API key is never returned to the browser or stored in a result.

## Local setup

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `PROJECT04_OPENAI_API_KEY` in the Windows user or process environment when available. Do not commit `.env`.

Start the app:

```powershell
python -m uvicorn app:app --reload
```

Open <http://127.0.0.1:8000/>.

On Windows, `SETUP_WINDOWS.cmd` and `RUN_WINDOWS.cmd` provide the packaged setup and launch path.

## Tests

```powershell
python -m pytest -q
python -m py_compile app.py core/*.py
node --check static/app.js
```

The known V6.2 baseline is 15 passing tests.

## License and data handling

Do not commit API keys, `.env`, `.venv`, caches, or private/local source material. Trial inputs are submitted to the configured OpenAI model for live inference. The synthetic population is generated locally from deterministic presets and is explicitly marked synthetic in `TrialResult`.
