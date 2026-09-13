# PROJECT 04 V6.2 Research Trial architecture

![PROJECT 04 V6.2 Research Trial architecture](../architecture.png)

## Runtime topology

`app.py` exposes the finished V6.2 trial:

| Route | Implementation |
|---|---|
| `GET /` | Serve `static/index.html` |
| `GET /api/health` | Report whether a local OpenAI key is available, the selected model, and `population_is_synthetic=true` |
| `POST /api/trial` | Validate `TrialRequest`, execute `run_research_trial`, and return `TrialResult` |

The browser sends:

- User message
- self-reported MBTI
- Short self-introduction
- Synthetic population preset and optional weights
- population size and deterministic seed
- base AI persona

The API key stays on the server.

## Strands orchestration

`run_research_trial` creates one caller-owned `AsyncOpenAI` client and a Strands `OpenAIModel` factory. The Evaluation Orchestrator and its subject/inference agents use the same selected model during one trial.

The Orchestrator has six implemented bounded tools:

1. `prepare_synthetic_population` creates or returns the deterministic synthetic aggregate profile.
2. `infer_provisional_user_model` infers a cold-start hypothesis from MBTI, self-introduction, and the current task.
3. `generate_population_mode_response` produces the broad-population baseline response.
4. `generate_personalized_mode_response` produces a response through the provisional user model.
5. `measure_current_pair` records supporting surface measurements after both raw responses exist.
6. `run_one_counterfactual_probe` permits at most one ambiguity-targeted re-probe.

Tool outputs are stored in trial state and execution events are appended to `agent_trace`. The application guardrail requires the population profile, provisional user model, and both live responses before a semantic result can be returned.

## Experimental conditions

### Population Mode

- Uses a deterministic synthetic population distribution.
- Represents broad aggregate preference pressure.
- Does not receive the separate self-introduction or provisional user model.
- Is not real-user evidence, a vote, training data, or production RLHF.

### Personalized Mode

- Uses the same base model, base persona, User message, truthfulness requirements, and safety floor.
- Receives a provisional model for this individual.
- Treats self-reported MBTI as a weak cold-start prior.
- Treats the Short self-introduction and current task as stronger evidence.
- Adapts reasoning priorities when warranted, not merely tone or MBTI-flavored wording.

The trial does not assume Personalized Mode is better.

## Deterministic measurement boundary

`measure_pair` records phrase hits, personal-context term hits, and lexical overlap. These are supporting observations only.

Length, sentence count, brevity, readability, and generic cognitive load are not treated as general quality signals. Semantic claims require exact excerpts from the two live responses.

## TrialResult and Evidence Packet

`TrialResult` contains:

- the exact User message, MBTI, and Short self-introduction,
- `PopulationProfile`,
- optional `ProvisionalUserModel`,
- raw Population and Personalized responses,
- deterministic measurements,
- `OpportunityPacket`,
- actual `AgentTraceEvent` records,
- model ID, and
- `population_is_synthetic=true`.

The `OpportunityPacket` keeps the conditions asymmetric:

- `population_baseline` records what the macro baseline contains and what it does not foreground for this user.
- `personalized_observation` records what newly surfaced, what baseline elements remain, and what may have weakened or disappeared.
- `research_questions` converts only strong observed differences into neutral, Evidence-backed Questions to test.
- `human_review_prompt` hands the unresolved judgment to the developer.

Exact excerpts are validated against the raw responses before they survive in the packet.

## Provider and security boundary

- `PROJECT04_OPENAI_API_KEY` is preferred; `OPENAI_API_KEY` is the fallback.
- `OPENAI_MODEL_ID` is preferred; `OPENAI_MODEL` is the fallback; `gpt-5.6-sol` is the default.
- Windows system trust is provided by `truststore.SSLContext`.
- `DefaultAsyncHttpxClient` keeps TLS verification enabled.
- `AsyncOpenAI` uses `max_retries=0`.
- The caller-owned client is reused throughout the tool loop and closed exactly once in `finally`.
- The key is not sent to the browser or included in `TrialResult`.

## Human Review boundary

PROJECT 04 returns observations and neutral Questions to test. It does not choose a winner, recommend adoption, prescribe implementation scope, generalize from one person, or update an agent/model.

The final sequence is:

```text
Population-oriented baseline
→ Personalized reasoning
→ Observed difference
→ Questions to test
→ Developer judgment
```

Developer judgment is the terminal boundary.
